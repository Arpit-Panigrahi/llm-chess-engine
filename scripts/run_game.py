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

import json
import os
import random
import sys
import time
import traceback
from datetime import datetime, timezone

import chess
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
        model_names = [m.get("name", "").split(":")[0] for m in models]
        if config.model not in model_names and f"{config.model}:latest" not in [m.get("name", "") for m in models]:
            print(f"\n⚠  WARNING: Model '{config.model}' not found in Ollama.")
            print(f"   Available models: {', '.join(m.get('name', '') for m in models) or '(none)'}")
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


def query_ollama(config, fen, legal_moves_list):
    """Send a position to Ollama and get a move response."""
    # Determine side to play
    board = chess.Board(fen)
    side = "White" if board.turn == chess.WHITE else "Black"

    # Build prompt
    if config.constrained_decoding:
        legal_str = json.dumps(legal_moves_list)
        prompt = (
            f"You are a chess engine playing as {side}. "
            f"The current board FEN is: {fen}. "
            f"It is {side}'s turn to move. "
            f"The ONLY legal moves in this position are: {legal_str}. "
            f"You MUST pick exactly one move from that list. "
            f"Respond ONLY with a single 4-character UCI move (e.g., e7e5). "
            f"Do not include any other text, explanations, or formatting."
        )
    else:
        prompt = (
            f"You are a chess engine playing as {side}. "
            f"The current board FEN is: {fen}. "
            f"It is {side}'s turn to move. "
            f"Respond ONLY with a single UCI move in source-destination format "
            f"(e.g., g8f6, e7e5, b8c6, d7d5). "
            f"Do not include piece letters, just the two squares. "
            f"Do not include any other text, explanations, or formatting."
        )

    payload = {
        "model": config.model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": config.temperature,
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
        return raw_response, elapsed_ms
    except requests.Timeout:
        elapsed_ms = int((time.time() - start) * 1000)
        return "", elapsed_ms
    except Exception as e:
        elapsed_ms = int((time.time() - start) * 1000)
        print(f"  ⚠ Ollama error: {e}")
        return "", elapsed_ms


def extract_uci_move(raw_response, board=None):
    """Extract a UCI move (4-5 chars like e2e4, e7e8q) from raw LLM text, with robust SAN/LAN fallbacks."""
    import re
    text = raw_response.strip()

    # 1. Clean up common wrappers (quotes, brackets, periods)
    text = re.sub(r'^["\'\[\(]+|["\'\]\)]+$', '', text)

    # 2. Try exact 4-5 char match first
    if re.match(r'^[a-h][1-8][a-h][1-8][qrbn]?$', text):
        return text

    # 3. Try to find a 4-5 char UCI pattern with optional piece prefix or hyphen/capture symbol
    # e.g., Nb8c6 -> b8c6, e2-e4 -> e2e4, b8xc6 -> b8c6
    match = re.search(r'\b[KQRBN]?[a-h][1-8][-x]?[a-h][1-8][qrbn]?\b', text, re.IGNORECASE)
    if match:
        candidate = match.group(0)
        # Strip piece prefix
        candidate = re.sub(r'^[KQRBNkqrbn]', '', candidate)
        # Strip hyphens and capture symbols
        candidate = candidate.replace('-', '').replace('x', '').replace('X', '')
        if re.match(r'^[a-h][1-8][a-h][1-8][qrbn]?$', candidate):
            return candidate

    # 4. If board is provided, try to resolve Standard Algebraic Notation (SAN) like "Nf6", "e4", "O-O"
    if board is not None:
        # Clean SAN string (remove check/mate/annotations)
        san_clean = re.sub(r'[+#?!]', '', text)
        try:
            move = board.parse_san(san_clean)
            return move.uci()
        except ValueError:
            pass

        # Try to find a match in the legal moves list by matching SAN or UCI substrings
        for move in board.legal_moves:
            uci = move.uci()
            san = board.san(move)
            if san.lower() == san_clean.lower() or uci.lower() in text.lower():
                return uci

    # 5. Fallback to searching for any standard 4-5 char UCI pattern
    match = re.search(r'\b([a-h][1-8][a-h][1-8][qrbn]?)\b', text)
    if match:
        return match.group(1)

    return ""


def play_game(config, game_num, run_dir):
    """Play a single game (White=random, Black=LLM) and return per-move records."""
    board = chess.Board()
    rng = random.Random(config.seed + game_num)
    records = []
    turn_num = 0

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

            raw_response, latency_ms = query_ollama(config, fen, legal_moves)
            uci_str = extract_uci_move(raw_response, board)

            is_legal = 0
            fallback_used = 1
            played_move = ""
            aborted = False

            if uci_str:
                try:
                    move = chess.Move.from_uci(uci_str)
                    if move in board.legal_moves:
                        is_legal = 1
                        fallback_used = 0
                        played_move = uci_str
                        board.push(move)
                    else:
                        if config.early_termination:
                            played_move = uci_str
                            aborted = True
                        else:
                            fallback_move = rng.choice(list(board.legal_moves))
                            played_move = fallback_move.uci()
                            board.push(fallback_move)
                except ValueError:
                    if config.early_termination:
                        played_move = uci_str
                        aborted = True
                    else:
                        fallback_move = rng.choice(list(board.legal_moves))
                        played_move = fallback_move.uci()
                        board.push(fallback_move)
            else:
                if config.early_termination:
                    played_move = ""
                    aborted = True
                else:
                    fallback_move = rng.choice(list(board.legal_moves))
                    played_move = fallback_move.uci()
                    board.push(fallback_move)

            record = {
                "game_id": game_num,
                "turn_number": turn_num,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "fen": fen,
                "temperature": config.temperature,
                "constrained_decoding": config.constrained_decoding,
                "latency_ms": latency_ms,
                "extracted_move": uci_str,
                "played_move": played_move,
                "is_legal": is_legal,
                "fallback_used": fallback_used,
                "raw_response": raw_response,
                "num_legal_moves": len(legal_moves),
            }
            records.append(record)

            if aborted:
                break

    result = "Aborted" if (config.early_termination and any(not r["is_legal"] for r in records)) else (board.result() if board.is_game_over() else "*")
    return records, result


def run(config, skip_preflight=False):
    """Execute the full run: preflight, games, persist artifacts."""

    config.print_banner()

    # ── Preflight ────────────────────────────────────────
    if not skip_preflight:
        print("\n🔍 Running Ollama preflight check...")
        if not check_ollama(config):
            print("\n✗ Preflight failed. Use --skip-preflight to bypass.")
            sys.exit(1)
        print("✓ Ollama is reachable and model is available.\n")
    else:
        print("\n⚡ Skipping preflight check (--skip-preflight)\n")

    # ── Setup run directory ──────────────────────────────
    run_dir = os.path.join("runs", config.run_id)
    os.makedirs(run_dir, exist_ok=True)

    # Persist resolved config
    config_path = os.path.join(run_dir, "config.resolved.json")
    config.save(config_path)

    # ── Play games ───────────────────────────────────────
    all_records = []
    game_results = []
    raw_output_path = os.path.join(run_dir, "raw_outputs.jsonl")

    print(f"Starting {config.num_games} games...\n")

    for game_num in range(1, config.num_games + 1):
        game_start = time.time()
        records, result = play_game(config, game_num, run_dir)
        game_time = time.time() - game_start

        all_records.extend(records)
        game_results.append({"game": game_num, "result": result, "llm_moves": len(records), "duration_s": round(game_time, 1)})

        # Append raw outputs incrementally
        with open(raw_output_path, "a") as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")

        legal = sum(1 for r in records if r["is_legal"])
        total = len(records)
        rate = (legal / total * 100) if total > 0 else 0
        print(f"  Game {game_num:3d}/{config.num_games}: {result:7s}  "
              f"LLM moves: {total:3d}  Legal: {legal}/{total} ({rate:.0f}%)  "
              f"Time: {game_time:.1f}s")

    # ── Compute metrics ──────────────────────────────────
    total_llm = len(all_records)
    total_legal = sum(1 for r in all_records if r["is_legal"])
    total_fallback = sum(1 for r in all_records if r["fallback_used"])
    latencies = [r["latency_ms"] for r in all_records if r["latency_ms"] > 0]

    metrics = {
        "schema_version": "1.0",
        "run_id": config.run_id,
        "tag": config.tag,
        "condition": {
            "temperature": config.temperature,
            "constrained_decoding": config.constrained_decoding,
            "seed": config.seed,
            "model": config.model,
        },
        "total_games": config.num_games,
        "total_llm_calls": total_llm,
        "total_legal_moves": total_legal,
        "total_fallback_moves": total_fallback,
        "legal_move_rate": round(total_legal / total_llm, 4) if total_llm > 0 else 0,
        "unique_moves": len(set(r["extracted_move"] for r in all_records if r["extracted_move"])),
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
