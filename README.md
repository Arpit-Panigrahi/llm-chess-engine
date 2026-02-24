# LLM Chess Engine — VICE 11 + Llama-3 Hybrid

A research project investigating **LLM hallucinations in chess move generation** by integrating [Llama-3 (8B)](https://ollama.com/library/llama3) into the [VICE](https://www.chessprogramming.org/Vice) chess engine via [Ollama](https://ollama.com/).

The engine uses Llama-3 as its primary move selector, falling back to classical alpha-beta search when the LLM produces an illegal move. All telemetry (FEN, temperature, latency, legality, raw LLM output) is logged for research analysis.

---

## Research Question

> **Can constraining an LLM with a legal-move list eliminate hallucinated chess moves?**

### Key Findings

| Tournament | Temperature | Legal Constraint | Legal Move Rate |
|:-----------|:-----------:|:----------------:|:---------------:|
| T1         | 0.1         | No               | 49.5%           |
| T2         | 0.8         | No               | 43.0%           |
| T3         | 0.8         | Yes              | **97.4%**       |

Adding the legal-move constraint (injecting the full list of valid UCI moves into the prompt) raised the legal move rate from ~43% to **97.4%**.

---

## Architecture

```
┌──────────────┐     UCI Protocol     ┌────────────────────┐
│  gui.py      │◄────────────────────►│  VICE Engine (C)   │
│  (Tkinter)   │                      │                    │
│  Tournament  │                      │  llm_search.c      │──► Builds legal move list
│  Runner      │                      │  http_client.c     │──► HTTP POST to Ollama
│              │                      │  llm_parser.c      │──► Extracts UCI move from LLM
│              │                      │  telemetry.c       │──► Logs to CSV
│              │                      │  search.c          │──► Classical α-β fallback
└──────────────┘                      └────────┬───────────┘
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
├── Source/                  # C source code for the VICE chess engine
│   ├── llm_search.c        # LLM move search entry point + legal move builder
│   ├── http_client.c       # Ollama HTTP integration via libcurl + cJSON
│   ├── llm_parser.c        # UCI move extraction from raw LLM response
│   ├── telemetry.c         # CSV telemetry logging
│   ├── search.c            # Classical alpha-beta search (fallback)
│   ├── evaluate.c          # Position evaluation heuristics
│   ├── movegen.c           # Legal move generation
│   ├── board.c             # Board representation (10x12 mailbox)
│   ├── uci.c               # UCI protocol handler
│   ├── vice.c              # Engine entry point
│   ├── cJSON.c/h           # JSON parser (MIT licensed, Dave Gamble)
│   ├── defs.h              # Constants, types, macros
│   ├── makefile             # Build configuration
│   └── ...                 # Other engine modules (attack, bitboards, etc.)
├── gui.py                  # Tkinter GUI — runs automated tournaments
├── analyze.py              # Data analysis + publication-ready charts
├── data/
│   ├── llm_research_log.csv      # Engine telemetry (464 rows)
│   └── llm_hallucinations.csv    # GUI-captured errors (298 rows)
├── docs/
│   └── ViceReadMe.html     # Original VICE engine documentation
├── .gitignore
├── requirements.txt
├── LICENSE
└── README.md
```

---

## Prerequisites

| Dependency | Version | Purpose |
|:-----------|:--------|:--------|
| GCC        | 11+     | Compile the C engine |
| libcurl    | 7.x+    | HTTP calls to Ollama |
| Ollama     | 0.1+    | Local LLM server |
| Python     | 3.8+    | GUI + analysis scripts |
| Tkinter    | —       | Chess GUI (usually bundled with Python) |

---

## Quick Start

### 1. Clone & Build

```bash
git clone git@github.com:Arpit-Panigrahi/llm-chess-engine.git
cd llm-chess-engine

# Install system dependencies (Fedora)
sudo dnf install -y gcc libcurl-devel python3-tkinter

# Build the engine
cd Source
make
cd ..
```

### 2. Start Ollama

```bash
# Install Ollama (if not already installed)
curl -fsSL https://ollama.com/install.sh | sh

# Pull the model
ollama pull llama3

# Start the server (runs on localhost:11434)
ollama serve
```

### 3. Run a Tournament

```bash
python3 gui.py
```

The GUI plays automated games: **White = random moves**, **Black = Llama-3 via VICE engine**. Telemetry is logged to `llm_research_log.csv`.

### 4. Analyze Results

```bash
python3 analyze.py
```

Generates `llm_analysis_charts.png` with four quadrant charts:
- **Q1**: Legal vs. Illegal moves per session
- **Q2**: Success rate (%) trend
- **Q3**: Latency distribution (box plots)
- **Q4**: Move diversity (unique move curves)

---

## Telemetry Schema

### llm_research_log.csv

| Column | Description |
|:-------|:------------|
| Timestamp | Unix epoch (seconds) |
| FEN | Board state before the move |
| Temperature | LLM sampling temperature |
| Latency_ms | Round-trip time to Ollama |
| Extracted_Move | UCI move parsed from LLM response |
| Is_Legal | 1 = legal, 0 = illegal |
| Fallback_Used | 1 = classical search used, 0 = LLM move played |
| Raw_Response | Full text output from Llama-3 |

---

## Configuration

Key parameters in the source code:

| Parameter | File | Default | Description |
|:----------|:-----|:--------|:------------|
| `temperature` | `llm_search.c` | 0.8 | LLM sampling temperature |
| `CURLOPT_TIMEOUT` | `http_client.c` | 30s | HTTP request timeout |
| `Limit(time=)` | `gui.py` | 15.0s | UCI time limit per move |
| `model` | `http_client.c` | `llama3` | Ollama model name |

---

## How the Legal Move Constraint Works

1. `BuildLegalMoveString()` generates all legal moves for the current position
2. Moves are formatted as a JSON array: `["e7e5", "d7d5", "g8f6", ...]`
3. The array is injected into the LLM prompt:
   > *"You MUST pick your move from this list of legal moves: [...]"*
4. The LLM's response is parsed for a 4–5 character UCI move
5. If the move is not in the legal set → fallback to classical alpha-beta search

---

## License

This project is licensed under the [MIT License](LICENSE).

The VICE chess engine is by Bluefever Software. [cJSON](https://github.com/DaveGamble/cJSON) is by Dave Gamble (MIT License).

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
