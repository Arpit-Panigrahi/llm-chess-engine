# LLM Chess Engine Deep Dive (From Scratch)

> A plain-language, end-to-end explanation of this whole project — from how a chess engine works to how the LLM (Llama-3) is plugged in, how data is logged, and how the research analysis runs.
>
> You should be able to explain this to a curious 15-year-old after reading it.

---

## 1. Big Picture: What Is This Project?

This project is a **chess engine** that has been upgraded with a **Large Language Model (LLM)** — Llama-3 — so we can study when the LLM makes **illegal or nonsensical chess moves** (called *hallucinations*) and how to reduce them.

There are three main parts:

1. **Classical Chess Engine (VICE in C)**  
   - Super-fast, traditional chess engine written in C.  
   - Knows all the rules of chess perfectly and never plays illegal moves.
2. **LLM Integration Layer (also in C)**  
   - Talks to the local Llama-3 server using HTTP.  
   - Gives the LLM the board position and a list of legal moves.  
   - Tries to use the LLM’s move; if it’s illegal, falls back to the classical engine.
3. **Python Tools**  
   - **GUI (`gui.py`)**: Runs automatic tournaments — White = random, Black = Llama-3 via this engine.  
   - **Analyzer (`analyze.py`)**: Reads logs and produces research-grade charts and stats.

The **research question** is:

> If we show the LLM a list of all legal moves, and tell it to choose only from that list, can we almost completely eliminate illegal / hallucinated moves?

The answer, from the experiments here, is **yes**: legal move rate jumps from ~43% to about **97.4%**.

---

## 2. How a Classical Chess Engine Works (VICE)

We start with the original **VICE engine** by Richard Allbert, which is a teaching engine written in C. This project keeps almost all of that code and adds new files on top.

### 2.1 Board Representation

Key files: `Source/board.c`, `Source/data.c`, `Source/defs.h`

- The board is stored in a **10x12 array** of 120 squares (called *sq120*).  
  - The real 8x8 board sits in the middle.  
  - The outer ring is marked OFFBOARD so move-generation code can step off the side and easily detect it.
- Each square holds an integer representing a piece:  
  - `wP` = white pawn, `wN` = white knight, ..., `bK` = black king.  
  - These are defined in an `enum` in `defs.h`.
- There are also **bitboards** (in `bitboards.c` and `data.c`):  
  - A bitboard is a 64-bit number where each bit is a square on the real 8x8 board.  
  - Example: a 1 in bit 0 means there is a pawn on a1, etc.  
  - They’re used for fast evaluation of pawn structures, etc.

### 2.2 Important Data Structures

Defined in `Source/defs.h`:

- `S_BOARD` — the **entire board state**:
  - `pieces[120]` — piece on each 120-square board cell.
  - `pawns[3]` — bitboards for white pawns, black pawns, all pawns.
  - `side` — whose turn: WHITE or BLACK.
  - `enPas` — en-passant square.
  - `castlePerm` — castling rights bits (WKCA, WQCA, BKCA, BQCA).
  - `KingSq[2]` — king square for white and black.
  - `material[2]` — material score for each side.
  - `pList[13][10]` — lists of positions of each piece type.
  - `HashTable` — transposition table (caching positions).
- `S_SEARCHINFO` — information needed for a search:
  - Time controls, node count, depth, flags for “time’s up”, etc.

In simple words: **`S_BOARD` is the “snapshot of the entire game right now”**, and **`S_SEARCHINFO` is the “rules for how much time/effort we spend thinking.”**

### 2.3 Move Generation

Key file: `Source/movegen.c`

- The engine generates **all pseudo-legal moves** (moves that obey piece-movement rules but might leave your own king in check).  
- Functions:
  - `GenerateAllMoves(pos, list)` — fills `list` with all pseudo-legal moves for the side to move.
  - `GenerateAllCaps(pos, list)` — like above, but captures only.
- It handles:
  - Pawn moves, double pawn pushes, promotions.
  - En-passant captures.
  - Castling moves.

Each move is encoded as a single `int` storing:

- from-square, to-square, captured piece, promotion piece, special flags (castle, en-passant, pawn start).

Helper macros in `defs.h` extract these fields (e.g. `FROMSQ(m)`, `TOSQ(m)`).

### 2.4 Making and Unmaking Moves

Key file: `Source/makemove.c`

- `MakeMove(pos, move)` applies a move to `pos`:
  - Updates the `pieces` array (move piece, capture, promotion).
  - Updates bitboards for pawns.
  - Updates material and piece counts.
  - Updates en-passant and castling rights.
  - Updates the Zobrist hash key (`pos->posKey`).
  - Finally checks: **does this leave my king in check?**  
    - If yes, the move is **illegal**; the function returns `FALSE` and *undoes* it.
- `TakeMove(pos)` reverses the last move using stored history.

So the pattern is:

1. Generate pseudo-legal moves.  
2. For each move, call `MakeMove`.  
3. If it returns FALSE → move is illegal, discard it.  
4. If TRUE → explore the resulting position.

### 2.5 Attack Detection

Key file: `Source/attack.c`

`SqAttacked(sq, side, pos)` checks if a square is attacked by a given side:

- Checks pawn attack patterns.
- Checks knight jump squares.
- Ray-traces along rook, bishop, and queen directions.
- Checks adjacent king squares.

This is used to:

- Verify king safety when generating legal moves.  
- Detect check and checkmate.

### 2.6 Evaluation Function

Key file: `Source/evaluate.c`

`EvalPosition(pos)` returns a score from White’s point of view:

- Starts with **material score**: sum of piece values (pawn=100, knight≈325, etc.).
- Adds or subtracts bonuses for:
  - Pawn structure (isolated/passed pawns).
  - Piece placement (piece-square tables: good vs bad squares).
  - Rooks/queens on open or semi-open files.
  - Bishop pair bonus.
  - King safety: different tables for opening vs endgame.
- Detects some **drawish** positions (insufficient material, etc.).

If it’s Black’s turn, the score sign is flipped so that:  
- Positive = good for side to move.  
- Negative = bad for side to move.

### 2.7 The Search (Classical Engine Brain)

Key file: `Source/search.c`

The main classical search function is `SearchPosition_Classical(pos, info)`:

- Uses **iterative deepening**: depth 1, 2, 3, … up to `info->depth`.
- At each depth, calls `AlphaBeta(...)`, a standard **alpha-beta pruning** search:
  - Explores a tree of possible moves: my move, your move, etc.
  - Alpha-beta prunes branches that cannot improve the outcome.
- Inside `AlphaBeta`:
  - Uses **quiescence search** to avoid “horizon effects” from noisy positions.
  - Uses a hash table (transposition table) to reuse results for repeated positions.
  - Uses heuristics like **move ordering**, **killer moves**, and **history scores** to search smarter.

Eventually, `SearchPosition_Classical` prints a line like:

```text
bestmove e2e4
```

following the **UCI protocol** (Universal Chess Interface).

### 2.8 UCI Protocol and Engine Entry Point

Key files: `Source/uci.c`, `Source/vice.c`

- `vice.c` is the main `int main(...)` for the C engine:
  - Initializes all tables and hash keys (`AllInit()` in `init.c`).
  - Sets up the hash table and maybe disables the opening book.
  - Waits for commands from stdin (usually a GUI or `python-chess`).
  - When it sees `uci`, it calls `Uci_Loop(...)`.

- `uci.c` (`Uci_Loop`) implements the **UCI protocol**:
  - `position ...` → sets the board to a given FEN and applies moves.
  - `go ...` → starts thinking with given time limits; calls `SearchPosition` (LLM-aware version) or classical search.
  - `bestmove xxyy` → prints the chosen move back to the GUI.

So from the outside, this engine behaves like a normal UCI engine (like Stockfish, etc.), but internally it can call the LLM.

---

## 3. Where the LLM Comes In

New key files for LLM integration:

- `Source/llm_search.c` — main LLM-based search hook.
- `Source/http_client.c` + `Source/http_client.h` — talks to Ollama via HTTP using libcurl.
- `Source/llm_parser.c` + `Source/llm_parser.h` — extracts a clean UCI move from raw text.
- `Source/telemetry.c` + `Source/telemetry.h` — logs a CSV row for each LLM move.
- `Source/cJSON.c` + `Source/cJSON.h` — JSON parsing library.

### 3.1 Replacing the Search Entry Point

In `defs.h` you’ll see:

```c
extern void SearchPosition_Classical(S_BOARD *pos, S_SEARCHINFO *info);
extern void SearchPosition(S_BOARD *pos, S_SEARCHINFO *info); // Your new LLM hook
```

And in `uci.c`, when a `go` command comes in, it calls `SearchPosition(pos, info)`.

- The **original** VICE only had one `SearchPosition`, which did classical alpha-beta.  
- This project keeps that logic in `SearchPosition_Classical` (still in `search.c`).  
- The new **LLM-aware** `SearchPosition` lives in `llm_search.c` and decides:
  - Try LLM first.  
  - If LLM fails or gives an illegal move → fall back to classical search.

### 3.2 Building the Legal Move List for the LLM

Function: `BuildLegalMoveString(S_BOARD *pos, char *out, size_t out_size)` in `llm_search.c`.

What it does:

1. Calls `GenerateAllMoves(pos, list)` to get all **pseudo-legal** moves.
2. For each move:
   - Calls `MakeMove` and checks if it returns TRUE (meaning the move is fully legal).
   - If legal, calls `TakeMove` to undo it.
   - Converts the move to **UCI format** using `PrMove`, e.g. `e2e4`.
3. Builds a JSON array string like:

   ```json
   ["e2e4", "d2d4", "g1f3", ...]
   ```

4. Prints a debug line:

   ```text
   info string Generated Legal Moves Array: ["e2e4", ...]
   ```

This array is later injected into the LLM prompt so the model knows the **only allowed moves**.

### 3.3 Talking to Ollama (HTTP Client)

Function: `GetMoveFromOllama(...)` in `http_client.c`.

High-level steps:

1. Builds a JSON payload for the Ollama `/api/generate` endpoint.
2. Uses `cJSON` to build the JSON:
  - Sets `model` to `"llama3"` (or whichever Ollama model name you use).
  - Builds a **prompt** string that includes:
    - Which side the engine is playing (White or Black).
    - The current FEN string.
    - A plain English sentence listing the legal moves array.
    - Very strict instructions: *“Respond ONLY with a 4-character UCI move (e.g. e7e5). Do not include any other text.”*
  - Adds `options.temperature = 0.8` to control randomness.
3. Uses **libcurl** to send an HTTP POST to `http://localhost:11434/api/generate` with JSON body.
4. Uses a callback (`WriteMemoryCallback`) to collect the HTTP response into a memory buffer.
5. Parses the JSON response from Ollama with `cJSON_Parse(...)` and extracts the `"response"` field (the raw LLM text) into `raw_response`.
6. On network errors, timeouts, or parse failures, it prints an info string and returns `0` (failure) so the caller can trigger fallback.

Important safety detail: `CURLOPT_TIMEOUT` is set to **30 seconds**, so if the LLM hangs, the engine doesn’t. It times out and uses classical search instead.

### 3.4 Parsing the LLM’s Text into a Move

Function: `ExtractUCI(const char *raw_response, char *uci_move)` in `llm_parser.c`.

Problem: even if we *ask* the LLM to respond only with `e2e4`, it might still output:

> "I recommend playing **e2e4**, the king’s pawn opening."

We therefore need to **scan** the text and extract the first token that *looks exactly like* a UCI move.

How `ExtractUCI` works:

1. Copies `raw_response` into a local buffer and tokenizes it using delimiters:
  - Spaces, newlines, punctuation like `.,:;"'()[]{}`.
2. For each token, it lowercases it and calls `IsValidUCIMove(token)`:
  - Length must be 4 or 5 characters.
  - Pattern must be `[a-h][1-8][a-h][1-8]` (from and to squares).
  - Optional 5th char (for promotions) must be `q`, `r`, `b`, or `n`.
3. The **first** token that passes these checks is copied into `uci_move`.
4. If none are found, `uci_move` is left empty.

This keeps us safe from extra words, punctuation, or formatting the LLM might add.

### 3.5 Putting It Together: `SearchPosition` (LLM + Fallback)

Function: `SearchPosition(S_BOARD *pos, S_SEARCHINFO *info)` in `llm_search.c`.

Flow:

1. **Prepare search**
  - Calls `ClearForSearch(pos, info)` to reset history/killer tables and counters.
  - Converts the current position to FEN via `BoardToFen(pos, fen)`.
  - Calls `BuildLegalMoveString(pos, legal_moves_str, ...)`.
2. **Call LLM**
  - Starts a timer using `gettimeofday` to measure latency.
  - Calls `GetMoveFromOllama(fen, temperature, legal_moves_str, raw_response, ...)`.
3. **Parse and validate**
  - If HTTP succeeded, runs `ExtractUCI(raw_response, uci_move)`.
  - If `uci_move` is non-empty, calls `ParseMove(uci_move, pos)` to let VICE:
    - Convert the move string to internal move encoding.
    - Check if this move is **legal** in the current position.
  - If `ParseMove` returns a valid move (not `NOMOVE`):
    - `is_legal = 1`, `fallback_used = 0`.
    - Stops timer and computes `latency_ms`.
    - Prints `bestmove <move>` according to UCI protocol.
4. **Fallback if needed**
  - If any step fails (HTTP error, no token, illegal move), it:
    - Leaves `fallback_used = 1`.
    - Stops timer and computes `latency_ms`.
    - Prints an `info string` explaining the failure.
    - Calls `SearchPosition_Classical(pos, info)` to let the traditional engine pick a move.
5. **Log telemetry**
  - Finally calls `LogLLMAction(...)` in `telemetry.c` to record:
    - `fen`, `temperature`, `latency_ms`, `raw_response`, `uci_move`, `is_legal`, `fallback_used`.

So, in one sentence: **the LLM gets first shot at choosing a move, but the classical engine is always there as a safety net, and every attempt is logged for research.**

---

## 4. Telemetry: What Exactly Gets Logged?

Key files: `Source/telemetry.c`, `Source/telemetry.h`, `data/llm_research_log.csv`

### 4.1 CSV Logging Function

Function: `LogLLMAction(...)` in `telemetry.c`.

Steps:

1. Ensures the `data/` directory exists with `mkdir("data", 0755)`.
2. Opens `data/llm_research_log.csv` in **append mode** (`"a"`).
3. Sanitizes strings (removes commas, newlines, quotes) so the CSV format stays valid.
4. Gets current Unix timestamp.
5. Writes one line per move:

  ```text
  Timestamp,FEN,Temperature,Latency_ms,Extracted_Move,Is_Legal,Fallback_Used,Raw_Response
  ```

  For example:

  ```text
  1740200000,rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1,0.80,245,e2e4,1,0,Llama raw text...
  ```

If the file can’t be opened (permissions, etc.), it simply returns — the engine never crashes because of logging.

### 4.2 Columns Meaning (Recap)

As used in `analyze.py`:

- `Timestamp` — Unix time in seconds when the LLM call finished.
- `FEN` — the board state **before** the move.
- `Temp` / `Temperature` — sampling temperature sent to the LLM.
- `Tokens/Time` / `Latency_ms` — round-trip time to Ollama in milliseconds.
- `Move` / `Extracted_Move` — UCI move parsed from the LLM output.
- `Valid` / `Is_Legal` — 1 if the move was legal, 0 if not.
- `Invalid` / `Fallback_Used` — 1 if the classical engine was used instead.
- `Raw_Output` / `Raw_Response` — entire raw text from the LLM (sanitized).

---

## 5. Python GUI: How the Tournaments Run

Key file: `gui.py`

The GUI is a **Tkinter** window that uses **python-chess** and talks to the C engine as a UCI engine.

### 5.1 Engine Setup

At the top of `gui.py`:

- `ENGINE_PATH` is built as `.../Source/vice` (the compiled C engine binary).
- The engine is started with:

  ```python
  self.engine = chess.engine.SimpleEngine.popen_uci(ENGINE_PATH)
  ```

This launches the C engine and talks to it through stdin/stdout using the UCI protocol.

### 5.2 Board and Display

- Uses `chess.Board()` from `python-chess` as the **high-level board**.
- Tkinter `Canvas` draws an 8x8 board and uses Unicode chess symbols for pieces.
- Handles mouse clicks so you can move white pieces manually when not in auto-test mode.

### 5.3 Automated Tournament Mode

Method: `run_automated_test(self)` in `ChessGUI`.

Behavior:

- Plays up to `max_games = 100` games in a loop.
- **White** moves:
  - Chooses a random move from `list(self.board.legal_moves)` and pushes it.
- **Black** moves:
  - Asks the engine: `self.engine.play(self.board, chess.engine.Limit(time=15.0))`.
  - This sends the current position to the UCI engine, which in turn calls the LLM + fallback logic.

If the engine (LLM) ever tries an **illegal move**, `python-chess` raises `chess.engine.EngineError`. The code catches this:

- Logs the error to `data/llm_hallucinations.csv` with columns:
  - Timestamp, Game_Number, Turn_Number, FEN, Error_Message.
- Resets the board and continues with the next game.

So you get **two types of logs**:

1. **Engine-side telemetry** — `llm_research_log.csv` from `telemetry.c`.
2. **GUI-side hallucination log** — `llm_hallucinations.csv` from Python.

These combine to give a detailed picture of when, why, and how the LLM fails.

---

## 6. Analysis Script: Turning Logs into Insights

Key file: `analyze.py`

This is a self-contained analysis pipeline that:

1. Loads the CSV logs into Pandas.
2. Cleans and segments the data into **tournaments**.
3. Prints detailed console stats.
4. Draws a set of **four quadrant plots** into `llm_analysis_charts.png`.

### 6.1 Loading and Cleaning Data

- Reads `data/llm_research_log.csv` into a DataFrame `df` with named columns.
- Reads `data/llm_hallucinations.csv` into `df_hall`.
- Cleans text columns (strip, replace `nan` with empty).
- Converts numeric columns to numbers (temperature, latency, Valid/Invalid as ints).
- Creates `DateTime` and `Date` columns from the Unix timestamp.
- Drops rows where no move was extracted (timeouts / hard failures).

### 6.2 Session / Tournament Segmentation

Function: `assign_session(row)`:

- If `Temp == 0.1` → **Tournament 1** (T1), low temperature, no constraint.
- Else if `Date <= 2026-02-22` → **Tournament 2** (T2), high temperature, no constraint.
- Else → **Tournament 3** (T3), high temperature, **legal move constraint enabled**.

Adds a `Session` column with labels like:

- `"T1: Temp=0.1\n(No Constraint)"`
- `"T2: Temp=0.8\n(No Constraint)"`
- `"T3: Temp=0.8\n(Legal Moves\nConstraint)"`

### 6.3 Final Metrics and Per-Session Stats

The script prints:

- Total valid API responses.
- Total logic failures (Invalid / fallback used).
- Final success rate (legal moves / attempts).
- Rows dropped for timeouts.

For each session (T1, T2, T3) it prints:

- Date range of calls.
- Total LLM calls and valid responses.
- Number and percentage of legal moves.
- Number and percentage of fallback triggers.
- Latency stats (mean, median, min, max, std dev).
- Unique move count and top moves (with ASCII bars showing frequencies).

It also summarizes the hallucination log (`df_hall`):

- Total hallucination entries.
- Unique illegal moves.
- Top 5 illegal moves with frequencies.

### 6.4 Quadrant Plots

The four-quadrant chart shows:

1. **Q1: Legal vs Illegal per Session**  
  - Side-by-side bars: number of legal vs illegal moves per tournament.
2. **Q2: Success Rate Comparison**  
  - Bar chart of percentage of legal moves for T1, T2, T3.
3. **Q3: Latency Distribution**  
  - Box plots of response times per tournament, with mean markers.
4. **Q4: Move Diversity**  
  - Line plots of the top 10 moves per session (as % of all moves).

This makes the main result very clear: **adding the legal move constraint dramatically raises the success rate (to ~97.4%) while still keeping move diversity high.**

---

## 7. How All the Pieces Talk to Each Other

Putting everything together:

1. You start **Ollama** with the Llama-3 model (`ollama serve` + `ollama pull llama3`).
2. You build the C engine in `Source/` with `make`, which produces the `vice` binary.
3. You run `python3 gui.py`:
  - The GUI launches, starts the UCI engine (`Source/vice`).
4. During a game:
  - GUI (python-chess) sends a **UCI `position` + `go`** command.
  - `uci.c` calls `SearchPosition(pos, info)`.
  - `llm_search.c` builds the legal moves array and calls `GetMoveFromOllama`.
  - `http_client.c` sends HTTP to Ollama and receives text.
  - `llm_parser.c` extracts a UCI move from that text.
  - If legal → engine prints `bestmove` with the LLM move.
  - If illegal / error → engine uses `SearchPosition_Classical` to pick a move.
  - `telemetry.c` logs everything to `data/llm_research_log.csv`.
  - GUI logs any catastrophic engine errors to `llm_hallucinations.csv`.
5. Later, you run `python3 analyze.py`:
  - Loads the CSV logs.
  - Segments by tournaments.
  - Prints metrics and saves `llm_analysis_charts.png`.

This is a **closed loop**: play games → log behavior → analyze → refine prompts/constraints.

---

## 8. Glossary (15-Year-Old Friendly)

- **Engine** — a computer program that plays chess. It calculates moves by looking ahead many turns.
- **LLM (Large Language Model)** — a program like ChatGPT that reads and writes text, trained on huge amounts of data.
- **Hallucination** — when an LLM confidently says something that is **wrong** or impossible, like a chess move that breaks the rules.
- **FEN** — a one-line text description of a chess board. It tells you where all the pieces are, whose turn it is, and some extra info.
- **UCI Move** — a move written like `e2e4` or `g7g8q` (for promotion). It says: “from square” + “to square” + (maybe) promotion piece.
- **Alpha-beta search** — a smart way for a chess engine to search many possible move sequences without checking every single one.
- **Evaluation function** — a formula the engine uses to score a position: positive = good for White, negative = good for Black.
- **Bitboard** — a 64-bit number used to represent which squares have certain pieces. It’s like having 64 on/off switches in one number.
- **Latency** — how long it takes (in milliseconds) for the LLM to receive the request and answer.
- **Temperature (LLM)** — controls how “random/creative” the LLM is. Low temperature = more predictable. High = more varied.
- **Constraint** — a rule we give the LLM, like “you MUST choose from this list of legal moves only.”
- **Fallback** — when the LLM fails, we let the classical engine pick the move instead.

---

## 9. Where to Change Things Yourself

If you want to experiment:

- **Change LLM temperature**:  
  - Edit `float temperature = 0.8;` in `Source/llm_search.c`.
- **Change HTTP timeout**:  
  - Edit `CURLOPT_TIMEOUT` in `Source/http_client.c`.
- **Change model name**:  
  - Edit `"model", "llama3"` in `Source/http_client.c`.
- **Change GUI time per move**:  
  - In `gui.py`, adjust `chess.engine.Limit(time=15.0)`.
- **Change max games per run**:  
  - In `gui.py`, change `self.max_games = 100`.

Because everything is logged and analyzed, you can tweak these knobs and then re-run `analyze.py` to see *exactly* how the LLM’s behavior changes.

You now have a full mental model of the project: from classical chess engine internals, to LLM prompting, to logging, to research analysis.