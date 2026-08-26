import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from web.app import app


class TestWebAPI(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_index_page(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"LLM Chess Engine", resp.data)

    def test_research_page(self):
        resp = self.client.get("/research")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Research Data", resp.data)

    def test_new_game_api(self):
        resp = self.client.post("/api/new-game")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("game_id", data)
        self.assertIn("fen", data)
        self.assertEqual(data["turn"], "white")
        self.assertFalse(data["is_game_over"])

    def test_make_move_and_engine_move(self):
        # 1. Start game
        resp = self.client.post("/api/new-game")
        game_id = resp.get_json()["game_id"]

        # 2. Make white move e2e4
        move_resp = self.client.post(
            "/api/move",
            data=json.dumps({"game_id": game_id, "move": "e2e4"}),
            content_type="application/json"
        )
        self.assertEqual(move_resp.status_code, 200)
        data = move_resp.get_json()
        self.assertEqual(data["turn"], "black")

        # 3. Engine move
        eng_resp = self.client.post(
            "/api/engine-move",
            data=json.dumps({"game_id": game_id}),
            content_type="application/json"
        )
        self.assertEqual(eng_resp.status_code, 200)
        eng_data = eng_resp.get_json()
        self.assertIn("engine_move", eng_data)
        self.assertEqual(eng_data["turn"], "white")

    def test_stateless_fen_move(self):
        # Test making a move on a non-existent game_id by providing FEN
        custom_fen = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
        resp = self.client.post(
            "/api/move",
            data=json.dumps({"game_id": "nonexistent", "move": "e7e5", "fen": custom_fen}),
            content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["turn"], "white")

    def test_research_stats_api(self):
        resp = self.client.get("/api/research-stats")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("total_calls", data)
        self.assertIn("success_rate", data)
        self.assertIn("conditions", data)


if __name__ == "__main__":
    unittest.main()
