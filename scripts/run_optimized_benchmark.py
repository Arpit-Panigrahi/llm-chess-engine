import os
import sys
import time
import json
import csv
import random
import chess
import chess.engine
import requests
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.run_config import RunConfig
from scripts.run_game import (
    compress_legal_moves,
    build_kv_aligned_prompt,
    extract_uci_move,
    query_ollama,
    compute_move_cpl,
    STATIC_KV_PREFIX,
)

def run_optimized_benchmark():
    print("=" * 75, flush=True)
    print("  LLM Chess Engine — Optimized Central-Weighted DMC vs Raw Benchmark", flush=True)
    print("=" * 75, flush=True)

    out_dir = "reports/optimized_dmc_benchmark"
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, "live_moves.csv")

    stockfish_path = "stockfish"
    try:
        sf_engine = chess.engine.SimpleEngine.popen_uci(stockfish_path)
        print("✓ Stockfish 18 Engine initialized for live depth-12 ACPL evaluation.\n", flush=True)
    except Exception as e:
        print(f"✗ Stockfish initialization failed: {e}", flush=True)
        sys.exit(1)

    ollama_url = "http://localhost:11434"
    model_name = "llama3.1"

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "condition", "game_id", "turn_number", "mode", "played_move",
            "move_legality", "turn_latency_ms", "prompt_tokens", "generation_tokens",
            "cpl_stockfish", "best_engine_move", "fen"
        ])
        writer.writeheader()

    seed = 42

    test_conditions = [
        {
            "tag": "t08_optimized_dmc_single_stage",
            "name": "Single-Stage (Central-Weighted Quoted DMC)",
            "num_games": 10,
            "max_turns": 6,
            "temp": 0.8,
            "mode": "single-stage",
            "use_dmc": True,
            "constrained": True,
        },
        {
            "tag": "t08_constrained_raw",
            "name": "Constrained (Raw JSON Array)",
            "num_games": 10,
            "max_turns": 6,
            "temp": 0.8,
            "mode": "single-stage",
            "use_dmc": False,
            "constrained": True,
        },
    ]

    summaries = []

    try:
        for cond_idx, cond in enumerate(test_conditions, 1):
            tag = cond["tag"]
            name = cond["name"]
            num_games = cond["num_games"]
            max_turns = cond["max_turns"]
            temp = cond["temp"]
            mode = cond["mode"]
            use_dmc = cond["use_dmc"]
            is_constrained = cond["constrained"]

            cfg = RunConfig(
                temperature=temp,
                constrained_decoding=is_constrained,
                use_dmc=use_dmc,
                mode=mode,
                model=model_name,
                seed=seed,
                ollama_base_url=ollama_url,
                num_games=num_games,
                max_turns=max_turns,
                eval_acpl=True,
            )

            print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", flush=True)
            print(f"  [{cond_idx}/2] EVALUATING: {name}", flush=True)
            print(f"  Games: {num_games} | Max Turns: {max_turns} | Mode: {mode} | DMC: {use_dmc}", flush=True)
            print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━", flush=True)

            cond_records = []
            cond_start = time.time()

            for g in range(1, num_games + 1):
                board = chess.Board()
                rng = random.Random(seed + g)
                turn_num = 0
                g_start = time.time()

                while not board.is_game_over() and turn_num < max_turns:
                    turn_num += 1

                    if board.turn == chess.WHITE:
                        legal = list(board.legal_moves)
                        board.push(rng.choice(legal))
                    else:
                        fen = board.fen()
                        legal_moves = [m.uci() for m in board.legal_moves]

                        raw_resp, latency_ms, prompt_tokens, generation_tokens = query_ollama(
                            cfg, fen, legal_moves,
                            is_constrained=is_constrained,
                            use_dmc=use_dmc,
                            temperature=temp
                        )
                        uci_str = extract_uci_move(raw_resp, board)

                        is_legal = 0
                        played_move = ""
                        played_move_obj = None

                        if uci_str:
                            try:
                                m_obj = chess.Move.from_uci(uci_str)
                                if m_obj in board.legal_moves:
                                    is_legal = 1
                                    played_move = uci_str
                                    played_move_obj = m_obj
                                    board.push(m_obj)
                                else:
                                    fb_move = rng.choice(list(board.legal_moves))
                                    played_move = fb_move.uci()
                                    played_move_obj = fb_move
                                    board.push(fb_move)
                            except ValueError:
                                fb_move = rng.choice(list(board.legal_moves))
                                played_move = fb_move.uci()
                                played_move_obj = fb_move
                                board.push(fb_move)
                        else:
                            fb_move = rng.choice(list(board.legal_moves))
                            played_move = fb_move.uci()
                            played_move_obj = fb_move
                            board.push(fb_move)

                        cpl = 0.0
                        best_move = ""
                        if is_legal and played_move_obj is not None:
                            cpl, best_move, _, _ = compute_move_cpl(chess.Board(fen), played_move_obj, sf_engine)

                        rec = {
                            "condition": tag,
                            "game_id": g,
                            "turn_number": turn_num,
                            "mode": mode,
                            "played_move": played_move,
                            "move_legality": bool(is_legal),
                            "is_legal": is_legal,
                            "turn_latency_ms": latency_ms,
                            "prompt_tokens": prompt_tokens,
                            "generation_tokens": generation_tokens,
                            "cpl_stockfish": cpl,
                            "best_engine_move": best_move,
                            "fen": fen,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                        cond_records.append(rec)

                        with open(csv_path, "a", newline="") as f_csv:
                            csv_fields = ["condition", "game_id", "turn_number", "mode", "played_move", "move_legality", "turn_latency_ms", "prompt_tokens", "generation_tokens", "cpl_stockfish", "best_engine_move", "fen"]
                            writer = csv.DictWriter(f_csv, fieldnames=csv_fields, extrasaction='ignore')
                            writer.writerow(rec)
                            f_csv.flush()

                g_duration = time.time() - g_start
                g_legal = sum(1 for r in cond_records if r["game_id"] == g and r["is_legal"])
                g_total = sum(1 for r in cond_records if r["game_id"] == g)
                rate = (g_legal / g_total * 100) if g_total else 0
                print(f"  Game {g:2d}/{num_games}: Legal {g_legal}/{g_total} ({rate:.0f}%) | Time: {g_duration:.1f}s", flush=True)

            cond_total_time = time.time() - cond_start
            total_moves = len(cond_records)
            legal_moves = sum(1 for r in cond_records if r["is_legal"])
            legal_rate = (legal_moves / total_moves * 100) if total_moves else 0

            latencies = [r["turn_latency_ms"] for r in cond_records]
            mean_lat = sum(latencies) / len(latencies) if latencies else 0
            p95_lat = sorted(latencies)[int(len(latencies)*0.95)] if latencies else 0

            p_toks = [r["prompt_tokens"] for r in cond_records]
            mean_p_toks = sum(p_toks) / len(p_toks) if p_toks else 0

            cpls = [r["cpl_stockfish"] for r in cond_records if r["is_legal"]]
            mean_acpl = sum(cpls) / len(cpls) if cpls else 0.0

            summary_item = {
                "tag": tag,
                "name": name,
                "total_games": num_games,
                "total_moves": total_moves,
                "legal_moves": legal_moves,
                "legal_rate": round(legal_rate, 2),
                "mean_latency_ms": round(mean_lat, 1),
                "p95_latency_ms": round(p95_lat, 1),
                "mean_prompt_tokens": round(mean_p_toks, 1),
                "acpl": round(mean_acpl, 1),
                "total_time_s": round(cond_total_time, 1),
            }
            summaries.append(summary_item)

            print(f"\n✓ Completed {name} in {cond_total_time/60:.1f} minutes", flush=True)
            print(f"  • Legality: {legal_rate:.1f}% ({legal_moves}/{total_moves})")
            print(f"  • Latency: {mean_lat:.1f} ms (p95: {p95_lat:.1f} ms)")
            print(f"  • Prompt Tokens: {mean_p_toks:.1f} tokens")
            print(f"  • Stockfish ACPL: {mean_acpl:.1f} cp\n", flush=True)

    finally:
        sf_engine.quit()

    summary_csv = os.path.join(out_dir, "metrics_comparison.csv")
    with open(summary_csv, "w", newline="") as f:
        fieldnames = ["tag", "name", "total_games", "total_moves", "legal_moves", "legal_rate", "mean_latency_ms", "p95_latency_ms", "mean_prompt_tokens", "acpl", "total_time_s"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for s in summaries:
            writer.writerow(s)

    print("=" * 75, flush=True)
    print("  ✅ Benchmark Complete! Results saved to: reports/optimized_dmc_benchmark/", flush=True)
    print("=" * 75, flush=True)

if __name__ == "__main__":
    run_optimized_benchmark()
