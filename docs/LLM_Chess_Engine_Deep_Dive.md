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
   - `