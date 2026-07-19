# LLM Chess Engine — Built on VICE 1.1 + Llama-3

A research project investigating **LLM hallucinations in chess move generation** by extending the [VICE chess engine](https://www.chessprogramming.org/Vice) (by **Bluefever Software / Richard Allbert**) with [Llama-3 (8B)](https://ollama.com/library/llama3) integration via [Ollama](https://ollama.com/).

> **VICE** (**V**ideo **I**nstructional **C**hess **E**ngine) is an open-source chess engine originally created by [Bluefever Software](http://www.bluefever.net) as part of an [87-video YouTube tutorial series](https://www.youtube.com/watch?v=bGAfaepBco4&list=PLZ1QII7yudbc-Ky058TEaOstZHVbT-2hg) teaching chess engine programming in C. All original VICE source code is used with permission per the author's open-use notice. This project adds LLM integration modules on top of the original engine.

The modified engine uses Llama-3 as its primary move selector, falling back to VICE's classical alpha-beta search when the LLM produces an illegal move. All telemetry (FEN, temperature, latency, legality, raw LLM output) is logged for research analysis.

---

## Research Question

> **Can constraining an LLM with a legal-move list eliminate hallucinated chess moves?**

### Key Findings

Using the standardized CLI matrix runner (`scripts/run_game.py`) with the robust UCI parser and early termination:

| Condition Tag | Temperature | Legal Constraint | Games | LLM Calls | Legal Move Rate | Unique Moves |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| `t02_unconstrained_v2` | 0.2 | No | 100 | 211 | **52.6%** | 7 |
| `t08_unconstrained` | 0.8 | No | 100 | 210 | **52.4%** | 11 |
| `t08_constrained` | 0.8 | Yes | 20 | 220 | **100.0%** | 40 |

### Key Conclusions
1. **Unconstrained Legality Ceiling**: Without structured constraints, the LLM hits a hard ceiling of **~52% legal moves** regardless of temperature (T=0.2 vs T=0.8).
2. **Deterministic Repetition**: Low temperature (`T=0.2`) does not improve legality; instead, it causes the model to deterministically repeat a single move pattern (e.g., `g8f6`) ignoring the actual board state, leading to rapid game aborts.
3. **Constraint Efficacy**: Injected legal-move constraints achieve a perfect **100.0% legal move rate** while significantly increasing move diversity (**40 unique moves** vs **11** in unconstrained).

---

## Architecture

### Web Interface (New)

```
┌──────────────┐     HTTP/REST      ┌─────────────────────────────┐
│  Web Browser │◄──────────────────►│  Flask Backend (Python)     │
│  (HTML/CSS/  │                    │  web/app.py                 │
│   JavaScript)│                    │                             │
│              │                    │  python-chess game logic    │
└──────────────┘                    └────────────┬────────────────┘
                                                 │ UCI Protocol (stdin/stdout)
                                    ┌────────────▼────────────────┐
                                    │  VICE Engine (C)            │
                                    │  Original: Bluefever Soft.  │
                                    │                             │
                                    │  + llm_search.c  (added)   │──► Legal moves
                                    │  + http_client.c (added)   │──► Ollama API
                                    │  + llm_parser.c  (added)   │──► Move parse
                                    │  + telemetry.c   (added)   │──► CSV logging
                                    └────────────┬────────────────┘
                                                 │ HTTP (libcurl)
                                    ┌────────────▼────────────────┐
                                    │  Ollama (local)             │
                                    │  llama3:latest              │
                                    │  8B params, Q4_0            │
                                    └─────────────────────────────┘
```

### Desktop GUI (Original)

```
┌──────────────┐     UCI Protocol     ┌─────────────────────────────┐
│  gui.py      │◄────────────────────►│  VICE Engine (C)            │
│  (Tkinter)   │                      │  Original: Bluefever Soft.  │
│  Tournament  │                      │                             │
│  Runner      │                      │  + llm_search.c  (added)    │──► Legal moves
│              │                      │  + http_client.c (added)    │──► Ollama API
│              │                      │  + llm_parser.c  (added)    │──► Move parse
│              │                      │  + telemetry.c   (added)    │──► CSV logging
│              │                      │  search.c (original+mod)    │──► α-β fallback
└──────────────┘                      └────────────┬────────────────┘
                                               │ HTTP (libcurl)
                                      ┌────────▼───────────┐
                                      │  Ollama (local)    │
                                      │  llama3:latest     │
                                      │  8B params, Q4_0   │
                                      └────────────────────┘
```

---

## Project Structure

```
.
├── web/                    # NEW — Flask web application
│   ├── app.py              # Flask backend with REST API
│   ├── templates/
│   │   ├── index.html      # Chess game page
│   │   └── research.html   # Research data visualization
│   └── static/
│       ├── css/style.css    # UI styles (dark theme)
│       └── js/game.js       # Client-side chess board & game logic
├── Source/                  # C source — VICE engine + LLM additions
│   ├── llm_search.c        # [ADDED] LLM search entry point + legal move builder
│   ├── http_client.c       # [ADDED] Ollama HTTP integration via libcurl + cJSON
│   ├── llm_parser.c        # [ADDED] UCI move extraction from raw LLM response
│   ├── telemetry.c         # [ADDED] CSV telemetry logging
│   ├── cJSON.c/h           # [ADDED] JSON parser (MIT, Dave Gamble)
│   ├── search.c            # [VICE, modified] Alpha-beta search + LLM fallback
│   ├── vice.c              # [VICE, modified] Engine entry point + curl init
│   ├── uci.c               # [VICE, modified] UCI protocol handler
│   ├── defs.h              # [VICE, modified] Constants, types, macros
│   ├── evaluate.c          # [VICE, original] Position evaluation
│   ├── movegen.c           # [VICE, original] Move generation
│   ├── board.c             # [VICE, original] Board representation (10x12)
│   ├── makefile             # Build configuration
│   └── ...                 # [VICE, original] attack, bitboards, etc.
├── gui.py                  # Tkinter GUI — runs automated tournaments
├── analyze.py              # Data analysis + publication-ready charts
├── data/
│   ├── llm_research_log.csv      # Engine telemetry (464 rows)
│   └── llm_hallucinations.csv    # GUI-captured errors (298 rows)
├── docs/
│   └── ViceReadMe.html     # Original VICE engine documentation
├── api/                    # NEW — Vercel serverless entry point
│   └── index.py            # Wraps Flask app for Vercel deployment
├── vercel.json             # Vercel build & routing configuration
├── .gitignore
├── requirements.txt
├── LICENSE
└── README.md
```

---

## Prerequisites

| Dependency | Version | Purpose |
|:-----------|:--------|:--------|
| Python     | 3.8+    | Web app + GUI + analysis scripts |
| Flask      | 3.1+    | Web application framework |
| GCC        | 11+     | Compile the C engine (optional for web) |
| libcurl    | 7.x+    | HTTP calls to Ollama (engine only) |
| Ollama     | 0.1+    | Local LLM server (engine only) |
| Tkinter    | —       | Desktop GUI (optional, bundled with Python) |

---

## Quick Start

### 1. Clone & Install Dependencies

```bash
git clone git@github.com:Arpit-Panigrahi/llm-chess-engine.git
cd llm-chess-engine

# Install Python dependencies
pip install -r requirements.txt
```

### 2. Run the Web Application

```bash
python web/app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser to:
- **Play chess** against the engine (or random fallback)
- **View research data** and tournament results

The web app works out of the box with a random-move engine. To enable LLM-powered moves,
set `LLM_ENGINE_ENABLED=1`, build the VICE engine, and start Ollama (see below).

### 3. Deploy to Vercel

This project includes a `vercel.json` configuration and a serverless entry point
(`api/index.py`) so you can deploy the Flask web app to [Vercel](https://vercel.com)
with minimal setup.

```bash
# Install the Vercel CLI (once)
npm i -g vercel

# Deploy from the project root
vercel
```

Or connect the GitHub repository directly from the
[Vercel dashboard](https://vercel.com/new) — it will auto-detect the configuration.

> **Note:** The Vercel deployment runs the Flask app as a serverless function. It serves
> the web interface with a random-move fallback because serverless instances cannot run
> the compiled VICE engine or a local Ollama server. Game state lives in memory per
> instance (so it can reset), and research telemetry is read from the bundled CSV files
> rather than written live. For the full LLM experience, run locally with
> `LLM_ENGINE_ENABLED=1` and a built VICE engine.

### 4. (Optional) Build the VICE Engine + Ollama

```bash
# Install system dependencies (Fedora)
sudo dnf install -y gcc libcurl-devel python3-tkinter

# Build the engine
cd Source
make
cd ..

# Install Ollama (if not already installed)
curl -fsSL https://ollama.com/install.sh | sh

# Pull the model and start the server
ollama pull llama3
ollama serve

# Enable the LLM engine for the web app
export LLM_ENGINE_ENABLED=1
```

Once the VICE engine is compiled and Ollama is running, the web app will automatically use LLM-generated moves instead of random fallback.

### 5. (Optional) Run the Desktop GUI

```bash
python3 gui.py
```

The desktop GUI plays automated games: **White = random moves**, **Black = Llama-3 via VICE engine**. Telemetry is logged to a git-ignored file at `runs/llm_hallucinations.csv`.

### 6. Diagnose your Ollama Environment

Detect host/container network topology and trace connectivity using:

```bash
python scripts/check_ollama_env.py --model llama3.1
```

It validates Ollama reachability, local process activity, and lists available models with clear instructions for Native, WSL, and Docker environments.

### 7. Run Required Matrix Experiment

Run the automated three-condition experiment matrix (100 games per condition by default, model `llama3.1`, seed `42`):

```bash
# Run the full 300 game matrix (3 conditions * 100 games)
bash scripts/run_experiment_matrix.sh --model llama3.1 --num-games 100
```

#### Key Execution Controls:
* **Deterministic Seed (`--seed 42`)**: Passed to both Ollama and the random move generator to ensure White's random moves are identical per game index across all conditions, establishing a fair baseline.
* **Early Termination (`--early-termination`)**: Aborts a game immediately on the first illegal move (hallucination) or empty response. This matches the legacy GUI's behavior and is **highly recommended for CPU-only execution** to complete unconstrained runs in minutes rather than hours.
  ```bash
  # Run matrix with early termination for fast CPU execution
  bash scripts/run_experiment_matrix.sh --model llama3.1 --num-games 100 --early-termination
  ```
* **Max Turns (`--max-turns 22`)**: Caps game length to a specific number of ply (half-moves). For constrained runs, setting this to a lower value (e.g., 22 ply) is recommended to prove the 100% legality hypothesis without the overhead of full 200-ply games.

### 8. Analyze Matrix Results & Generate Report

Aggregates execution logs, runs integrity checks (schema and duplicate checks), computes pairwise deltas, and writes a research report:

```bash
python scripts/analyze_all.py --run-root runs --out reports/experiment_matrix
```

This creates:
- `reports/experiment_matrix/report.md`: Markdown research report with comparison tables and interpretations.
- `reports/experiment_matrix/metrics_comparison.csv`: Condensed comparative table.
- `reports/experiment_matrix/plots/legal_rate_comparison.png`: Vertical bar chart of success percentages.
- `reports/experiment_matrix/plots/latency_comparison.png`: Double bar chart comparing mean vs. median reaction times.
- `reports/experiment_matrix/plots/move_diversity_comparison.png`: Unique moves proposed per condition.

---

## Robust UCI Parser & SAN Resolution

The orchestrator (`scripts/run_game.py`) includes a robust UCI parser (`extract_uci_move`) that handles various LLM output formats:
1. **Long Algebraic Notation (LAN)**: Strips piece prefixes (e.g., `"Nb8c6"` is resolved to `"b8c6"`).
2. **Standard Algebraic Notation (SAN)**: Resolves SAN moves (e.g., `"Nf6"`) contextually against the current `chess.Board` state to find the corresponding UCI move (e.g., `"g8f6"`).
3. **Formatting Cleanup**: Strips quotes, markdown bolding, and trailing punctuation (e.g., `'"e7e5"'` is cleaned to `"e7e5"`).

This separates formatting variations from true logical chess errors, ensuring unconstrained runs measure the model's actual chess logic.

---

## Telemetry Schema

See [docs/results_schema.md](docs/results_schema.md) for full descriptions of all telemetry log and manifest structures.

---

## Tinkering & Custom Experiments

You can easily run custom experiments with different temperatures, constraint settings, seeds, and game lengths to find the optimal configuration or observe specific LLM behaviors.

### 1. Tinkering with a Single Game / Run
Use `scripts/run_game.py` to run custom configurations directly:

* **Greedy / Deterministic Play (`T=0.0` + Constrained)**:
  Best for testing the model's absolute baseline chess preference under strict constraints.
  ```bash
  python3 scripts/run_game.py --temperature 0.0 --constrained-decoding --num-games 1 --tag greedy_constrained
  ```

* **Creative Play (`T=1.2` + Constrained)**:
  Encourages the model to play highly diverse and unusual moves while ensuring they remain 100% legal.
  ```bash
  python3 scripts/run_game.py --temperature 1.2 --constrained-decoding --num-games 1 --tag creative_constrained
  ```

* **Extreme Hallucination Test (`T=1.8` + Unconstrained)**:
  Observe how the model behaves under extreme randomness without constraints. Early termination is recommended to abort the game immediately on the first illegal move.
  ```bash
  python3 scripts/run_game.py --temperature 1.8 --no-constrained-decoding --num-games 1 --early-termination --tag extreme_hallucination
  ```

### 2. Tinkering with the Experiment Matrix
Use `scripts/run_experiment_matrix.sh` to run the full 3-condition matrix with custom parameters:

* **Fast Custom Matrix (5 games per condition)**:
  ```bash
  bash scripts/run_experiment_matrix.sh --model llama3.1 --num-games 5 --seed 999 --early-termination
  ```

* **Matrix with Custom Network Endpoint & Turn Cap**:
  Pass any extra arguments directly to the underlying `run_game.py` script:
  ```bash
  bash scripts/run_experiment_matrix.sh --model llama3.1 --num-games 10 --early-termination --max-turns 15 --ollama-url http://192.168.1.50:11434
  ```

### 3. Temperature Cheat Sheet
Use this guide to select the right temperature for your experiments:

| Temperature | Randomness | Expected Behavior (Unconstrained) | Expected Behavior (Constrained) |
|:---:|:---|:---|:---|
| **`0.0`** | None (Greedy) | Deterministic, repeats identical moves, ignores board state. | Deterministic, plays the same opening/moves every game. |
| **`0.2 - 0.5`** | Low | High repetition, low move diversity, ~52% legal rate. | Low move diversity, highly standard openings. |
| **`0.7 - 0.9`** | Balanced | Moderate diversity, frequent hallucinations, ~52% legal rate. | Balanced play, good move diversity, 100% legal. |
| **`1.0 - 1.5`** | High | Heavy hallucinations, rapid game aborts. | High move diversity, unusual/creative moves, 100% legal. |
| **`> 1.5`** | Extreme | Mostly gibberish/invalid formatting. | Extreme move diversity, highly chaotic play, 100% legal. |

### 4. CLI Parameter Reference

| Flag | Type | Default | Description |
|:---|:---:|:---:|:---|
| `--temperature` | `float` | `0.8` | LLM sampling temperature ∈ `[0.0, 2.0]`. |
| `--constrained-decoding` | `bool` | `True` | Inject the list of legal moves into the prompt. |
| `--no-constrained-decoding`| `bool` | `False` | Disable legal move prompt injection. |
| `--seed` | `int` | `42` | Deterministic seed for Ollama and random moves. |
| `--num-games` | `int` | `10` | Number of games to play in the run. |
| `--max-turns` | `int` | `200` | Maximum ply (half-moves) per game. |
| `--early-termination` | `bool` | `False` | Abort game immediately on the first illegal move. |
| `--ollama-url` | `str` | `http://localhost:11434` | Endpoint URL of the Ollama server. |
| `--model` | `str` | `llama3` | Ollama model name to use. |
| `--tag` | `str` | `None` | Custom tag to identify the run in reports. |

---

## Troubleshooting & Environment Guide

See [docs/runtime_modes_ollama.md](docs/runtime_modes_ollama.md) for full setup instructions mapping Native Linux, WSL2 hosts, and Docker configurations.

---

## Privacy Policy: No Shipped Personal Logs

No active author runtime logs or personal system details are committed to tracking. Local runs automatically output to `runs/` and `logs/`, which are blocked in `.gitignore`. Historical data is preserved exclusively as sanitized reference samples inside `data/reference/`.

---

## How the Legal Move Constraint Works

1. `BuildLegalMoveString()` generates all legal moves for the current position
2. Moves are formatted as a JSON array: `["e7e5", "d7d5", "g8f6", ...]`
3. The array is injected into the LLM prompt:
   > *"You MUST pick your move from this list of legal moves: [...]"*
4. The LLM's response is parsed for a 4–5 character UCI move
5. If the move is not in the legal set → fallback to classical alpha-beta search

---

## Acknowledgments

This project would not exist without the foundational work of **Richard Allbert (Bluefever Software)**, who created the VICE chess engine and generously made it available as an educational resource through his [YouTube series](https://www.youtube.com/watch?v=bGAfaepBco4&list=PLZ1QII7yudbc-Ky058TEaOstZHVbT-2hg). The original VICE source code is used with permission per the author's open-use statement:

> *"You are welcome to use the code as you like to help with your projects!"*  
> — Richard Allbert, VICE ReadMe

---

## License

The **LLM integration code** (files marked `[ADDED]` above) is licensed under the [MIT License](LICENSE).

The **original VICE engine** source code is by [Bluefever Software / Richard Allbert](http://www.bluefever.net) and is used under their open-use permission. See [docs/ViceReadMe.html](docs/ViceReadMe.html) for the original documentation.

[cJSON](https://github.com/DaveGamble/cJSON) is by Dave Gamble (MIT License).

---

## Citation

If you use this work in academic research, please cite:

```bibtex
@misc{panigrahi2026llmchess,
  author       = {Panigrahi, Arpit},
  title        = {LLM Chess Engine: Measuring and Constraining Hallucinations in Neural Move Generation},
  year         = {2026},
  publisher    = {GitHub},
  url          = {https://github.com/Arpit-Panigrahi/llm-chess-engine}
}
```

Please also credit the original VICE engine:

```bibtex
@misc{allbert2013vice,
  author       = {Allbert, Richard},
  title        = {VICE: Video Instructional Chess Engine},
  year         = {2013},
  publisher    = {Bluefever Software},
  url          = {https://www.youtube.com/playlist?list=PLZ1QII7yudbc-Ky058TEaOstZHVbT-2hg}
}
```
