import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENGINE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Source", "vice")


class TestCEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ensure binary exists
        if not os.path.exists(ENGINE_PATH):
            source_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Source")
            subprocess.run(["make"], cwd=source_dir, check=True)

    def test_engine_binary_exists(self):
        self.assertTrue(os.path.exists(ENGINE_PATH))

    def test_uci_handshake(self):
        p = subprocess.Popen(
            [ENGINE_PATH],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, _ = p.communicate(input="uci\nisready\nquit\n", timeout=5)
        self.assertIn("id name", stdout)
        self.assertIn("uciok", stdout)
        self.assertIn("readyok", stdout)
        self.assertIn("option name LLM_Model", stdout)
        self.assertIn("option name LLM_Url", stdout)
        self.assertIn("option name LLM_Temperature", stdout)
        self.assertIn("option name LLM_Constrained", stdout)

    def test_classical_search_fallback(self):
        # Disable LLM and test fast classical alpha-beta move generation
        commands = (
            "uci\n"
            "setoption name LLM_Enabled value false\n"
            "isready\n"
            "position startpos\n"
            "go depth 3\n"
            "quit\n"
        )
        p = subprocess.Popen(
            [ENGINE_PATH],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, _ = p.communicate(input=commands, timeout=5)
        self.assertIn("bestmove", stdout)


if __name__ == "__main__":
    unittest.main()
