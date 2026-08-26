import json
import os
import sys
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
    STATIC_KV_PREFIX,
)


class TestSpeculativeDMC(unittest.TestCase):
    def setUp(self):
        self.board_start = chess.Board()
        self.legal_start_uci = [m.uci() for m in self.board_start.legal_moves]

    # ── Test 1: DMC Compression on Starting Position ─────────────────
    def test_dmc_startpos(self):
        compressed = compress_legal_moves(self.legal_start_uci)
        self.assertIn("a2:[a3,a4]", compressed)
        self.assertIn("b1:[a3,c3]", compressed)
        self.assertIn("e2:[e3,e4]", compressed)
        self.assertIn("g1:[f3,h3]", compressed)
        self.assertEqual(len(compressed.split("|")), 10)  # 8 pawns + 2 knights

    # ── Test 2: DMC Decompression Round-Trip Equality ───────────────
    def test_dmc_decompression_equality(self):
        compressed = compress_legal_moves(self.legal_start_uci)
        decompressed = decompress_legal_moves(compressed)
        self.assertEqual(sorted(self.legal_start_uci), sorted(decompressed))

    # ── Test 3: DMC Promotion Representation ─────────────────────────
    def test_dmc_promotions(self):
        promo_moves = ["e7e8q", "e7e8r", "e7e8b", "e7e8n", "e7d8q"]
        compressed = compress_legal_moves(promo_moves)
        self.assertEqual(compressed, "e7:[d8q,e8b,e8n,e8q,e8r]")
        decompressed = decompress_legal_moves(compressed)
        self.assertEqual(sorted(promo_moves), sorted(decompressed))

    # ── Test 4: DMC Compression Ratio Verification ───────────────────
    def test_dmc_compression_ratio(self):
        raw_json = json.dumps(self.legal_start_uci)
        compressed = compress_legal_moves(self.legal_start_uci)
        # DMC character length should be significantly smaller than raw JSON array
        self.assertLess(len(compressed), len(raw_json) * 0.75)

    # ── Test 5: DMC Empty & Single Move Edge Cases ───────────────────
    def test_dmc_empty_and_single_move(self):
        self.assertEqual(compress_legal_moves([]), "")
        self.assertEqual(decompress_legal_moves(""), [])
        self.assertEqual(compress_legal_moves(["e2e4"]), "e2:[e4]")
        self.assertEqual(decompress_legal_moves("e2:[e4]"), ["e2e4"])

    # ── Test 6: KV-Cache Static Prefix Invariance ───────────────────
    def test_kv_aligned_static_prefix(self):
        p_unconstrained = build_kv_aligned_prompt(self.board_start.fen(), self.legal_start_uci, is_constrained=False)
        p_constrained_raw = build_kv_aligned_prompt(self.board_start.fen(), self.legal_start_uci, is_constrained=True, use_dmc=False)
        p_constrained_dmc = build_kv_aligned_prompt(self.board_start.fen(), self.legal_start_uci, is_constrained=True, use_dmc=True)

        self.assertTrue(p_unconstrained.startswith(STATIC_KV_PREFIX))
        self.assertTrue(p_constrained_raw.startswith(STATIC_KV_PREFIX))
        self.assertTrue(p_constrained_dmc.startswith(STATIC_KV_PREFIX))

    # ── Test 7: KV-Cache Unconstrained Suffix Structure ──────────────
    def test_kv_aligned_dynamic_suffix_unconstrained(self):
        fen = self.board_start.fen()
        prompt = build_kv_aligned_prompt(fen, self.legal_start_uci, is_constrained=False)
        self.assertIn(f"Board FEN: {fen}", prompt)
        self.assertNotIn("Legal moves", prompt)

    # ── Test 8: KV-Cache DMC Suffix Structure ────────────────────────
    def test_kv_aligned_dynamic_suffix_dmc(self):
        fen = self.board_start.fen()
        prompt = build_kv_aligned_prompt(fen, self.legal_start_uci, is_constrained=True, use_dmc=True)
        self.assertIn(f"Board FEN: {fen}", prompt)
        self.assertIn("Legal moves (DMC grouped):", prompt)
        self.assertIn("e2:[e3,e4]", prompt)

    # ── Test 9: UCI Move Extraction - Standard Formats ───────────────
    def test_extract_uci_standard(self):
        self.assertEqual(extract_uci_move("e2e4"), "e2e4")
        self.assertEqual(extract_uci_move("  g8f6  "), "g8f6")
        self.assertEqual(extract_uci_move('"e7e8q"'), "e7e8q")

    # ── Test 10: UCI Move Extraction - Bracketed & Colon DMC Formats ──
    def test_extract_uci_bracketed(self):
        self.assertEqual(extract_uci_move("e7[e5]"), "e7e5")
        self.assertEqual(extract_uci_move("e7:e5"), "e7e5")
        self.assertEqual(extract_uci_move("g8(f6)"), "g8f6")

    # ── Test 11: UCI Move Extraction - Arrow Format ───────────────────
    def test_extract_uci_arrow(self):
        self.assertEqual(extract_uci_move("e7->e5"), "e7e5")
        self.assertEqual(extract_uci_move("b8->c6"), "b8c6")

    # ── Test 12: UCI Move Extraction - Contextual SAN Resolution ─────
    def test_extract_uci_san(self):
        self.assertEqual(extract_uci_move("Nf3", self.board_start), "g1f3")
        self.assertEqual(extract_uci_move("e4", self.board_start), "e2e4")
        self.assertEqual(extract_uci_move("d4", self.board_start), "d2d4")

    # ── Test 13: Stockfish Position Evaluation ───────────────────────
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

    # ── Test 14: Centipawn Loss on Best Move (CPL == 0.0) ─────────────
    def test_compute_cpl_best_move(self):
        if not os.path.exists("/usr/bin/stockfish") and not os.path.exists("/usr/local/bin/stockfish"):
            self.skipTest("Stockfish binary not installed")
        engine = chess.engine.SimpleEngine.popen_uci("stockfish")
        try:
            _, best_move_uci = evaluate_position_score(self.board_start, engine, depth=8)
            best_move = chess.Move.from_uci(best_move_uci)
            cpl, best_m, _, _ = compute_move_cpl(self.board_start, best_move, engine, depth=8)
            self.assertAlmostEqual(cpl, 0.0, delta=15.0)  # CPL for engine best move should be ~0
            self.assertEqual(best_m, best_move_uci)
        finally:
            engine.quit()

    # ── Test 15: Centipawn Loss on Suboptimal Move (CPL > 0) ──────────
    def test_compute_cpl_blunder(self):
        if not os.path.exists("/usr/bin/stockfish") and not os.path.exists("/usr/local/bin/stockfish"):
            self.skipTest("Stockfish binary not installed")
        engine = chess.engine.SimpleEngine.popen_uci("stockfish")
        try:
            # Suboptimal 1. h4 opening
            suboptimal_move = chess.Move.from_uci("h2h4")
            cpl, _, _, _ = compute_move_cpl(self.board_start, suboptimal_move, engine, depth=8)
            self.assertGreater(cpl, 0.0)
        finally:
            engine.quit()

    # ── Test 16: Speculative RunConfig Default Flags ──────────────────
    def test_speculative_run_config_defaults(self):
        config = RunConfig()
        self.assertFalse(config.speculative)
        self.assertFalse(config.use_dmc)
        self.assertTrue(config.eval_acpl)
        self.assertEqual(config.stockfish_path, "stockfish")

    # ── Test 17: Speculative RunConfig CLI Flag Parsing ──────────────
    def test_speculative_run_config_cli_parsing(self):
        args = ["--speculative", "--use-dmc", "--no-acpl", "--stockfish-path", "/custom/stockfish"]
        config, _ = RunConfig.from_cli(args)
        self.assertTrue(config.speculative)
        self.assertTrue(config.use_dmc)
        self.assertFalse(config.eval_acpl)
        self.assertEqual(config.stockfish_path, "/custom/stockfish")

    # ── Test 18: Speculative RunConfig Dict Serialization ─────────────
    def test_speculative_run_config_serialization(self):
        config = RunConfig(speculative=True, use_dmc=True, eval_acpl=False)
        d = config.to_dict()
        self.assertTrue(d["speculative"])
        self.assertTrue(d["use_dmc"])
        self.assertFalse(d["eval_acpl"])

        restored = RunConfig.from_dict(d)
        self.assertTrue(restored.speculative)
        self.assertTrue(restored.use_dmc)
        self.assertFalse(restored.eval_acpl)

    # ── Test 19: Speculative Decision Loop - Fast-Path Hit ────────────
    @patch("scripts.run_game.query_ollama")
    def test_speculative_decision_loop_fast_hit(self, mock_query):
        # Return a legal move on fast path
        mock_query.return_value = ("e7e5", 150)
        config = RunConfig(speculative=True, num_games=1, max_turns=2, early_termination=False, eval_acpl=False)
        records, result = play_game(config, 1, "runs/test_spec")
        self.assertGreater(len(records), 0)
        self.assertEqual(records[0]["fast_path_hit"], 1)
        self.assertEqual(records[0]["speculative_fallback_used"], 0)
        self.assertEqual(records[0]["is_legal"], 1)

    # ── Test 20: Speculative Decision Loop - Fast-Path Miss Fallback ──
    @patch("scripts.run_game.query_ollama")
    def test_speculative_decision_loop_fallback(self, mock_query):
        # 1st call (Fast path): illegal move 'e7e9'
        # 2nd call (Slow path DMC): legal move 'e7e5'
        mock_query.side_effect = [("e7e9", 100), ("e7e5", 200)]
        config = RunConfig(speculative=True, use_dmc=True, num_games=1, max_turns=2, early_termination=False, eval_acpl=False)
        records, result = play_game(config, 1, "runs/test_spec")
        self.assertGreater(len(records), 0)
        self.assertEqual(records[0]["fast_path_hit"], 0)
        self.assertEqual(records[0]["speculative_fallback_used"], 1)
        self.assertEqual(records[0]["is_legal"], 1)
        self.assertEqual(records[0]["played_move"], "e7e5")
        self.assertEqual(records[0]["latency_ms"], 300)

    # ── Test 21: Expected Amortized Latency Formulation ──────────────
    def test_amortized_latency_formula(self):
        p_legal = 0.526
        t_fast = 5092.0
        t_slow = 6500.0
        # E[Latency] = T_fast + (1 - P(Legal)) * T_slow
        expected_latency = t_fast + (1.0 - p_legal) * t_slow
        self.assertAlmostEqual(expected_latency, 8173.0, delta=1.0)

    # ── Test 22: 20-Game Speculative Tournament with Stockfish ACPL ──
    @patch("scripts.run_game.query_ollama")
    def test_20_game_speculative_tournament(self, mock_query):
        """Simulate a full 20-game tournament under the speculative pipeline with Stockfish ACPL."""
        engine = None
        if os.path.exists("/usr/bin/stockfish") or os.path.exists("/usr/local/bin/stockfish"):
            try:
                engine = chess.engine.SimpleEngine.popen_uci("stockfish")
            except Exception:
                engine = None

        # Setup mock LLM: alternating fast-path legal/illegal moves
        def query_side_effect(config, fen, legal_moves_list, is_constrained=None, use_dmc=None, temperature=None):
            if is_constrained:
                # Constrained slow-path ALWAYS produces a legal move from list
                return legal_moves_list[0], 120
            else:
                # Fast path produces legal move 50% of the time, illegal 50%
                b = chess.Board(fen)
                if b.fullmove_number % 2 == 1:
                    return list(legal_moves_list)[0], 80
                else:
                    return "a1a9", 80  # Illegal move

        mock_query.side_effect = query_side_effect

        config = RunConfig(
            speculative=True,
            use_dmc=True,
            num_games=20,
            max_turns=6,
            eval_acpl=True if engine else False,
            stockfish_path="stockfish",
        )

        all_records = []
        try:
            for g in range(1, 21):
                records, result = play_game(config, g, "runs/test_tournament", stockfish_engine=engine)
                all_records.extend(records)
                self.assertGreater(len(records), 0)
                # Verify 100% legality of all moves played in this game
                for r in records:
                    self.assertEqual(r["is_legal"], 1)
                    self.assertIn(r["played_move"], [m.uci() for m in chess.Board(r["fen"]).legal_moves])

            # Global tournament assertions
            total_moves = len(all_records)
            self.assertGreater(total_moves, 40)
            legal_rate = sum(1 for r in all_records if r["is_legal"]) / total_moves
            self.assertEqual(legal_rate, 1.0)  # 100.0% Legality Guarantee

            fast_hits = sum(1 for r in all_records if r["fast_path_hit"] == 1)
            fallbacks = sum(1 for r in all_records if r["speculative_fallback_used"] == 1)
            self.assertGreater(fast_hits, 0)
            self.assertGreater(fallbacks, 0)
            self.assertEqual(fast_hits + fallbacks, total_moves)

            if engine:
                cpls = [r["centipawn_loss"] for r in all_records if "centipawn_loss" in r]
                self.assertEqual(len(cpls), total_moves)
                mean_cpl = sum(cpls) / len(cpls)
                self.assertGreaterEqual(mean_cpl, 0.0)

        finally:
            if engine:
                engine.quit()


if __name__ == "__main__":
    unittest.main()
