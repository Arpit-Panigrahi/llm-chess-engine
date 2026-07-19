"""
run_config.py — Canonical run configuration for LLM Chess Engine experiments.

Centralizes all runtime parameters into one validated, serializable object.
Parses from CLI args, env vars, or defaults. Persisted per-run as config.resolved.json.
"""

import argparse
import json
import os
import sys
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone


@dataclass
class RunConfig:
    """Resolved, validated runtime configuration for a single experiment run."""

    temperature: float = 0.8
    constrained_decoding: bool = True
    seed: int = 42
    model: str = "llama3"
    ollama_base_url: str = "http://localhost:11434"
    num_games: int = 50
    tag: str = ""
    run_id: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:6])
    time_limit: float = 15.0
    max_turns: int = 200
    early_termination: bool = False

    # ── Validation ──────────────────────────────────────────

    def validate(self):
        """Validate all parameters. Raises ValueError with clear messages."""
        errors = []

        if not (0.0 <= self.temperature <= 2.0):
            errors.append(
                f"temperature={self.temperature} is out of range [0.0, 2.0].\n"
                f"  Fix: use --temperature with a value between 0.0 and 2.0"
            )

        if not isinstance(self.seed, int):
            errors.append(
                f"seed={self.seed!r} is not an integer.\n"
                f"  Fix: use --seed with an integer value (e.g., --seed 42)"
            )

        if not self.model or not self.model.strip():
            errors.append(
                f"model is empty.\n"
                f"  Fix: use --model with a valid Ollama model name (e.g., --model llama3)"
            )

        if not self.ollama_base_url:
            errors.append(
                f"ollama_base_url is empty.\n"
                f"  Fix: use --ollama-url or set OLLAMA_BASE_URL env var"
            )

        if self.num_games < 1:
            errors.append(
                f"num_games={self.num_games} must be >= 1.\n"
                f"  Fix: use --num-games with a positive integer"
            )

        if self.time_limit <= 0:
            errors.append(
                f"time_limit={self.time_limit} must be > 0.\n"
                f"  Fix: use --time-limit with a positive number (seconds)"
            )

        if self.max_turns < 1:
            errors.append(
                f"max_turns={self.max_turns} must be >= 1.\n"
                f"  Fix: use --max-turns with a positive integer"
            )

        if errors:
            header = "Configuration validation failed:\n"
            detail = "\n".join(f"  [{i+1}] {e}" for i, e in enumerate(errors))
            raise ValueError(header + detail)

    # ── Serialization ───────────────────────────────────────

    def to_dict(self):
        return asdict(self)

    def to_json(self, indent=2):
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path):
        """Save resolved config to a JSON file."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(self.to_json())

    @classmethod
    def from_dict(cls, d):
        # Only pass known fields
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)

    @classmethod
    def from_json_file(cls, path):
        with open(path) as f:
            return cls.from_dict(json.load(f))

    # ── CLI / Env parsing ───────────────────────────────────

    @classmethod
    def from_cli(cls, args=None):
        """Parse from CLI arguments, with env var fallbacks."""
        parser = argparse.ArgumentParser(
            description="LLM Chess Engine — Run Configuration",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""Examples:
  python scripts/run_game.py --temperature 0.2 --seed 42
  python scripts/run_game.py --temperature 0.8 --seed 42 --constrained-decoding
  python scripts/run_game.py --temperature 0.8 --no-constrained-decoding --num-games 100

Environment variables (override defaults, CLI overrides env):
  OLLAMA_BASE_URL    Ollama server URL (default: http://localhost:11434)
  LLM_MODEL          Model name (default: llama3)
""",
        )

        parser.add_argument("--temperature", type=float,
                            default=float(os.environ.get("LLM_TEMPERATURE", "0.8")),
                            help="LLM sampling temperature [0.0, 2.0] (default: 0.8)")
        parser.add_argument("--constrained-decoding", dest="constrained_decoding",
                            action="store_true", default=True,
                            help="Inject legal moves into prompt (default: on)")
        parser.add_argument("--no-constrained-decoding", dest="constrained_decoding",
                            action="store_false",
                            help="Disable legal-move constraint in prompt")
        parser.add_argument("--seed", type=int,
                            default=int(os.environ.get("LLM_SEED", "42")),
                            help="Random seed for reproducibility (default: 42)")
        parser.add_argument("--model", type=str,
                            default=os.environ.get("LLM_MODEL", "llama3"),
                            help="Ollama model name (default: llama3)")
        parser.add_argument("--ollama-url", type=str,
                            default=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
                            help="Ollama server base URL (default: http://localhost:11434)")
        parser.add_argument("--num-games", type=int, default=50,
                            help="Number of games to play (default: 50)")
        parser.add_argument("--tag", type=str, default="",
                            help="Condition tag for this run (e.g., t02_unconstrained)")
        parser.add_argument("--time-limit", type=float, default=15.0,
                            help="Time limit per move in seconds (default: 15.0)")
        parser.add_argument("--max-turns", type=int, default=200,
                            help="Maximum half-moves (ply) to play per game (default: 200)")
        parser.add_argument("--early-termination", action="store_true", default=False,
                            help="Abort game immediately on first hallucination (GUI style)")
        parser.add_argument("--skip-preflight", action="store_true", default=False,
                            help="Skip Ollama connectivity check")

        parsed = parser.parse_args(args)

        config = cls(
            temperature=parsed.temperature,
            constrained_decoding=parsed.constrained_decoding,
            seed=parsed.seed,
            model=parsed.model,
            ollama_base_url=parsed.ollama_url,
            num_games=parsed.num_games,
            tag=parsed.tag,
            time_limit=parsed.time_limit,
            max_turns=parsed.max_turns,
            early_termination=parsed.early_termination,
        )
        config.validate()
        return config, parsed.skip_preflight

    # ── Display ─────────────────────────────────────────────

    def print_banner(self):
        """Print a clear parameter banner at run start."""
        print("=" * 60)
        print("  LLM Chess Engine — Run Configuration")
        print("=" * 60)
        print(f"  Run ID:              {self.run_id}")
        print(f"  Tag:                 {self.tag or '(none)'}")
        print(f"  Model:               {self.model}")
        print(f"  Temperature:         {self.temperature}")
        print(f"  Constrained Decoding:{' ON' if self.constrained_decoding else ' OFF'}")
        print(f"  Seed:                {self.seed}")
        print(f"  Ollama URL:          {self.ollama_base_url}")
        print(f"  Num Games:           {self.num_games}")
        print(f"  Time Limit:          {self.time_limit}s")
        print(f"  Max Turns (Ply):     {self.max_turns}")
        print(f"  Early Termination:   {' ON' if self.early_termination else ' OFF'}")
        print("=" * 60)


if __name__ == "__main__":
    # Quick test: parse and display
    config, skip = RunConfig.from_cli()
    config.print_banner()
    print("\nResolved config JSON:")
    print(config.to_json())
