import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.run_config import RunConfig


class TestRunConfig(unittest.TestCase):
    def test_default_config(self):
        config = RunConfig()
        config.validate()
        self.assertEqual(config.model, "llama3")
        self.assertEqual(config.temperature, 0.8)
        self.assertTrue(config.constrained_decoding)
        self.assertEqual(config.engine_mode, "python")

    def test_invalid_temperature(self):
        config = RunConfig(temperature=3.5)
        with self.assertRaises(ValueError):
            config.validate()

    def test_invalid_engine_mode(self):
        config = RunConfig(engine_mode="invalid_mode")
        with self.assertRaises(ValueError):
            config.validate()

    def test_serialization(self):
        config = RunConfig(temperature=0.2, constrained_decoding=False, num_games=10)
        d = config.to_dict()
        self.assertEqual(d["temperature"], 0.2)
        self.assertFalse(d["constrained_decoding"])
        
        restored = RunConfig.from_dict(d)
        self.assertEqual(restored.temperature, 0.2)
        self.assertFalse(restored.constrained_decoding)
        self.assertEqual(restored.num_games, 10)


if __name__ == "__main__":
    unittest.main()
