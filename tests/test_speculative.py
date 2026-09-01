import json
import os
import sys
import time
import unittest
from unittest.mock import patch, MagicMock
import chess
import chess.engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.run_config import RunConfig
from scripts.run_game import (
    compress_legal_moves,
    decompress_legal_moves,
    build_kv_aligned_prompt,
    extract_uci_move,
    evaluate_position_score,
    compute_move_cpl,
    play_game,
    run,
    STATIC_KV_PREFIX,
)


class TestSpeculativeDMC(unittest.TestCase):
    def setUp(self):
        self.board_start = chess.Board()
        self.legal_start_uci = [m.uci() for m in self.board_start.legal_moves]

    # ── Test 1: Start Position Legal Moves Compression ──────────────
    def test_dmc_startpos(self):
        compressed = compress_legal_moves(self.legal_start_uci)
        self.assertIn("e2e4", compressed)
        self.assertIn("g1f3", compressed)
        self.assertEqual(len(compressed.split()), 20)

    # ── Test 2: DMC Decompression Roundtrip Equality ─────────────────
    def test_dmc_decompression_equality(self):
        compressed = compress_legal_moves(self.legal_start_uci)
        decompressed = decompress_legal_moves(compressed)
        self.assertEqual(sorted(self.legal_start_uci), sorted(decompressed))

    # ── Test 3: DMC Direct Board Object Support ───────────────────────
    def test_dmc_board_object_support(self):
        compressed_from_board = compress_legal_moves(self.board_start)
        compressed_from_list = compress_legal_moves(self.legal_start_uci)
        self.assertEqual(compressed_from_board, compressed_from_list)

    # ── Test 4: DMC Speed Sub-Millisecond Benchmark (<1ms) ───────────
    def test_dmc_speed_sub_millisecond(self):
        # Benchmark 1000 calls on complex midgame positions
        complex_fen = "r1bqk2r/pp1n1ppp/2p1pn2/3p4/2PP4/2NBPN2/PP3PPP/R1BQK2R w KQkq - 0 7"
        board = chess.Board(complex_fen)
        start_t = time.perf_counter()
        iters = 1000
        for _ in range(iters):
            _ = compress_legal_moves(board)
        elapsed_total = time.perf_counter() - start_t
        avg_ms_per_call = (elapsed_total / iters) * 1000
        self.assertLess(avg_ms_per_call, 1.0, f"DMC compression took {avg_ms_per_call:.3f}ms (must be <1ms)")

    # ── Test 5: DMC Promotion Representation ─────────────────────────
    def test_dmc_promotions(self):
        promo_moves = ["e7e8q", "e7e8r", "e7e8b", "e7e8n", "e7d8q"]
        compressed = compress_legal_moves(promo_moves)
        self.assertEqual(compressed, "e7d8q e7e8b e7e8n e7e8q e7e8r")
        decompressed = decompress_legal_moves(compressed)
        self.assertEqual(sorted(promo_moves), sorted(decompressed))

    # ── Test 6: DMC Compression Ratio Verification ───────────────────
    def test_dmc_compression_ratio(self):
        raw_json = json.dumps(self.legal_start_uci)
        compressed = compress_legal_moves(self.legal_start_uci)
        self.assertLess(len(compressed), len(raw_json) * 0.75)

    # ── Test 7: DMC Empty & Single Move Edge Cases ───────────────────
    def test_dmc_empty_and_single_move(self):
        self.assertEqual(compress_legal_moves([]), "")
        self.assertEqual(decompress_legal_moves(""), [])
        self.assertEqual(compress_legal_moves(["e2e4"]), "e2e4")
        self.assertEqual(decompress_legal_moves("e2e4"), ["e2e4"])

    # ── Test 8: KV-Cache Static Prefix Invariance ───────────────────
    def test_kv_aligned_static_prefix(self):
        p_unconstrained = build_kv_aligned_prompt(self.board_start.fen(), self.legal_start_uci, is_constrained=False)
        p_constrained_raw = build_kv_aligned_prompt(self.board_start.fen(), self.legal_start_uci, is_constrained=True, use_dmc=False)
        p_constrained_dmc = build_kv_aligned_prompt(self.board_start.fen(), self.legal_start_uci, is_constrained=True, use_dmc=True)

        self.assertTrue(p_unconstrained.startswith(STATIC_KV_PREFIX))
        self.assertTrue(p_constrained_raw.startswith(STATIC_KV_PREFIX))
        self.assertTrue(p_constrained_dmc.startswith(STATIC_KV_PREFIX))

    # ── Test 9: KV-Cache Unconstrained Suffix Structure ──────────────
    def test_kv_aligned_dynamic_suffix_unconstrained(self):
        fen = self.board_start.fen()
        prompt = build_kv_aligned_prompt(fen, self.legal_start_uci, is_constrained=False)
        self.assertIn(f"Board FEN: {fen}", prompt)
        self.assertNotIn("Legal moves", prompt)

    # ── Test 10: KV-Cache DMC Suffix Structure ───────────────────────
    def test_kv_aligned_dynamic_suffix_dmc(self):
        fen = self.board_start.fen()
        prompt = build_kv_aligned_prompt(fen, self.legal_start_uci, is_constrained=True, use_dmc=True)
        self.assertIn(f"Board FEN: {fen}", prompt)
        self.assertIn("Legal moves: a2a3", prompt)
        self.assertIn("e2e4", prompt)

    # ── Test 11: UCI Move Extraction - Standard Formats ──────────────
    def test_extract_uci_standard(self):
        self.assertEqual(extract_uci_move("e2e4"), "e2e4")
        self.assertEqual(extract_uci_move("  g8f6  "), "g8f6")
        self.assertEqual(extract_uci_move('"e7e8q"'), "e7e8q")

    # ── Test 12: UCI Move Extraction - Bracketed & Colon DMC Formats ─
    def test_extract_uci_bracketed(self):
        self.assertEqual(extract_uci_move("e7[e5]"), "e7e5")
        self.assertEqual(extract_uci_move("e7:e5"), "e7e5")
        self.assertEqual(extract_uci_move("g8(f6)"), "g8f6")

    # ── Test 13: UCI Move Extraction - Arrow Format ──────────────────
    def test_extract_uci_arrow(self):
        self.assertEqual(extract_uci_move("e7->e5"), "e7e5")
        self.assertEqual(extract_uci_move("b8->c6"), "b8c6")

    # ── Test 14: UCI Move Extraction - Contextual SAN Resolution ────
    def test_extract_uci_san(self):
        self.assertEqual(extract_uci_move("Nf3", self.board_start), "g1f3")
        self.assertEqual(extract_uci_move("e4", self.board_start), "e2e4")
        self.assertEqual(extract_uci_move("d4", self.board_start), "d2d4")

    # ── Test 15: Stockfish Position Evaluation ───────────────────────
    def test_stockfish_position_eval(self):
        if not os.path.exists("/usr/bin/stockfish") and not os.path.exists("/usr/local/bin/stockfish"):
            self.skipTest("Stockfish binary not installed")
        engine = chess.engine.SimpleEngine.popen_uci("stockfish")
        try:
            score, best_move = evaluate_position_score(self.board_start, engine, depth=5)
            self.assertIsInstance(score, float)
            self.assertIn(best_move, self.legal_start_uci)
        finally:
            engine.quit()

    # ── Test 16: Centipawn Loss on Best Move (CPL == 0.0) ────────────
    def test_compute_cpl_best_move(self):
        if not os.path.exists("/usr/bin/stockfish") and not os.path.exists("/usr/local/bin/stockfish"):
            self.skipTest("Stockfish binary not installed")
        engine = chess.engine.SimpleEngine.popen_uci("stockfish")
        try:
            _, best_move_uci = evaluate_position_score(self.board_start, engine, depth=8)
            best_move = chess.Move.from_uci(best_move_uci)
            cpl, best_m, _, _ = compute_move_cpl(self.board_start, best_move, engine, depth=8)
            self.assertAlmostEqual(cpl, 0.0, delta=15.0)
            self.assertEqual(best_m, best_move_uci)
        finally:
            engine.quit()

    # ── Test 17: Centipawn Loss on Suboptimal Move (CPL > 0) ─────────
    def test_compute_cpl_blunder(self):
        if not os.path.exists("/usr/bin/stockfish") and not os.path.exists("/usr/local/bin/stockfish"):
            self.skipTest("Stockfish binary not installed")
        engine = chess.engine.SimpleEngine.popen_uci("stockfish")
        try:
            suboptimal_move = chess.Move.from_uci("h2h4")
            cpl, _, _, _ = compute_move_cpl(self.board_start, suboptimal_move, engine, depth=8)
            self.assertGreater(cpl, 0.0)
        finally:
            engine.quit()

    # ── Test 18: Single-Stage Default Mode in RunConfig ──────────────
    def test_single_stage_default_mode(self):
        config = RunConfig()
        self.assertEqual(config.mode, "single-stage")
        self.assertTrue(config.use_dmc)
        self.assertFalse(config.speculative)
        self.assertTrue(config.eval_acpl)
        self.assertEqual(config.stockfish_path, "stockfish")

    # ── Test 19: Mode CLI Flag Parsing ───────────────────────────────
    def test_mode_cli_parsing(self):
        # Default single-stage
        config1, _ = RunConfig.from_cli([])
        self.assertEqual(config1.mode, "single-stage")
        self.assertTrue(config1.use_dmc)
        self.assertFalse(config1.speculative)

        # Ablation speculative mode
        config2, _ = RunConfig.from_cli(["--mode", "ablation-speculative"])
        self.assertEqual(config2.mode, "ablation-speculative")
        self.assertTrue(config2.speculative)

        # Unconstrained mode
        config3, _ = RunConfig.from_cli(["--mode", "unconstrained"])
        self.assertEqual(config3.mode, "unconstrained")
        self.assertFalse(config3.constrained_decoding)

    # ── Test 20: Primary Execution Path: Single-Stage DMC ────────────
    @patch("scripts.run_game.query_ollama")
    def test_primary_single_stage_dmc_execution(self, mock_query):
        mock_query.return_value = ("e7e5", 140, 48, 5)
        config = RunConfig(mode="single-stage", num_games=1, max_turns=2, eval_acpl=False)
        records, result = play_game(config, 1, "runs/test_single_stage")

        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["mode"], "single-stage-dmc")
        self.assertEqual(rec["played_move"], "e7e5")
        self.assertTrue(rec["move_legality"])
        self.assertEqual(rec["prompt_tokens"], 48)
        self.assertEqual(rec["generation_tokens"], 5)
        self.assertEqual(mock_query.call_count, 1)  # Strictly 1 API call per turn

    # ── Test 21: Ablation Speculative Sequential Retry Path ──────────
    @patch("scripts.run_game.query_ollama")
    def test_ablation_speculative_retry_path(self, mock_query):
        # Call 1: Fast path illegal move 'e7e9'
        # Call 2: Slow path DMC fallback legal move 'e7e5'
        mock_query.side_effect = [("e7e9", 80, 20, 4), ("e7e5", 150, 45, 5)]
        config = RunConfig(mode="ablation-speculative", num_games=1, max_turns=2, eval_acpl=False)
        records, result = play_game(config, 1, "runs/test_ablation")

        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["mode"], "ablation-speculative")
        self.assertEqual(rec["fast_path_hit"], 0)
        self.assertEqual(rec["speculative_fallback_used"], 1)
        self.assertTrue(rec["move_legality"])
        self.assertEqual(rec["played_move"], "e7e5")
        self.assertEqual(rec["prompt_tokens"], 65)  # 20 + 45
        self.assertEqual(rec["generation_tokens"], 9)  # 4 + 5
        self.assertEqual(mock_query.call_count, 2)  # Two sequential calls

    # ── Test 22: game_results.json Persistence & Telemetry Structure ──
    @patch("scripts.run_game.query_ollama")
    def test_game_results_json_persistence(self, mock_query):
        mock_query.return_value = ("e7e5", 110, 42, 4)
        config = RunConfig(mode="single-stage", num_games=1, max_turns=2, eval_acpl=False)
        run_dir = os.path.join("runs", config.run_id)
        
        run(config, skip_preflight=True)

        results_file = os.path.join(run_dir, "game_results.json")
        self.assertTrue(os.path.isfile(results_file))

        with open(results_file) as f:
            data = json.load(f)

        self.assertEqual(data["mode"], "single-stage")
        self.assertIn("moves", data)
        self.assertGreater(len(data["moves"]), 0)
        move_entry = data["moves"][0]
        self.assertEqual(move_entry["mode"], "single-stage-dmc")
        self.assertTrue(move_entry["move_legality"])
        self.assertIn("turn_latency_ms", move_entry)
        self.assertIn("prompt_tokens", move_entry)
        self.assertIn("generation_tokens", move_entry)

    # ── Test 23: 20-Game Single-Stage Tournament with Stockfish ACPL ──
    @patch("scripts.run_game.query_ollama")
    def test_20_game_single_stage_tournament(self, mock_query):
        engine = None
        if os.path.exists("/usr/bin/stockfish") or os.path.exists("/usr/local/bin/stockfish"):
            try:
                engine = chess.engine.SimpleEngine.popen_uci("stockfish")
            except Exception:
                engine = None

        # Return legal move from compressed list
        def query_side_effect(config, fen, legal_moves_list, is_constrained=None, use_dmc=None, temperature=None):
            return legal_moves_list[0], 90, 45, 4

        mock_query.side_effect = query_side_effect

        config = RunConfig(
            mode="single-stage",
            num_games=20,
            max_turns=6,
            eval_acpl=True if engine else False,
            stockfish_path="stockfish",
        )

        all_records = []
        try:
            for g in range(1, 21):
                records, result = play_game(config, g, "runs/test_single_stage_tourney", stockfish_engine=engine)
                all_records.extend(records)
                for r in records:
                    self.assertEqual(r["mode"], "single-stage-dmc")
                    self.assertTrue(r["move_legality"])
                    self.assertEqual(r["is_legal"], 1)

            total_moves = len(all_records)
            self.assertGreater(total_moves, 40)
            self.assertEqual(sum(1 for r in all_records if r["is_legal"]), total_moves)
        finally:
            if engine:
                engine.quit()


if __name__ == "__main__":
    unittest.main()
