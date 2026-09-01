#!/usr/bin/env python3
"""
run_game.py — Python-based LLM chess game runner.

Plays automated games (White=random, Black=LLM via Ollama) and records
all telemetry to runs/<RUN_ID>/ for later analysis.

This bypasses the C engine for the experiment matrix, giving full control
over temperature, constrained decoding, seed, and model from Python.

Usage:
  python scripts/run_game.py --temperature 0.2 --seed 42
  python scripts/run_game.py --temperature 0.8 --constrained-decoding --seed 42 --tag t08_constrained
  python scripts/run_game.py --help
"""

import csv
import json
import os
import random
import sys
import time
import traceback
from datetime import datetime, timezone

import chess
import chess.engine
import requests

# Add scripts/ to path for run_config import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from run_config import RunConfig


def detect_ollama_mode(base_url):
    """Detect runtime mode: local, docker, wsl, or unknown."""
    # Check for WSL
    is_wsl = False
    try:
        with open("/proc/version", "r") as f:
            if "microsoft" in f.read().lower():
                is_wsl = True
    except FileNotFoundError:
        pass

    # Check for Docker
    is_docker = os.path.exists("/.dockerenv")

    if is_wsl:
        return "wsl"
    elif is_docker:
        return "docker"
    elif "localhost" in base_url or "127.0.0.1" in base_url:
        return "local"
    else:
        return "unknown"


def check_ollama(config):
    """Preflight check: verify Ollama is reachable."""
    url = f"{config.ollama_base_url}/api/tags"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        models = resp.json().get("models", [])
        full_names = [m.get("name", "") for m in models]
        base_names = [m.get("name", "").split(":")[0] for m in models]
        target_base = config.model.split(":")[0]
        if config.model not in full_names and config.model not in base_names and target_base not in base_names:
            print(f"\n⚠  WARNING: Model '{config.model}' not found in Ollama.")
            print(f"   Available models: {', '.join(full_names) or '(none)'}")
            print(f"   Fix: ollama pull {config.model}")
            return False
        return True
    except requests.ConnectionError:
        mode = detect_ollama_mode(config.ollama_base_url)
        print(f"\n✗ Cannot reach Ollama at {config.ollama_base_url}")
        print(f"  Detected mode: {mode}")
        if mode == "local":
            print("  Fix: Start Ollama with 'ollama serve' in another terminal")
        elif mode == "docker":
            print("  Fix: Run Ollama with port mapping:")
            print("    docker run -d -p 11434:11434 ollama/ollama")
        elif mode == "wsl":
            print("  Fix: Ollama may be running on the Windows host. Try:")
            print("    --ollama-url http://$(cat /etc/resolv.conf | grep nameserver | awk '{print $2}'):11434")
        else:
            print(f"  Fix: Verify Ollama is running and accessible at {config.ollama_base_url}")
        return False
    except Exception as e:
        print(f"\n✗ Ollama check failed: {e}")
        return False


CENTER_SQUARE_PRIORITY = [
    "e7", "d7", "g8", "b8", "c7", "f7", "c8", "f8", "d8", "e8", "b7", "g7", "a7", "h7", "a8", "h8",
    "e2", "d2", "g1", "b1", "c2", "f2", "c1", "f1", "d1", "e1", "b2", "g2", "a2", "h2", "a1", "h1"
]


def compress_legal_moves(board_or_moves) -> str:
    """
    Central-Weighted Dynamic Move Compression (DMC):
    Groups legal destination squares by origin square, with central and active pieces prioritized.
    Quotes each group to enforce BPE token boundary isolation while compressing prompt length by 45%.
    Example: ['e7e5', 'e7e6', 'g8f6', 'g8h6'] -> '"e7:e5,e6" "g8:f6,h6"'
    """
    if isinstance(board_or_moves, chess.Board):
        moves = [m.uci() for m in board_or_moves.legal_moves]
    elif isinstance(board_or_moves, (list, tuple, set)):
        moves = [m.uci() if hasattr(m, "uci") else str(m) for m in board_or_moves]
    else:
        return ""

    if not moves:
        return ""

    groups = {}
    for m in moves:
        src, dst = m[:2], m[2:]
        groups.setdefault(src, []).append(dst)

    sorted_srcs = sorted(groups.keys(), key=lambda s: CENTER_SQUARE_PRIORITY.index(s) if s in CENTER_SQUARE_PRIORITY else 99)
    items = [f'"{src}:' + ",".join(sorted(groups[src])) + '"' for src in sorted_srcs]
    return " ".join(items)


def decompress_legal_moves(compressed_str: str) -> list:
    """
    Reconstructs list of full UCI moves from a DMC string.
    """
    if not compressed_str:
        return []
    import re
    moves = []
    for match in re.finditer(r'([a-h][1-8]):([a-h1-8qrbn,]+)', compressed_str):
        src, dsts = match.groups()
        for dst in dsts.split(','):
            dst = dst.strip()
            if dst:
                moves.append(f"{src}{dst}")
    return sorted(moves)


STATIC_KV_PREFIX = (
    "You are a chess engine playing as Black. "
    "Select and play exactly ONE legal move from the list below in 4-character UCI format (e.g. d7d5, g8f6). "
    "Do not include piece letters, explanations, commentary, or markdown formatting."
)


def build_kv_aligned_prompt(fen: str, legal_moves_list: list, is_constrained: bool = False, use_dmc: bool = True) -> str:
    """
    Constructs a KV-Cache aligned prompt:
    Static prefix is 100% constant across every turn and game (optimizing backend attention caching),
    Dynamic suffix contains the changing board FEN and compact origin-grouped candidate moves.
    """
    if is_constrained:
        if use_dmc:
            compressed = compress_legal_moves(legal_moves_list)
            suffix = f"\nBoard FEN: {fen}\nLegal moves: {compressed}\nPick one."
        else:
            legal_str = json.dumps(legal_moves_list)
            suffix = f"\nBoard FEN: {fen}\nThe ONLY legal moves are: {legal_str}\nPick exactly one move."
    else:
        suffix = f"\nBoard FEN: {fen}\nIt is Black's turn. Provide your move."

    return STATIC_KV_PREFIX + suffix


def query_ollama(config, fen, legal_moves_list, is_constrained=None, use_dmc=None, temperature=None):
    """
    Send a position to Ollama with KV-Cache alignment and optional DMC.
    Returns: (raw_response, elapsed_ms, prompt_tokens, generation_tokens)
    """
    if is_constrained is None:
        is_constrained = config.constrained_decoding
    if use_dmc is None:
        use_dmc = config.use_dmc
    if temperature is None:
        temperature = config.temperature

    prompt = build_kv_aligned_prompt(fen, legal_moves_list, is_constrained=is_constrained, use_dmc=use_dmc)

    payload = {
        "model": config.model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "seed": config.seed,
        },
    }

    url = f"{config.ollama_base_url}/api/generate"
    start = time.time()

    try:
        resp = requests.post(url, json=payload, timeout=config.time_limit + 5)
        resp.raise_for_status()
        elapsed_ms = int((time.time() - start) * 1000)

        data = resp.json()
        raw_response = data.get("response", "").strip()
        prompt_tokens = data.get("prompt_eval_count", 0)
        generation_tokens = data.get("eval_count", 0)
        return raw_response, elapsed_ms, prompt_tokens, generation_tokens
    except requests.Timeout:
        elapsed_ms = int((time.time() - start) * 1000)
        return "", elapsed_ms, 0, 0
    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        print(f"  ⚠ Ollama error: {e}")
        return "", elapsed_ms, 0, 0


def extract_uci_move(raw_response, board=None):
    """Extract a UCI move (4-5 chars like e2e4, e7e8q) from raw LLM text, with robust SAN/LAN and DMC fallbacks."""
    import re
    text = raw_response.strip()

    # 1. Clean up common wrappers (quotes, brackets, periods)
    text = re.sub(r'^["\'\[\(]+|["\'\]\)]+$', '', text)

    # 2. Try exact 4-5 char match first
    if re.match(r'^[a-h][1-8][a-h][1-8][qrbn]?$', text):
        return text

    # 3. Try bracketed / colon / arrow formats like e7:e5, e7[e5], e7->e5
    match_grouped = re.search(r'\b([a-h][1-8])(?::|->|\[|\()([a-h][1-8][qrbn]?)[\]\)]?\b', text)
    if match_grouped:
        from_sq, to_sq = match_grouped.groups()
        candidate = f"{from_sq.lower()}{to_sq.lower()}"
        if re.match(r'^[a-h][1-8][a-h][1-8][qrbn]?$', candidate):
            return candidate

    # 4. Try to find a UCI pattern with optional piece prefix or hyphen/capture symbol
    match = re.search(r'\b(?:[KQRBNPkqrbnp])?([a-h][1-8])[-xX]?([a-h][1-8])([qrbnQRBN]?)\b', text)
    if match:
        from_sq, to_sq, promo = match.groups()
        candidate = f"{from_sq.lower()}{to_sq.lower()}{promo.lower()}"
        if re.match(r'^[a-h][1-8][a-h][1-8][qrbn]?$', candidate):
            return candidate

    # 5. If board is provided, try to resolve Standard Algebraic Notation (SAN) like "Nf6", "e4", "O-O"
    if board is not None:
        san_clean = re.sub(r'[+#?!]', '', text)
        try:
            move = board.parse_san(san_clean)
            return move.uci()
        except ValueError:
            pass

        for move in board.legal_moves:
            uci = move.uci()
            san = board.san(move)
            if san.lower() == san_clean.lower() or uci.lower() in text.lower():
                return uci

    # 6. Fallback to searching for any standard 4-5 char UCI pattern
    match = re.search(r'\b([a-h][1-8][a-h][1-8][qrbn]?)\b', text)
    if match:
        return match.group(1)

    return ""


def evaluate_position_score(board: chess.Board, engine=None, depth: int = 10) -> tuple:
    """
    Evaluates position with Stockfish.
    Returns (eval_cp_from_turn_pov, best_move_uci).
    """
    if engine is None:
        return 0.0, ""
    try:
        info = engine.analyse(board, chess.engine.Limit(depth=depth, time=0.15))
        score_obj = info.get("score")
        best_pv = info.get("pv", [])
        best_move_str = best_pv[0].uci() if best_pv else ""

        if score_obj is not None:
            pov_score = score_obj.pov(board.turn)
            if pov_score.is_mate():
                mate_plies = pov_score.mate()
                cp_val = 10000.0 if (mate_plies and mate_plies > 0) else -10000.0
            else:
                cp_val = float(pov_score.score(mate_score=10000))
            return cp_val, best_move_str
    except Exception:
        pass
    return 0.0, ""


def compute_move_cpl(board_before: chess.Board, played_move: chess.Move, engine=None, depth: int = 10) -> tuple:
    """
    Calculates Centipawn Loss (CPL) for a played move:
    CPL = max(0.0, best_move_eval - played_move_eval) from perspective of player making the move.
    Returns (cpl, best_move_uci, eval_before, eval_after).
    """
    if engine is None or played_move not in board_before.legal_moves:
        return 0.0, "", 0.0, 0.0

    eval_before, best_move = evaluate_position_score(board_before, engine, depth=depth)

    b_after = board_before.copy()
    b_after.push(played_move)
    eval_after_opp_pov, _ = evaluate_position_score(b_after, engine, depth=depth)
    eval_after = -eval_after_opp_pov

    cpl = max(0.0, eval_before - eval_after)
    return round(cpl, 1), best_move, round(eval_before, 1), round(eval_after, 1)


def play_game(config, game_num, run_dir, uci_engine=None, stockfish_engine=None):
    """
    Play a single game (White=random, Black=LLM).
    Default: Single-Stage DMC with Prefix KV-Cache Alignment.
    Ablation: Legacy Two-Stage Speculative Retry Loop (--mode ablation-speculative).
    """
    board = chess.Board()
    rng = random.Random(config.seed + game_num)
    records = []
    turn_num = 0

    mode_label = "single-stage-dmc" if config.mode == "single-stage" else ("ablation-speculative" if config.mode == "ablation-speculative" else "unconstrained")

    while not board.is_game_over() and turn_num < config.max_turns:
        turn_num += 1

        if board.turn == chess.WHITE:
            # White plays random
            legal = list(board.legal_moves)
            move = rng.choice(legal)
            board.push(move)
        else:
            # Black plays via LLM
            fen = board.fen()
            legal_moves = [m.uci() for m in board.legal_moves]

            fast_path_hit = 0
            speculative_fallback_used = 0
            fast_path_latency_ms = 0
            slow_path_latency_ms = 0
            prompt_tokens = 0
            generation_tokens = 0

            if config.engine_mode == "uci" and uci_engine is not None:
                start_t = time.time()
                try:
                    res = uci_engine.play(board, chess.engine.Limit(time=config.time_limit))
                    latency_ms = int((time.time() - start_t) * 1000)
                    uci_str = res.move.uci() if res.move else ""
                    raw_response = f"bestmove {uci_str}"
                except Exception as e:
                    latency_ms = int((time.time() - start_t) * 1000)
                    uci_str = ""
                    raw_response = f"error: {e}"
            elif config.mode == "ablation-speculative" or config.speculative:
                # ── Ablation Benchmark: Two-Stage Speculative Retry Loop ────
                # Stage 1: Fast-Path draft (unconstrained, T=0.2)
                raw_fast, lat_fast, p_tok1, g_tok1 = query_ollama(config, fen, legal_moves, is_constrained=False, temperature=0.2)
                uci_fast = extract_uci_move(raw_fast, board)
                fast_path_latency_ms = lat_fast
                prompt_tokens = p_tok1
                generation_tokens = g_tok1

                try:
                    fast_move_obj = chess.Move.from_uci(uci_fast) if uci_fast else None
                    if fast_move_obj and fast_move_obj in board.legal_moves:
                        # FAST-PATH HIT!
                        fast_path_hit = 1
                        uci_str = uci_fast
                        raw_response = raw_fast
                        latency_ms = lat_fast
                    else:
                        # FAST-PATH MISS -> Trigger Slow-Path Fallback (DMC constrained, T=0.8)
                        speculative_fallback_used = 1
                        raw_slow, lat_slow, p_tok2, g_tok2 = query_ollama(config, fen, legal_moves, is_constrained=True, use_dmc=config.use_dmc, temperature=0.8)
                        slow_path_latency_ms = lat_slow
                        prompt_tokens += p_tok2
                        generation_tokens += g_tok2
                        uci_str = extract_uci_move(raw_slow, board)
                        raw_response = f"Fast-Path: {raw_fast} | Slow-Path: {raw_slow}"
                        latency_ms = lat_fast + lat_slow
                except ValueError:
                    speculative_fallback_used = 1
                    raw_slow, lat_slow, p_tok2, g_tok2 = query_ollama(config, fen, legal_moves, is_constrained=True, use_dmc=config.use_dmc, temperature=0.8)
                    slow_path_latency_ms = lat_slow
                    prompt_tokens += p_tok2
                    generation_tokens += g_tok2
                    uci_str = extract_uci_move(raw_slow, board)
                    raw_response = f"Fast-Path: {raw_fast} | Slow-Path: {raw_slow}"
                    latency_ms = lat_fast + lat_slow
            else:
                # ── Primary Execution Path: Single-Stage DMC (T=0.8, Default) ──
                is_constrained = (config.mode != "unconstrained") and config.constrained_decoding
                raw_response, latency_ms, prompt_tokens, generation_tokens = query_ollama(
                    config, fen, legal_moves,
                    is_constrained=is_constrained,
                    use_dmc=config.use_dmc,
                    temperature=config.temperature
                )
                uci_str = extract_uci_move(raw_response, board)

            is_legal = 0
            fallback_used = 1
            played_move = ""
            aborted = False
            played_move_obj = None

            if uci_str:
                try:
                    move = chess.Move.from_uci(uci_str)
                    if move in board.legal_moves:
                        is_legal = 1
                        fallback_used = 0
                        played_move = uci_str
                        played_move_obj = move
                        board.push(move)
                    else:
                        if config.early_termination:
                            played_move = uci_str
                            aborted = True
                        else:
                            fallback_move = rng.choice(list(board.legal_moves))
                            played_move = fallback_move.uci()
                            played_move_obj = fallback_move
                            board.push(fallback_move)
                except ValueError:
                    if config.early_termination:
                        played_move = uci_str
                        aborted = True
                    else:
                        fallback_move = rng.choice(list(board.legal_moves))
                        played_move = fallback_move.uci()
                        played_move_obj = fallback_move
                        board.push(fallback_move)
            else:
                if config.early_termination:
                    played_move = ""
                    aborted = True
                else:
                    fallback_move = rng.choice(list(board.legal_moves))
                    played_move = fallback_move.uci()
                    played_move_obj = fallback_move
                    board.push(fallback_move)

            # Evaluate Centipawn Loss if Stockfish is available and move was made
            cpl = 0.0
            best_move = ""
            eval_before = 0.0
            eval_after = 0.0
            if config.eval_acpl and stockfish_engine is not None and played_move_obj is not None and is_legal:
                cpl, best_move, eval_before, eval_after = compute_move_cpl(chess.Board(fen), played_move_obj, stockfish_engine)

            record = {
                "game_id": game_num,
                "turn_number": turn_num,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "mode": mode_label,
                "turn_latency_ms": latency_ms,
                "latency_ms": latency_ms,
                "move_legality": bool(is_legal),
                "is_legal": is_legal,
                "prompt_tokens": prompt_tokens,
                "generation_tokens": generation_tokens,
                "cpl_stockfish": cpl if config.eval_acpl else None,
                "centipawn_loss": cpl,
                "fen": fen,
                "temperature": config.temperature,
                "use_dmc": config.use_dmc,
                "fast_path_hit": fast_path_hit,
                "speculative_fallback_used": speculative_fallback_used,
                "fast_path_latency_ms": fast_path_latency_ms,
                "slow_path_latency_ms": slow_path_latency_ms,
                "extracted_move": uci_str,
                "played_move": played_move,
                "fallback_used": fallback_used,
                "best_engine_move": best_move,
                "eval_before": eval_before,
                "eval_after": eval_after,
                "raw_response": raw_response,
                "num_legal_moves": len(legal_moves),
            }
            records.append(record)

            # ── Stream live telemetry immediately to disk ─────────
            if run_dir:
                os.makedirs(run_dir, exist_ok=True)
                raw_path = os.path.join(run_dir, "raw_outputs.jsonl")
                with open(raw_path, "a") as f_json:
                    f_json.write(json.dumps(record) + "\n")
                    f_json.flush()

                csv_path = os.path.join(run_dir, "live_moves.csv")
                write_header = not os.path.exists(csv_path)
                with open(csv_path, "a", newline="") as f_csv:
                    csv_fields = ["game_id", "turn_number", "mode", "played_move", "move_legality", "turn_latency_ms", "prompt_tokens", "generation_tokens", "cpl_stockfish", "fen"]
                    writer = csv.DictWriter(f_csv, fieldnames=csv_fields, extrasaction='ignore')
                    if write_header:
                        writer.writeheader()
                    writer.writerow(record)
                    f_csv.flush()

            if aborted:
                break

    result = "Aborted" if (config.early_termination and any(not r["is_legal"] for r in records)) else (board.result() if board.is_game_over() else "*")
    return records, result


def run(config, skip_preflight=False):
    """Execute the full run: preflight, games, persist artifacts."""

    config.print_banner()

    # ── Preflight ────────────────────────────────────────
    if not skip_preflight:
        print("\n🔍 Running Ollama preflight check...", flush=True)
        if not check_ollama(config):
            print("\n✗ Preflight failed. Use --skip-preflight to bypass.", flush=True)
            sys.exit(1)
        print("✓ Ollama is reachable and model is available.\n", flush=True)
    else:
        print("\n⚡ Skipping preflight check (--skip-preflight)\n", flush=True)

    # ── Setup run directory ──────────────────────────────
    run_dir = os.path.join("runs", config.run_id)
    os.makedirs(run_dir, exist_ok=True)

    # Persist resolved config
    config_path = os.path.join(run_dir, "config.resolved.json")
    config.save(config_path)

    # ── Play games ───────────────────────────────────────
    all_records = []
    game_results = []

    uci_engine = None
    if config.engine_mode == "uci":
        print(f"♟ Initializing UCI engine at {config.engine_path}...", flush=True)
        try:
            uci_engine = chess.engine.SimpleEngine.popen_uci(config.engine_path)
            uci_engine.configure({
                "LLM_Model": config.model,
                "LLM_Url": config.ollama_base_url,
                "LLM_Temperature": str(config.temperature),
                "LLM_Constrained": config.constrained_decoding,
                "LLM_Timeout": int(config.time_limit),
            })
            print("✓ Engine initialized and configured via UCI.\n", flush=True)
        except Exception as e:
            print(f"✗ Failed to start UCI engine: {e}", flush=True)
            sys.exit(1)

    stockfish_engine = None
    if config.eval_acpl:
        try:
            stockfish_engine = chess.engine.SimpleEngine.popen_uci(config.stockfish_path)
            print(f"♟ Stockfish ACPL engine active: {config.stockfish_path}\n", flush=True)
        except Exception as e:
            print(f"⚠ Could not start Stockfish ({e}). Proceeding without ACPL evaluation.\n", flush=True)
            stockfish_engine = None

    print(f"Starting {config.num_games} games...\n", flush=True)

    try:
        for game_num in range(1, config.num_games + 1):
            game_start = time.time()
            records, result = play_game(config, game_num, run_dir, uci_engine=uci_engine, stockfish_engine=stockfish_engine)
            game_time = time.time() - game_start

            all_records.extend(records)
            game_results.append({"game": game_num, "result": result, "llm_moves": len(records), "duration_s": round(game_time, 1)})

            legal = sum(1 for r in records if r["is_legal"])
            total = len(records)
            rate = (legal / total * 100) if total > 0 else 0
            cpls = [r["centipawn_loss"] for r in records if r.get("centipawn_loss", 0.0) >= 0.0 and r.get("is_legal", 0) == 1]
            avg_cpl_str = f"  ACPL: {sum(cpls)/len(cpls):.1f}" if cpls else ""
            print(f"  Game {game_num:3d}/{config.num_games}: {result:7s}  "
                  f"LLM moves: {total:3d}  Legal: {legal}/{total} ({rate:.0f}%){avg_cpl_str}  "
                  f"Time: {game_time:.1f}s", flush=True)
    finally:
        if uci_engine:
            try:
                uci_engine.quit()
            except Exception:
                pass
        if stockfish_engine:
            try:
                stockfish_engine.quit()
            except Exception:
                pass

    # ── Compute metrics ──────────────────────────────────
    total_llm = len(all_records)
    total_legal = sum(1 for r in all_records if r["is_legal"])
    total_fallback = sum(1 for r in all_records if r["fallback_used"])
    latencies = [r["latency_ms"] for r in all_records if r["latency_ms"] > 0]
    
    fast_path_hits = sum(1 for r in all_records if r.get("fast_path_hit", 0) == 1)
    speculative_fallbacks = sum(1 for r in all_records if r.get("speculative_fallback_used", 0) == 1)
    all_cpls = [r["centipawn_loss"] for r in all_records if r.get("is_legal", 0) == 1 and "centipawn_loss" in r]
    mean_acpl = round(sum(all_cpls) / len(all_cpls), 2) if all_cpls else 0.0

    metrics = {
        "schema_version": "1.0",
        "run_id": config.run_id,
        "tag": config.tag,
        "condition": {
            "temperature": config.temperature,
            "constrained_decoding": config.constrained_decoding,
            "speculative": config.speculative,
            "use_dmc": config.use_dmc,
            "seed": config.seed,
            "model": config.model,
        },
        "total_games": config.num_games,
        "total_llm_calls": total_llm,
        "total_legal_moves": total_legal,
        "total_fallback_moves": total_fallback,
        "legal_move_rate": round(total_legal / total_llm, 4) if total_llm > 0 else 0,
        "unique_moves": len(set(r["extracted_move"] for r in all_records if r["extracted_move"])),
        "average_centipawn_loss": mean_acpl,
        "fast_path_hits": fast_path_hits if config.speculative else None,
        "fast_path_hit_rate": round(fast_path_hits / total_llm, 4) if (config.speculative and total_llm > 0) else None,
        "speculative_fallbacks": speculative_fallbacks if config.speculative else None,
        "latency_mean_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0,
        "latency_median_ms": round(sorted(latencies)[len(latencies) // 2], 1) if latencies else 0,
        "latency_min_ms": min(latencies) if latencies else 0,
        "latency_max_ms": max(latencies) if latencies else 0,
        "game_results": game_results,
    }

    # ── Write metrics ────────────────────────────────────
    metrics_path = os.path.join(run_dir, "metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)

    # ── Write game_results.json (Detailed Telemetry) ────
    results_path = os.path.join(run_dir, "game_results.json")
    game_results_payload = {
        "run_id": config.run_id,
        "mode": config.mode,
        "summary": metrics,
        "moves": [
            {
                "game_id": r.get("game_id"),
                "turn_number": r.get("turn_number"),
                "mode": r.get("mode"),
                "turn_latency_ms": r.get("turn_latency_ms"),
                "move_legality": r.get("move_legality"),
                "prompt_tokens": r.get("prompt_tokens"),
                "generation_tokens": r.get("generation_tokens"),
                "cpl_stockfish": r.get("cpl_stockfish"),
                "played_move": r.get("played_move"),
                "fen": r.get("fen"),
            }
            for r in all_records
        ],
    }
    with open(results_path, "w") as f:
        json.dump(game_results_payload, f, indent=2)

    # ── Write manifest ───────────────────────────────────
    manifest = {
        "schema_version": "1.0",
        "run_id": config.run_id,
        "tag": config.tag,
        "started_at": all_records[0]["timestamp"] if all_records else "",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "ollama_mode": detect_ollama_mode(config.ollama_base_url),
        "config": config.to_dict(),
        "summary": {
            "total_games": config.num_games,
            "legal_move_rate": metrics["legal_move_rate"],
            "unique_moves": metrics["unique_moves"],
            "average_centipawn_loss": mean_acpl,
            "latency_mean_ms": metrics["latency_mean_ms"],
        },
    }
    manifest_path = os.path.join(run_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    # ── Summary ──────────────────────────────────────────
    print(f"\n{'=' * 60}")
    print(f"  Run Complete: {config.run_id}")
    print(f"{'=' * 60}")
    print(f"  Games:           {config.num_games}")
    print(f"  LLM Calls:       {total_llm}")
    print(f"  Legal Moves:     {total_legal} ({metrics['legal_move_rate']*100:.1f}%)")
    print(f"  Fallback Moves:  {total_fallback}")
    print(f"  Unique Moves:    {metrics['unique_moves']}")
    if config.eval_acpl and all_cpls:
        print(f"  Mean ACPL:       {mean_acpl} cp")
    if config.speculative:
        print(f"  Fast-Path Hits:  {fast_path_hits}/{total_llm} ({metrics['fast_path_hit_rate']*100:.1f}%)")
        print(f"  Slow Fallbacks:  {speculative_fallbacks}")
    if latencies:
        print(f"  Latency (mean):  {metrics['latency_mean_ms']} ms")
        print(f"  Latency (med):   {metrics['latency_median_ms']} ms")
    print(f"\n  Outputs saved to: {run_dir}/")
    print(f"    config.resolved.json")
    print(f"    manifest.json")
    print(f"    metrics.json")
    print(f"    raw_outputs.jsonl")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    config, skip_preflight = RunConfig.from_cli()
    run(config, skip_preflight)
