import os
import sys
import unittest
import chess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.run_game import extract_uci_move


class TestUCIParser(unittest.TestCase):
    def test_clean_coordinate_move(self):
        self.assertEqual(extract_uci_move("e2e4"), "e2e4")
        self.assertEqual(extract_uci_move("g8f6"), "g8f6")
        self.assertEqual(extract_uci_move("e7e8q"), "e7e8q")

    def test_wrapped_move(self):
        self.assertEqual(extract_uci_move('"e2e4"'), "e2e4")
        self.assertEqual(extract_uci_move('[e7e5]'), "e7e5")
        self.assertEqual(extract_uci_move('Move: (g8f6)'), "g8f6")

    def test_prefixed_and_hyphenated_move(self):
        self.assertEqual(extract_uci_move("Nb8c6"), "b8c6")
        self.assertEqual(extract_uci_move("e2-e4"), "e2e4")
        self.assertEqual(extract_uci_move("b8xc6"), "b8c6")

    def test_san_with_board(self):
        board = chess.Board()
        # White opening moves
        self.assertEqual(extract_uci_move("Nf3", board), "g1f3")
        self.assertEqual(extract_uci_move("e4", board), "e2e4")
        self.assertEqual(extract_uci_move("d4", board), "d2d4")

    def test_invalid_text(self):
        self.assertEqual(extract_uci_move("I cannot make a move."), "")
        self.assertEqual(extract_uci_move(""), "")


if __name__ == "__main__":
    unittest.main()
