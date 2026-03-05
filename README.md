# LLM Chess Engine — Built on VICE 1.1 + Llama-3

A research project investigating **LLM hallucinations in chess move generation** by extending the [VICE chess engine](https://www.chessprogramming.org/Vice) (by **Bluefever Software / Richard Allbert**) with [Llama-3 (8B)](https://ollama.com/library/llama3) integration via [Ollama](https://ollama.com/).

> **VICE** (**V**ideo **I**nstructional **C**hess **E**ngine) is an open-source chess engine originally created by [Bluefever Software](http://www.bluefever.net) as part of an [87-video YouTube tutorial series](https://www.youtube.com/watch?v=bGAfaepBco4&list=PLZ1QII7yudbc-Ky058TEaOstZHVbT-2hg) teaching chess engine programming in C. All original VICE source code is used with permission per the author's open-use notice. This project adds LLM integration modules on top of the original engine.

The modified engine uses Llama-3 as its primary move selector, falling back to VICE's classical alpha-beta search when the LLM produces an illegal move. All telemetry (FEN, temperature, latency, legality, raw LLM output) is logged for research analysis.

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

The web app works out of the box with a random-move engine. For LLM-powered moves, build the VICE engine and start Ollama (see below).

### 3. (Optional) Build the VICE Engine + Ollama

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
```

Once the VICE engine is compiled and Ollama is running, the web app will automatically use LLM-generated moves instead of random fallback.

### 4. (Optional) Run the Desktop GUI

```bash
python3 gui.py
```

The desktop GUI plays automated games: **White = random moves**, **Black = Llama-3 via VICE engine**. Telemetry is logged to `llm_research_log.csv`.

### 5. Analyze Results

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
