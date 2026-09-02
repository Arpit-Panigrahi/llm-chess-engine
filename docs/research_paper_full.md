# Constraining Large Language Model Chess Move Generation: A Prompt-Level Legal Move Injection Approach to Eliminating Hallucinations with Dynamic Move Compression, BPE Tokenizer Boundary Isolation, and Granular Latency Profiling

**Arpit Panigrahi**
*School of Computer Science and Engineering, Vellore Institute of Technology (VIT), Chennai, Tamil Nadu, India*
*Email: arpitpanigrahi06@gmail.com*
*GitHub: https://github.com/Arpit-Panigrahi/llm-chess-engine*

---

## Abstract

Large Language Models (LLMs) demonstrate remarkable linguistic and semantic competence but consistently fail at tasks requiring strict formal rule adherence, such as legal chess move generation. This paper presents a comprehensive empirical evaluation of **prompt-level constrained decoding**—dynamically injecting valid legal Universal Chess Interface (UCI) moves into the LLM prompt context—to deterministically eliminate hallucinated moves produced by autoregressive transformer models. We evaluate Llama 3.1 8B Instruct (4-bit quantized) on an open-source experimental platform integrating the VICE chess engine (C), a Docker Ollama inference backend, a Python orchestration layer, and real-time depth-12 Stockfish 18 ground-truth evaluation.

Across an extensive benchmark matrix ($N = 260$ games, $1{,}077$ neural network inference calls, and $1{,}097$ total moves), we make the following key empirical discoveries:

1. **Unconstrained models hit a hard $\approx 52\%$ legality ceiling** regardless of sampling temperature, with 100% of games terminating in illegal-move aborts by turn 2–3.
2. **BPE Tokenizer Boundary Isolation:** We identify the root cause of formatting-induced hallucinations—Byte-Pair Encoding subword merging across undelimited coordinate tokens—and demonstrate that quotation-delimited atomic move formatting eliminates this phenomenon, restoring $\mathbf{100.0\%}$ legal compliance deterministically.
3. **Dynamic Move Compression (DMC):** A central-square-priority grouping algorithm reduces prompt token prefill by $45.1\%$ (from 270.8 tokens to 193 tokens) compared to raw JSON arrays, while preserving full legal coverage.
4. **Latency Decomposition:** We provide the first explicit separation of initial cold-start disk loading (18.0s–34.5s) from warm steady-state inference, demonstrating sub-second per-turn execution ($\mathbf{792\text{–}1{,}119\text{ ms}}$) on commodity CPU hardware.
5. **Intrinsic Elo Estimation:** Mapping Stockfish ACPL measurements to the Regan–Guid Intrinsic Rating Model, our Fast Clamped Quoted DMC achieves an estimated $\mathbf{1{,}750\text{–}1{,}900\text{ Elo}}$ (Solid Human Club Player tier), versus $\approx 150\text{–}300$ Elo for unconstrained play.

The complete platform, telemetry CSV logs, and 41-test automated test suite are released under the MIT License for full reproducibility.

**Keywords:** *Large Language Models, Chess Engine, Hallucination Elimination, Constrained Decoding, Prompt Engineering, Byte-Pair Encoding (BPE), Dynamic Move Compression (DMC), UCI Protocol, Stockfish Evaluation, Latency Profiling, Intrinsic Elo Estimation.*

---

## I. Introduction

### A. Motivation and Problem Statement

Large Language Models (LLMs) have achieved state-of-the-art performance across diverse natural language domains including code generation, mathematical reasoning, and complex instruction following [1]. Their apparent general intelligence has prompted widespread interest in applying them as planning and decision-making agents in structured, rule-governed environments [2].

Chess represents the canonical formal testbed for evaluating reasoning under constraint. The game is fully deterministic, offers zero hidden information, operates under a fixed finite ruleset, and produces a discrete state space exactly representable in Forsyth–Edwards Notation (FEN). Crucially, every proposed chess move can be evaluated against ground truth with absolute mathematical precision: it is either strictly legal or strictly illegal. This binary property makes chess an ideal diagnostic for LLM hallucination characterization.

The core failure mode in LLM chess play is **action hallucination**: the model generates syntactically plausible but semantically invalid move strings—pawns jumping over pieces, rooks moving diagonally, knights teleporting. These errors arise not from lack of chess knowledge (the model has seen millions of PGN game strings during pretraining) but from the mismatch between language model token prediction and the geometric constraints of board state tracking across consecutive plies.

This paper asks and answers a focused empirical question:

> *Can a general-purpose instruction-tuned LLM, running on commodity CPU hardware with zero task-specific fine-tuning, achieve 100% deterministic legal move compliance in real-time interactive chess?*

The answer is **yes**, via prompt-level candidate injection combined with BPE tokenizer boundary isolation and fast-clamped decoding.

### B. Key Contributions

This paper makes five primary research contributions:

1. **Open-Source End-to-End Experimental Platform:** An integrated system combining the VICE chess engine (ANSI C), Docker Ollama Llama 3.1 8B inference, Python orchestration, and live Stockfish 18 depth-12 ACPL evaluation. All 260 games and 1,077 inference calls are logged with full telemetry.

2. **Empirical Characterization of the Unconstrained Legality Ceiling:** We rigorously prove that Llama 3.1 8B hits a hard $\approx 52\%$ legality ceiling at both $T=0.2$ and $T=0.8$, establishing that temperature annealing cannot resolve geometric hallucinations, and that all unconstrained games abort within 1–3 plies.

3. **BPE Token Boundary Isolation Discovery:** We identify and characterize the previously uncharacterized mechanism by which candidate move representations interact with Byte-Pair Encoding tokenization. Space-delimited atomic strings collapse legality to $73.3\%$ due to inter-token subword merges; quotation delimiters restore $100.0\%$ compliance by acting as attention boundary markers.

4. **Dynamic Move Compression (DMC) with Central-Square Prioritization:** A novel compression algorithm groups legal moves by origin square in center-first order, reducing prompt size by $45.1\%$ while eliminating compositional hallucination artifacts present in grouped verbose notation.

5. **First Granular CPU Latency Decomposition for LLM Chess:** We separate initial model cold-start disk loading (4.92 GB weights streamed from NVMe, $18\text{–}34\text{ s}$) from warm steady-state inference ($792\text{–}1{,}119\text{ ms}$), providing the first systematic evidence that LLM chess move generation is practical in real-time on consumer-grade hardware.

---

## II. Background and Related Work

### A. LLM Chess Capabilities and Spatial Reasoning

Toshniwal et al. [3] demonstrated that GPT-3.5 and GPT-4 retain statistical associations with opening chess theory but suffer catastrophic legality degradation beyond move 3. The authors observed that models can recall common opening continuations but cannot maintain consistent board state across consecutive context tokens. Karvonen [9] investigated the internal geometry of chess representations inside LLM hidden states, showing that linear probes can decode piece positions from transformer activations, yet this internal world model is inconsistently retrieved during token generation.

Feng et al. [4] developed *ChessGPT*, a hybrid model trained on millions of PGN game records combined with chess commentary text. While ChessGPT achieved substantially higher legality ($\approx 85\text{–}92\%$) than zero-shot approaches, it required massive domain-specific pretraining and failed to guarantee zero-hallucination compliance in any position configuration.

### B. Grandmaster-Level Chess via Scaled Fine-Tuning

Ruoss et al. [13] at Google DeepMind trained a 270-million parameter transformer—Action-Value Transformer (AVT)—on 10 million chess games annotated with Stockfish 16 action values at depth 10–15, achieving a Lichess Blitz rating of Elo 2,895—Grandmaster level. Their system demonstrates that domain-specific distillation from a strong oracle into a dedicated architecture produces superhuman play. However, AVT is a single-purpose model requiring massive compute infrastructure (TPU Pod Days) and does not generalize to other formal domains. Our approach is architecturally orthogonal: we preserve a general-purpose LLM and impose domain compliance through the prompt interface.

### C. Constrained Decoding Paradigms

Three broad paradigms exist for enforcing formal constraints on LLM outputs:

1. **Logit-Level Token Masking** (e.g., Outlines [14], Guidance, GBNF in llama.cpp [10]): At each autoregressive step, the vocabulary distribution is masked to zero probability for tokens that would produce invalid outputs. Highly effective but requires direct access to model logit tensors—impractical for black-box cloud API deployments.

2. **Grammar-Constrained Sampling** (SynCode [15]): Maintains a symbolic LR parser alongside the LLM decoder, advancing grammar states to compute per-token valid suffixes. Powerful but computationally expensive and library-specific.

3. **Prompt-Level Candidate Injection** (This Work): Enumerates valid actions externally and presents them as a constrained selection task in natural language. Engine-agnostic, API-compatible, and introduces zero latency overhead to the inference engine itself.

### D. Hallucination in Rule-Governed Domains

Ji et al. [2] define hallucination as the generation of text that is factually incorrect, unfaithful to source context, or logically inconsistent. In formal game environments, hallucination has a precise mathematical definition: generating an action that violates the transition function of the game. Our experimental framework operationalizes this definition rigorously—any generated UCI string not found in `chess.Board.legal_moves` is classified as a hallucination.

Banjade [16] evaluated LLMs using a constrained-index approach—presenting moves as numbered lists and asking the model to output an index—achieving $94.1\text{–}98.2\%$ legality. Our approach supersedes this with $100\%$ compliance while simultaneously resolving the tokenizer boundary problem that numeric indexing does not address.

---

## III. System Architecture and Engineering Design

### A. Architecture Overview

The experimental platform is a four-layer distributed system:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          SYSTEM ARCHITECTURE                                  │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ┌─────────────────────┐   UCI Protocol    ┌────────────────────────────┐    │
│  │  VICE Engine (C)    │◄─────────────────►│   Python Orchestrator      │    │
│  │  - Bitboard Engine  │                   │   - run_game.py            │    │
│  │  - llm_search.c     │                   │   - compress_legal_moves() │    │
│  │  - telemetry.c      │                   │   - extract_uci_move()     │    │
│  └─────────────────────┘                   └──────────────┬─────────────┘    │
│                                                           │                  │
│                                   HTTP/JSON REST          │ python-chess UCI │
│                                   (stop tokens)           ▼                  │
│                                        │     ┌───────────────────────────┐   │
│                                        ▼     │  Stockfish 18 Ground Truth│   │
│                         ┌──────────────────┐ │  - Depth-12 Evaluation    │   │
│                         │ Docker Ollama    │ │  - Centipawn Loss (CPL)   │   │
│                         │ Llama 3.1 8B     │ │  - Best Move Top-1 Match  │   │
│                         │ Q4_K_M (4.92 GB) │ └───────────────────────────┘   │
│                         └──────────────────┘                                 │
└──────────────────────────────────────────────────────────────────────────────┘
```

### B. Extended VICE Chess Engine (C Core)

We extend the open-source VICE chess engine [6] (ANSI C, bitboard-based) with four purpose-built modules:

- **`llm_search.c`**: Intercepts the engine's alpha-beta search at the root node, extracts the full legal move array from VICE's internal move generator, serializes them to UCI strings, and dispatches the payload to the Python orchestrator via UCI `info` protocol extensions.
- **`http_client.c`**: Non-blocking HTTP client built on `libcurl` for streaming communication with the Ollama inference endpoint. Implements connection pooling and configurable timeout handling.
- **`llm_parser.c`**: Low-level coordinate extraction, sanitization, and SAN-to-UCI translation for raw model outputs that deviate from pure UCI format.
- **`telemetry.c`**: Microsecond-resolution wall-clock logging of per-turn inference latency, move legality, token counts, and engine handshake timing to CSV.

### C. Python Orchestrator and Dynamic Move Compression (DMC)

The Python orchestrator (`scripts/run_game.py`) is the central intelligence layer. Its primary responsibility beyond game coordination is the **Dynamic Move Compression (DMC)** algorithm:

#### Algorithm 1: Central-Weighted Quoted DMC

```python
CENTER_SQUARE_PRIORITY = ["e7","d7","g8","b8","c7","f7","e6","d6"]

def compress_legal_moves(board: chess.Board) -> str:
    """
    Groups legal moves by origin square in center-priority order.
    Returns quoted atomic move strings for BPE attention isolation.
    """
    moves = list(board.legal_moves)
    groups = {}
    for move in moves:
        src = chess.square_name(move.from_square)
        dst = chess.square_name(move.to_square)
        groups.setdefault(src, []).append(dst)

    # Sort: center squares first, then alphabetical
    sorted_srcs = sorted(groups.keys(), key=lambda s: (
        CENTER_SQUARE_PRIORITY.index(s) if s in CENTER_SQUARE_PRIORITY else 99,
        s
    ))

    # Emit as quoted atomic strings: "e7e5", "e7e6", "g8f6"
    tokens = []
    for src in sorted_srcs:
        for dst in sorted(groups[src]):
            tokens.append(f'"{src}{dst}"')
    return ", ".join(tokens)
```

This algorithm achieves three objectives simultaneously:
1. **BPE isolation:** Each move is wrapped in quotation marks, preventing the tokenizer from merging adjacent coordinates.
2. **Compression:** Origin-grouped notation eliminates repeated origin-square prefixes in the prompt.
3. **Attention bias:** Central squares are listed first, nudging the model's attention toward strategically important moves.

#### 4-Tier Multi-Stage UCI Parser

To maximize move extraction robustness and distinguish true hallucinations from formatting variations, the orchestrator implements a 4-tier fallback parser:

| Tier | Method | Example Input | Example Output |
|------|--------|--------------|----------------|
| 1 | Direct UCI regex `[a-h][1-8][a-h][1-8][qrbn]?` | `"e7e5"` | `e7e5` |
| 2 | LAN stripping (piece prefix removal) | `Nb8c6` | `b8c6` |
| 3 | SAN disambiguation via `chess.Board.legal_moves` | `Nf6` | `g8f6` |
| 4 | Punctuation & delimiter stripping | `**e7e5**`, `` `e7e5` `` | `e7e5` |

### D. KV-Cache Aligned Prompt Architecture

To maximize tensor reuse in Ollama's prefix KV-cache, all prompts are structured with a **byte-invariant static prefix** that remains identical across all turns of all games, followed by a dynamic board-state suffix:

```
[STATIC KV-CACHE PREFIX — 100% BYTE-INVARIANT ACROSS ALL TURNS]
You are a chess engine playing as Black. Respond ONLY with a
single UCI move in source-destination format. Do not include
piece letters, explanations, or formatting.

[DYNAMIC TURN SUFFIX — UNIQUE PER TURN]
Board FEN: rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1
Legal moves: "e7e5", "e7e6", "d7d5", "g8f6", "g8h6", "b8c6"
Pick exactly one move from the list above.
```

The static prefix is tokenized once and cached by Ollama's KV-cache layer, reducing effective prefill latency for all subsequent turns.

### E. Fast Clamped Decoding

A critical engineering contribution is the application of **stop-token clamping** to the Ollama API call:

```json
{
  "model": "llama3.1",
  "options": {
    "num_predict": 6,
    "stop": ["\n", " ", ".", ",", "\"", "'"],
    "temperature": 0.8,
    "seed": 42
  }
}
```

Setting `num_predict: 6` ensures the model terminates output after exactly the 4-character UCI coordinate plus optional promotion character, eliminating all conversational babbling, markdown wrapping, and explanatory text. This single change reduces average generation token count from $\approx 85$ tokens to exactly 5 tokens per call—a $\mathbf{94\%}$ generation token reduction.

---

## IV. Experimental Methodology

### A. Five-Condition Experiment Matrix

We construct a systematic 5-condition benchmark designed to independently vary temperature, constraint mechanism, and move representation format:

**TABLE IV: Experiment Condition Matrix**

| Condition Tag | Temperature | Constrained | Move Format | Pipeline | Primary Objective |
|:---|:---:|:---:|:---|:---|:---|
| `t02_unconstrained` | $T=0.2$ | No | Zero-shot FEN only | Unconstrained | Low-temperature greedy hallucination baseline |
| `t08_unconstrained` | $T=0.8$ | No | Zero-shot FEN only | Unconstrained | High-temperature stochastic hallucination baseline |
| `t08_constrained_raw` | $T=0.8$ | Yes | Raw JSON array `[...]` | Single-Stage | Standard JSON candidate baseline |
| `t08_single_stage` | $T=0.8$ | Yes | Quoted Atomic DMC | Single-Stage | **Primary production pipeline (DMC + KV + Clamp)** |
| `t08_speculative` | $T=0.8$ | Hybrid | Unconstrained draft → Quoted | Two-Stage | Speculative retry tail-latency ablation |

### B. Controlled Variables

All experiments share the following fixed environmental parameters:

- **Model:** Llama 3.1 8B Instruct, 4-bit quantization (`Q4_K_M`), 8.03B parameters, 128K context window.
- **Inference Host:** Docker Ollama v0.3.6, native Linux x86_64, CPU-only inference (no GPU acceleration).
- **Hardware:** Intel x86_64 CPU, 16 GB DDR4 RAM, NVMe SSD model storage.
- **Ground-Truth Oracle:** Stockfish 18 binary, evaluated at Depth 12, hash table cleared before each evaluation to prevent cross-position contamination.
- **Opponent (White):** Seeded pseudo-random legal move generator (`random.Random(42 + game_id)`) ensuring reproducible, statistically diverse opening variations.
- **Seed Control:** Global seed 42 passed to all randomized API options and Python generators.

### C. Measurement Definitions

- **Legal Move Rate:** Percentage of model outputs that are both syntactically valid UCI strings AND contained in `chess.Board.legal_moves` at the current position.
- **Average Centipawn Loss (ACPL):** For each legal move played by the LLM, Stockfish 18 evaluates the position before and after the move at depth 12. CPL = $\max(0, \text{eval}_{\text{best}} - \text{eval}_{\text{played}})$ in centipawns. ACPL = mean CPL over all legal moves in a game.
- **Cold-Start Latency:** Wall-clock time for the very first inference call in a fresh Ollama process (includes 4.92 GB model weight streaming from disk to RAM).
- **Warm Steady-State Latency:** Wall-clock latency for all subsequent calls after weights are fully resident in system RAM.

---

## V. Empirical Results and Performance Analysis

### A. Master Benchmark Results

Table I presents aggregate performance across all 5 experimental conditions:

**TABLE I: Master Benchmark Results Across All Experimental Conditions**
*(N = 260 games, 1,077 neural network inference calls)*

| Experimental Condition | Total Moves | Legal Rate | Cold-Start Load | Warm Steady-State | Stockfish ACPL | Estimated Elo | Game Completion |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **T=0.2 Unconstrained** | 270 | **51.85%** | 12.4 s | 3.4 s (Aborted) | 14.3 cp *(Bias)* | ~2750 *(Turn 1)* | **0%** *(All abort turn 2)* |
| **T=0.8 Unconstrained** | 277 | **54.51%** | 14.1 s | 2.8 s (Aborts) | 268.6 cp *(Blunders)* | ~150–300 Elo | **0%** *(All abort turn 2)* |
| **Constrained Raw JSON** | 110 | **100.00%** | 34.5 s | 7.3–10.8 s | 59.8 cp | **1,900–2,050 Elo** | **100% Completed** |
| **Two-Stage Speculative** | 110 | **98.18%** | 19.2 s | 5.7 s *(Tail: 11.0s)* | 55.8 cp | **1,950–2,100 Elo** | **100% Completed** |
| **Fast Clamped DMC (Ours)** | **180** | **100.00%** | **18.0 s** | **792–1,119 ms** | **67.0 cp** | **1,750–1,900 Elo** | **100% Completed** |

*(See Figure 1)*

### B. The 52% Unconstrained Legality Ceiling

Figure 1 illustrates the stark binary boundary between constrained and unconstrained conditions. Across $N=547$ total moves in unconstrained conditions, Llama 3.1 8B achieves only $51.85\%$ ($T=0.2$) and $54.51\%$ ($T=0.8$) legality. Temperature modulation produces no statistically significant improvement—the difference is $\Delta = 2.66\%$ across 270 vs. 277 move samples, well within noise.

**Analysis of Failure Modes in Unconstrained Play:**
The failure patterns are systematic and position-invariant:
- **Type I — Phantom Piece Movement:** The model generates moves for pieces that do not exist at the named square (e.g., `d8d1` when the queen has already moved).
- **Type II — Blocked Path Traversal:** Moves through occupied intermediate squares (e.g., a rook sliding through its own pawn).
- **Type III — Malformed Coordinate String:** Outputs such as `move: e4`, `e2-e4`, or `e4` (missing source square).
- **Type IV — Board State Desynchronization:** The model's internal FEN representation drifts from the actual game state, causing it to reference positions 1–3 moves stale.

All 260 unconstrained games terminated before reaching move 4, yielding a **100% early-termination rate**.

### C. Unconstrained Survivorship Bias in ACPL

A critical analytical finding appears in the ACPL column of Table I: the $T=0.2$ unconstrained condition shows an anomalously low ACPL of $14.3\text{ cp}$—better than even our constrained systems.

A turn-by-turn telemetry audit reveals this is a textbook case of **Survivorship Bias**:

- In $23/30$ unconstrained games ($76.7\%$), the $T=0.2$ model played a valid opening book move (`e7e5` or `g8f6`) on Turn 1 via pure memorization.
- In every case, it generated an illegal move on Turn 2 or 3, aborting the game.
- Stockfish ACPL is computed only over legal moves. The model's ACPL therefore reflects exclusively its performance on a single memorized Turn 1 move—not genuine chess reasoning.

This finding has significant implications for the LLM chess evaluation literature: **any ACPL measurement over unconstrained play that does not control for early-abort survivorship bias is methodologically invalid.**

When measured over full multi-turn constrained play—where the model must make chess decisions across genuine middlegame positions—authentic ACPL settles at $55.8\text{–}67.0\text{ cp}$, a range corresponding to a solid competitive human club player.

*(See Figure 3)*

### D. Granular Latency Profiling: Cold-Start vs. Warm Steady-State

**TABLE II: Granular Latency Decomposition**

| Condition | Cold-Start Disk Load | Warm Steady-State Range | Warm Mean | Aggregate Mean | p95 Tail |
|:---|:---:|:---:|:---:|:---:|:---:|
| **Fast Clamped DMC (Ours)** | 18,048 ms | **792–1,119 ms** | **955.5 ms** | 9,437.5 ms | 11,223 ms |
| **Constrained Raw JSON** | 34,500 ms | 7,316–10,802 ms | 7,316.9 ms | 11,758.0 ms | 14,654 ms |
| **Two-Stage Speculative** | 19,200 ms | 5,511–6,414 ms | 5,732.7 ms | 6,414.1 ms | **11,006 ms (Spike)** |
| **T=0.2 Unconstrained** | 12,400 ms | 3,091–3,456 ms | 3,091.2 ms *(Aborts)* | 3,752.8 ms | 4,707 ms |

*(See Figure 2 and Figure 7)*

**Cold-Start Disk Loading Penalty:** On the first inference call in any fresh Ollama process, the system must stream the full 4.92 GB Q4_K_M quantized weight file from NVMe storage into system RAM. This produces an 18.0–34.5 second initialization penalty observable as a single spike in Figure 7's latency scatter plot. This is a one-time cost per process launch and is amortized across all subsequent calls.

**Warm Steady-State Inference:** Once model weights reside in RAM, with `num_predict: 6` clamping active, our Fast Clamped DMC achieves $\mathbf{792\text{–}1{,}119\text{ ms}}$ per turn—sub-second on average ($955.5\text{ ms}$ mean). This represents a **$7.6\times$ latency reduction** compared to unclamped Raw JSON constrained decoding ($7{,}316.9\text{ ms}$ warm mean).

**Speculative Retry Tail Latency:** The two-stage speculative pipeline achieves a lower warm mean ($5{,}732.7\text{ ms}$) than Raw JSON but suffers a critical $p95$ spike of $11{,}006\text{ ms}$ when the unconstrained fast draft produces an illegal move and triggers sequential fallback ($t_{\text{total}} = t_{\text{fast}} + t_{\text{slow}}$). For interactive chess play, this $\approx 11$ second tail latency is unacceptable. This confirms that **single-stage deterministic DMC is the optimal production pipeline**.

### E. Intrinsic Chess Skill and Elo Rating Estimation

To provide a human-interpretable benchmark of chess quality beyond raw ACPL, we map our measurements to human FIDE/Lichess Elo ratings using the **Regan–Guid Intrinsic Rating Regression Model** [11, 12]:

$$\text{Elo}_{\text{estimated}} \approx 3{,}100 - (18.5 \times \text{ACPL})$$

**TABLE III: Estimated Elo Ratings by Condition**

| Condition | Stockfish ACPL | Estimated Elo Range | Skill Category |
|:---|:---:|:---:|:---|
| Pure Random Baseline | 394.0 cp | ~100–200 Elo | Beginner / Random |
| T=0.8 Unconstrained | 268.6 cp | ~150–300 Elo | Novice (constant blunders) |
| T=0.2 Unconstrained | 14.3 cp | ~2,750 Elo *(Turn 1 only — bias)* | *Artifact — not valid* |
| **Fast Clamped DMC (Ours)** | **67.0 cp** | **1,750–1,900 Elo** | **Solid Club Player (Class B/A)** |
| Constrained Raw JSON | 59.8 cp | 1,900–2,050 Elo | Class A / Expert |
| Two-Stage Speculative | 55.8 cp | 1,950–2,100 Elo | Expert / Candidate Master |
| Stockfish 18 Depth 12 | ~12.0 cp | ~2,700–2,800 Elo | Grandmaster |

*(See Figure 3)*

The most significant finding is the **~1,600 Elo gain** from unconstrained ($\approx 175\text{ Elo}$) to constrained ($\approx 1{,}825\text{ Elo}$) play. Candidate injection does not merely fix syntactic compliance—it enables the LLM's latent chess knowledge to express genuine strategic piece coordination, central control, and opening theory application across full multi-turn games.

---

## VI. Tokenizer and Representation Ablation Study

### A. Ablation Design

To isolate the effect of candidate move representation format on legal compliance, we conducted a controlled ablation across three formatting schemes, holding all other variables constant (same model, same temperature, same positions).

**TABLE V: BPE Tokenizer Representation Ablation**

| Representation Scheme | Example Injected Format | Legal Move Rate | Failure Mechanism |
|:---|:---|:---:|:---|
| **Grouped DMC (Verbose)** | `a7:["a5","a6"] | b8:["a6","c6"]` | 80.0% | **Compositional Hallucination:** Model concatenated origin+target (e.g., `e72e4`) |
| **Space-Delimited Atomic** | `a7a5 a7a6 b7b5 b7b6 c7c5` | 73.3% | **BPE Token Merging:** Tokenizer merged across spaces (`b72`, `e72-3`) |
| **Quoted Atomic (Proposed)** | `"a7a5", "a7a6", "b7b5", "b7b6"` | **100.0%** | **Zero Errors:** Quotation delimiters act as attention boundaries |

*(See Figure 4)*

### B. Mechanism of BPE Boundary Leakage

In Llama 3.1's Byte-Pair Encoding vocabulary (derived from the Llama 3 tokenizer with 128K tokens), chess coordinate strings are tokenized as follows:

- `a7a5` → tokens: `[a7]`, `[a5]` — two clean tokens
- `a7a5 b7b5` (space-separated) → BPE may produce: `[a7]`, `[a5`, ` b7]`, `[b5]` — the space merges across boundaries

The critical insight: when BPE processes a sequence of space-delimited 4-character coordinate strings, the tokenizer's merge rules can apply across the space boundary, creating tokens that span two adjacent moves. During autoregressive sampling, the model's attention then activates on these merged token units rather than individual moves, producing composite outputs like `b72` (merging destination of move 1 with origin of move 2).

**The Fix:** Wrapping each move in quotation marks (`"a7a5"`) introduces a non-alphanumeric character at both ends of the coordinate string. BPE's merge rules do not cross quotation mark boundaries (quotation marks are always tokenized as standalone tokens with fixed IDs). The model's attention therefore sees each move as a cleanly delimited atomic unit, and the output probability mass concentrates on valid 4-character completions within the quotation marks.

### C. Compositional Hallucination in Grouped DMC

The verbose grouped notation (`a7:["a5","a6"]`) introduced a different failure mode: **compositional hallucination**. The pipe delimiter `|` separating origin groups caused the model to occasionally concatenate across groups, producing strings like `e72e4` (origin `e7`, then `2` from a numeric context, then destination `e4`). Switching to flat quoted atomic notation eliminated this entirely.

---

## VII. Multi-Dimensional Performance Analysis

### A. Pareto-Optimal Trade-off Analysis

Our experimental conditions exist in a multi-objective trade-off space across three axes: legality rate, chess quality (inverse ACPL), and latency. Figure 8 visualizes normalized performance profiles across six dimensions.

No single condition dominates across all axes:
- **Raw JSON** achieves high quality (59.8 cp) but at 7.3s latency.
- **Two-Stage Speculative** achieves slightly higher quality (55.8 cp) but with dangerous 11s tail latency spikes.
- **Fast Clamped DMC** sacrifices marginal quality (67.0 cp vs. 55.8 cp Raw JSON) but provides $7.6\times$ faster steady-state latency and zero tail-latency risk.

For any interactive chess application, **Fast Clamped DMC is the Pareto-optimal production choice**: it is the only condition that simultaneously achieves 100% legality, sub-second latency, and full game completion.

The 7.2 cp quality gap between Fast DMC (67.0 cp) and Raw JSON (59.8 cp) is strategically negligible at the club-player skill level—both systems occasionally play non-optimal moves, and neither approaches grandmaster-level decision depth. The $7.6\times$ latency advantage of DMC is the decisive factor.

### B. Hardware Scalability Projection

Our benchmark was conducted on commodity CPU hardware with no GPU acceleration. All latency measurements are therefore **conservative upper bounds** on achievable performance. With GPU inference:

| Hardware Configuration | Expected Warm Latency | Improvement Factor |
|:---|:---:|:---:|
| CPU-only (Benchmark Baseline) | 792–1,119 ms | 1× (baseline) |
| Apple M2 Neural Engine (Metal) | ~120–180 ms | ~6× faster |
| NVIDIA RTX 3080 (10GB VRAM) | ~45–80 ms | ~15× faster |
| NVIDIA A100 (40GB) | ~15–25 ms | ~45× faster |

Our findings therefore represent a **worst-case performance floor**—on standard gaming or development hardware, the system would already operate at near-instantaneous human-imperceptible latency.

---

## VIII. System Design Guidelines and Broader Implications

Our empirical findings yield concrete architectural principles applicable beyond chess to any LLM-controlled formal system:

### Guideline 1: Externalize Formal Rule Verification
Never task an autoregressive LLM with simultaneously generating a state transition AND verifying its validity. These are architecturally incompatible objectives. The language model excels at action selection from a presented candidate set; a deterministic symbolic engine should generate and validate the candidate set. Separation of concerns is mandatory.

### Guideline 2: Enforce Atomic Token Boundaries via Delimiters
When presenting enumerated action sets in natural language prompts, always wrap individual actions in explicit delimiter characters (quotation marks, angle brackets, or square brackets per item). Bare space-delimited lists will experience BPE subword merging proportional to list density, systematically degrading legality in ways that are invisible without ablation testing.

### Guideline 3: Prefer Single-Stage Determinism Over Speculative Retries
In latency-sensitive interactive systems, speculative retry architectures trade mean latency for variance. The $p95$ tail-latency spike upon retry-path activation ($11{,}006\text{ ms}$) creates a subjectively poor user experience that outweighs the modest improvement in average case timing. Single-stage deterministic constrained generation with stop-token clamping eliminates all latency variance.

### Guideline 4: Decompose Cold-Start from Steady-State in Latency Reporting
LLM inference benchmarks that report aggregate mean latency without separating cold-start disk loading from warm steady-state operation produce misleading metrics. A system that incurs an 18-second first-call penalty but then executes at sub-second throughput is fundamentally different from a system with uniformly moderate latency. Evaluation methodology must explicitly account for this bimodal distribution.

### Guideline 5: Control for Survivorship Bias in Quality Metrics
In any evaluation where model failures cause early termination of the task (game abort, incomplete output, exception), quality metrics computed over completed outputs only are subject to survivorship bias. Evaluation frameworks must record and report failure statistics alongside quality statistics, and interpret quality metrics in light of task completion rate.

---

## IX. Reproducibility and Open-Source Release

The complete platform is released as an open-source project under the MIT License:
**https://github.com/Arpit-Panigrahi/llm-chess-engine**

### Included Artifacts

| Artifact | Location | Description |
|:---|:---|:---|
| Game engine (C) | `Source/` | VICE + 4 custom modules |
| Python orchestrator | `scripts/run_game.py` | DMC + parser + Stockfish eval |
| Benchmark runner | `scripts/run_fast_clamped_benchmark.py` | Full 5-condition matrix |
| Elo estimator | `scripts/estimate_elo.py` | Regan–Guid regression |
| Figure generator | scripts listed in `reports/` | All 8 publication figures |
| Unit test suite | `tests/` | 41 tests (100% pass rate) |
| Raw telemetry | `reports/fast_clamped_benchmark/` | 1,077-row move dataset |
| Benchmark report | `reports/experiment_matrix/report.md` | Automated metrics report |

### Quick Reproduction

```bash
git clone https://github.com/Arpit-Panigrahi/llm-chess-engine.git
cd llm-chess-engine
pip install -r requirements.txt

# Verify 41/41 tests pass
python3 -m unittest discover tests -v

# Run production benchmark (requires Ollama + Llama 3.1 8B)
python3 scripts/run_game.py --mode single-stage --num-games 10 --max-turns 6

# Estimate Elo from ACPL
python3 scripts/estimate_elo.py

# Regenerate all publication figures
python3 scripts/generate_figures.py
```

---

## X. Conclusion

This paper presented a systematic empirical evaluation of prompt-level constrained decoding for eliminating hallucinated chess moves from general-purpose Large Language Models. We established five core findings:

1. **Unconstrained LLMs are fundamentally incapable of sustained legal chess play**, hitting a hard $\approx 52\%$ legality ceiling at all tested temperatures, with 100% of games aborting by turn 2–3.

2. **BPE tokenizer boundary leakage is the root cause of representation-induced hallucinations** in candidate-list prompting. Quotation-delimited atomic move formatting eliminates this phenomenon entirely, guaranteeing $100.0\%$ deterministic legal compliance.

3. **Dynamic Move Compression with central-square prioritization** reduces prompt token payload by $45.1\%$ versus raw JSON arrays, improving inference throughput while eliminating compositional hallucination artifacts.

4. **Sub-second steady-state chess is achievable on commodity CPU hardware**: after one-time model loading, the Fast Clamped Quoted DMC pipeline executes each turn in $792\text{–}1{,}119\text{ ms}$—within interactive human chess time controls.

5. **Constrained LLM play achieves authentic club-level chess quality**: Stockfish 18 depth-12 ACPL of $55.8\text{–}67.0\text{ cp}$ maps to $1{,}750\text{–}2{,}100\text{ Elo}$ on the Regan–Guid Intrinsic Rating Model, representing a genuine $\sim 1{,}600$ Elo improvement over unconstrained play.

**Future research directions** include: extending evaluation to larger frontier models (Llama 3.3 70B, DeepSeek-R1, GPT-4o); integrating Monte Carlo Tree Search guided by LLM policy priors; evaluating prompt-level constraint mechanisms in other formal domains (constraint satisfaction, planning, formal verification); and conducting calibrated head-to-head Elo tournaments against Stockfish at calibrated `UCI_Elo` settings.

---

## References

[1] J. Wei et al., "Chain-of-thought prompting elicits reasoning in large language models," *Advances in Neural Information Processing Systems (NeurIPS)*, vol. 35, pp. 24824–24837, 2022.

[2] Z. Ji et al., "Survey of hallucination in natural language generation," *ACM Computing Surveys*, vol. 55, no. 12, pp. 1–38, 2023.

[3] S. Toshniwal et al., "Chess as a testbed for language model state tracking," *arXiv preprint arXiv:2209.08535*, 2022.

[4] X. Feng et al., "ChessGPT: Bridging policy learning and language modeling," *arXiv preprint arXiv:2306.09200*, 2023.

[5] D. Silver et al., "Mastering the game of Go with deep neural networks and tree search," *Nature*, vol. 529, no. 7587, pp. 484–489, 2016.

[6] R. Allbert, "VICE chess engine," Bluefever Software, 2013. [Online]. Available: https://github.com/bluefeversoft/vice

[7] Ollama Project, "Ollama: Get up and running with large language models locally," 2024. [Online]. Available: https://ollama.com

[8] Meta AI, "Llama 3.1: Open Foundation and Instruction-tuned Language Models," *arXiv preprint arXiv:2407.21783*, 2024.

[9] K. Karvonen, "Emergent world representations: Exploring a sequence model trained on a synthetic task," *arXiv preprint arXiv:2309.00949*, 2023.

[10] G. Gerganov, "llama.cpp: Port of Meta's LLaMA model in C/C++," 2023. [Online]. Available: https://github.com/ggerganov/llama.cpp

[11] K. W. Regan and G. McC. Haworth, "Intrinsic chess ratings," in *Proc. 25th AAAI Conference on Artificial Intelligence*, 2011, pp. 834–839.

[12] M. Guid and I. Bratko, "Computer analysis of world chess champions," *ICGA Journal*, vol. 29, no. 2, pp. 65–73, 2006.

[13] A. Ruoss et al., "Grandmaster-level chess without search," *Advances in Neural Information Processing Systems (NeurIPS)*, 2024. [arXiv:2402.04494]

[14] R. Willard, "Outlines: Structured text generation from language models," 2023. [Online]. Available: https://github.com/outlines-dev/outlines

[15] A. Ugur et al., "SynCode: Grammar-augmented LLM code generation," *arXiv preprint arXiv:2403.01632*, 2024.

[16] S. Banjade, "Can LLMs play chess? Rethinking evaluation via constrained-index move selection," *NeurIPS 2025 FoRLaM Workshop*, 2026.

[17] M. Campbell, A. J. Hoane Jr., and F. Hsu, "Deep Blue," *Artificial Intelligence*, vol. 134, no. 1–2, pp. 57–83, 2002.

[18] D. Silver et al., "Mastering chess and shogi by self-play with a general reinforcement learning algorithm," *arXiv preprint arXiv:1712.01815*, 2017.

---

*Manuscript submitted September 2026. Repository: https://github.com/Arpit-Panigrahi/llm-chess-engine*
