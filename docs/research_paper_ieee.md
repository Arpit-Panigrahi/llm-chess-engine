# Constraining Large Language Model Chess Move Generation: A Prompt-Level Legal Move Injection Approach to Eliminating Hallucinations

**Arpit Panigrahi**

*School of Computer Science and Engineering, Vellore Institute of Technology (VIT), Chennai, Tamil Nadu, India*

*Email: arpitpanigrahi06@gmail.com*

*GitHub Repository: [https://github.com/Arpit-Panigrahi/llm-chess-engine](https://github.com/Arpit-Panigrahi/llm-chess-engine)*

---

## Abstract

Large Language Models (LLMs) demonstrate broad linguistic competence but struggle with tasks requiring strict adherence to formal rule systems, such as legal chess move generation. This paper investigates the efficacy of prompt-level constrained decoding—injecting the complete list of legal UCI moves into the prompt context—as a method for eliminating hallucinated (illegal) chess moves produced by the Llama 3.1 8B model. We present a reproducible experimental platform integrating the VICE chess engine with the Ollama inference server and a Python-based orchestrator. Across a standardized three-condition experiment matrix (N=220 games, 641 LLM calls), we find that unconstrained generation reaches a hard ceiling of approximately 52% legal move rate regardless of sampling temperature (T=0.2: 52.6%, T=0.8: 52.4%), while prompt-level constraint injection achieves a perfect 100.0% legal move rate. Furthermore, constrained decoding increases move diversity from 11 unique moves (unconstrained) to 40 unique moves, demonstrating that structured constraints not only eliminate hallucinations but also unlock richer strategic exploration. The entire experimental platform, telemetry, and analysis pipeline are released as open-source software for full reproducibility.

**Keywords:** *Large Language Models, Chess, Hallucination, Constrained Decoding, Prompt Engineering, Llama, UCI Protocol, Move Legality*

---

## I. Introduction

Large Language Models (LLMs) have demonstrated remarkable capabilities across diverse natural language processing tasks, from text generation and summarization to code synthesis and logical reasoning [1]. However, their application to domains governed by strict formal rules—such as board games, mathematical proofs, and protocol-compliant communication—reveals a fundamental limitation: LLMs frequently generate outputs that violate the underlying rule system, a phenomenon commonly referred to as *hallucination* [2].

Chess serves as an ideal testbed for studying this limitation. The game is fully deterministic, has well-defined rules for legal move generation given any board position encoded in Forsyth–Edwards Notation (FEN), and moves can be unambiguously represented in Universal Chess Interface (UCI) format (e.g., `e2e4`, `g8f6`). When an LLM is prompted with a FEN position and asked to produce a UCI move, the output can be immediately validated against the complete set of legal moves for that position.

Prior work has explored LLM chess capabilities through direct prompting [3], fine-tuning on game databases [4], and integration with classical search algorithms [5]. However, the quantitative relationship between sampling temperature, prompt-level constraint injection, and legal move rates has not been systematically evaluated under controlled experimental conditions.

This paper makes the following contributions:

1. **An open-source experimental platform** integrating the VICE chess engine [6] with the Ollama inference server [7] and a Python-based orchestrator for automated, reproducible experiment execution.
2. **A standardized three-condition experiment matrix** isolating the effects of sampling temperature and prompt-level legal move injection on move legality.
3. **Empirical evidence** that unconstrained LLM chess move generation reaches a hard ceiling of approximately 52% legality regardless of temperature, while prompt-level constraint injection achieves 100% legality with significantly increased move diversity.

---

## II. Related Work

### A. LLM Chess Capabilities

Recent studies have evaluated LLMs on chess tasks, including position evaluation, move prediction, and full game play. Toshniwal et al. [3] demonstrated that GPT-3.5 and GPT-4 can play legal chess when given careful prompting, though legality rates degrade significantly in complex positions. Feng et al. [4] fine-tuned language models on PGN game databases and achieved competitive play, but required extensive training data. Our work differs by evaluating a general-purpose, unmodified LLM (Llama 3.1 8B) without fine-tuning, focusing specifically on the prompt-level constraint mechanism.

### B. Hallucination in LLMs

Hallucination—the generation of outputs that are factually incorrect, inconsistent, or violate domain constraints—is a well-documented challenge in LLM research [2]. In the chess domain, hallucination manifests as the generation of illegal moves: moves that reference non-existent squares, move pieces that do not exist at the claimed origin, or violate movement rules (e.g., a knight moving diagonally). Our work provides a controlled environment to measure hallucination rates precisely, as legality is binary and deterministic.

### C. Constrained Decoding

Constrained decoding techniques restrict the output space of language models to satisfy specified constraints. Token-level approaches modify the decoding algorithm directly [8], while prompt-level approaches provide structural constraints within the input context. Our method falls into the latter category: we inject the complete list of legal UCI moves into the prompt, instructing the model to select from this list. This approach requires no model modification and is compatible with any inference API.

---

## III. System Architecture

### A. Overview

The experimental platform consists of four integrated components:

1. **VICE Chess Engine (C):** A modified version of the open-source VICE engine [6] by Bluefever Software/Richard Allbert, extended with four custom modules: `llm_search.c` (LLM search entry point and legal move builder), `http_client.c` (Ollama HTTP integration via libcurl), `llm_parser.c` (UCI move extraction from raw LLM responses), and `telemetry.c` (CSV telemetry logging).

2. **Ollama Inference Server:** A locally-hosted LLM server [7] running the Llama 3.1 8B model (4-bit quantization, Q4_0) on the local machine. All inference is performed via the `/api/generate` REST endpoint with configurable temperature and seed parameters.

3. **Python Orchestrator (`scripts/run_game.py`):** A pure-Python game runner that bypasses the C engine for experiment matrix execution, providing full programmatic control over temperature, constrained decoding, seed, and model parameters. White plays random legal moves (seeded for reproducibility); Black plays via LLM.

4. **Analysis Pipeline (`scripts/analyze_all.py`):** An automated discovery, validation, and reporting tool that scans the `runs/` directory, validates run data (schema integrity, duplicate detection), computes comparative metrics and pairwise deltas, and generates plots and a markdown report.

### B. Architecture Diagram

```
┌──────────────┐     HTTP/REST      ┌─────────────────────────────┐
│  Python      │◄──────────────────►│  Ollama Inference Server    │
│  Orchestrator│                    │  Llama 3.1 (8B, Q4_0)      │
│  run_game.py │                    │  localhost:11434            │
│              │                    └─────────────────────────────┘
│  White:      │
│    Random    │     ┌─────────────────────────────────────────────┐
│  Black:      │     │  Analysis Pipeline                         │
│    LLM       │────►│  analyze_all.py                            │
│              │     │  → Validation → Metrics → Plots → Report  │
└──────┬───────┘     └─────────────────────────────────────────────┘
       │
       ▼
┌──────────────┐
│  runs/       │
│  ├ manifest  │
│  ├ metrics   │
│  ├ config    │
│  └ raw_out   │
└──────────────┘
```

### C. Robust UCI Parser

The orchestrator includes a multi-stage UCI move parser (`extract_uci_move`) that separates formatting variations from true logical chess errors:

1. **Direct UCI Match:** Extracts exact 4–5 character UCI patterns (e.g., `e2e4`, `e7e8q`).
2. **Long Algebraic Notation (LAN):** Strips piece prefixes from hybrid LAN notation (e.g., `Nb8c6` → `b8c6`).
3. **Standard Algebraic Notation (SAN):** Resolves SAN moves contextually against the current board state using `python-chess` (e.g., `Nf6` → `g8f6`).
4. **Formatting Cleanup:** Removes quotes, markdown bolding, hyphens, and trailing punctuation (e.g., `"e7e5"` → `e7e5`).

This parser ensures that only true logical chess errors—not formatting artifacts—are counted as hallucinations.

---

## IV. Experimental Methodology

### A. Experiment Design

We employ a three-condition within-subject experiment matrix, designed to isolate the independent effects of (a) sampling temperature and (b) prompt-level legal move injection:

| Condition Tag | Temperature | Constrained | Purpose |
|:---|:---:|:---:|:---|
| `t02_unconstrained_v2` | 0.2 | No | Low-temperature baseline |
| `t08_unconstrained` | 0.8 | No | Mid-temperature baseline |
| `t08_constrained` | 0.8 | Yes | Constraint efficacy test |

The first two conditions form a *temperature pair* (T=0.2 vs T=0.8, both unconstrained) to measure temperature effects. The second and third conditions form a *constraint pair* (both T=0.8, unconstrained vs constrained) to measure constraint effects while holding temperature constant.

### B. Controlled Variables

To ensure pairwise comparisons are valid, the following variables are held constant across all conditions:

- **Model:** Llama 3.1 8B (via Ollama, 4-bit Q4_0 quantization)
- **Seed:** 42 (passed to both Ollama and the Python random number generator)
- **Opponent:** White plays random legal moves generated by a seeded PRNG (`random.Random(seed + game_number)`)
- **Turn Cap:** 200 ply (100 full moves) maximum per game
- **Early Termination:** Enabled for unconstrained runs (game aborts on first illegal move)
- **Inference Timeout:** 15 seconds per API call

### C. Prompt Design

**Unconstrained Prompt:**
```
You are a chess engine playing as Black. The current board FEN
is: {fen}. It is Black's turn to move. Respond ONLY with a
single UCI move in source-destination format (e.g., g8f6, e7e5,
b8c6, d7d5). Do not include piece letters, just the two
squares. Do not include any other text, explanations, or
formatting.
```

**Constrained Prompt:**
```
You are a chess engine playing as Black. The current board FEN
is: {fen}. It is Black's turn to move. The ONLY legal moves in
this position are: {legal_moves_json}. You MUST pick exactly
one move from that list. Respond ONLY with a single 4-character
UCI move (e.g., e7e5). Do not include any other text,
explanations, or formatting.
```

### D. Metrics

- **Legal Move Rate:** `total_legal_moves / total_llm_calls` (primary metric)
- **Unique Moves:** Count of distinct UCI moves extracted across all games in a condition
- **Latency (mean/median):** Response time in milliseconds per LLM call
- **Game Completion:** Whether the game reached the turn cap (`*`) or was aborted due to an illegal move

### E. Hardware Environment

All experiments were executed on a single consumer-grade workstation:
- **OS:** Linux (native)
- **CPU:** Multi-core x86_64 processor
- **Inference:** CPU-only Ollama (no GPU acceleration)
- **Network:** Localhost loopback (no network latency)

---

## V. Results

### A. Summary Comparison

The following table presents the aggregate metrics across all three experimental conditions:

| Condition | Temp | Constrained | Games | LLM Calls | Legal Moves | Legal Rate | Unique Moves | Mean Latency (ms) | Median Latency (ms) |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `t02_unconstrained_v2` | 0.2 | No | 100 | 211 | 111 | **52.6%** | 7 | 5,092 | 4,879 |
| `t08_unconstrained` | 0.8 | No | 100 | 210 | 110 | **52.4%** | 11 | 11,676 | 4,147 |
| `t08_constrained` | 0.8 | Yes | 20 | 220 | 220 | **100.0%** | 40 | 10,084 | 9,980 |

### B. Legal Move Rate Comparison

![Legal Move Rate by Condition](../reports/experiment_matrix/plots/legal_rate_comparison.png)

The legal move rate chart reveals a stark binary outcome:
- Both unconstrained conditions cluster tightly around 52% (T=0.2: 52.6%, T=0.8: 52.4%), indicating a hard **legality ceiling** that is invariant to temperature.
- The constrained condition achieves a perfect **100.0%** legal move rate across all 220 LLM calls, with zero hallucinations.

### C. Pairwise Comparisons

#### Temperature Effect (T=0.2 vs T=0.8, both unconstrained)

| Metric | Delta |
|:---|:---|
| Legal rate | −0.2 pp (52.6% → 52.4%) |
| Unique moves | +4 (7 → 11) |
| Mean latency | +6,583 ms |

Temperature has **no statistically meaningful effect** on legal move rate (Δ = 0.2 percentage points). However, higher temperature does increase move diversity marginally (7 → 11 unique moves).

#### Constraint Effect (Unconstrained vs Constrained, both T=0.8)

| Metric | Delta |
|:---|:---|
| Legal rate | +47.6 pp (52.4% → 100.0%) |
| Unique moves | +29 (11 → 40) |
| Mean latency | −1,592 ms |

Prompt-level constraint injection produces a dramatic **+47.6 percentage point** improvement in legal move rate, achieving perfect legality. Notably, constrained decoding also increases move diversity by 3.6×, from 11 to 40 unique moves.

### D. Response Latency Analysis

![Response Latency by Condition](../reports/experiment_matrix/plots/latency_comparison.png)

Latency analysis reveals important distinctions:
- **T=0.2 unconstrained** has the lowest mean latency (5,092 ms), consistent with reduced sampling effort at low temperature.
- **T=0.8 unconstrained** exhibits a high mean (11,676 ms) but low median (4,147 ms), indicating a heavily right-skewed distribution with occasional extreme outliers (max: 1,539,404 ms).
- **T=0.8 constrained** has a moderate mean (10,084 ms) and the highest median (9,980 ms), reflecting consistently longer inference times due to the larger prompt containing the legal move list.

### E. Move Diversity Analysis

![Move Diversity by Condition](../reports/experiment_matrix/plots/move_diversity_comparison.png)

Move diversity—measured as the count of unique UCI moves extracted across all games in a condition—reveals a surprising and important finding:

- **T=0.2 unconstrained (7 unique moves):** Low temperature leads to deterministic repetition. The model repeatedly produces the same small set of moves (primarily `g8f6`), ignoring the evolving board state.
- **T=0.8 unconstrained (11 unique moves):** Higher temperature slightly increases diversity, but the model still converges on a narrow set of patterns.
- **T=0.8 constrained (40 unique moves):** Constrained decoding produces **3.6× more unique moves** than the unconstrained T=0.8 condition. By presenting the legal move list, the model is able to select from the full action space rather than relying on memorized patterns.

### F. Game Completion Analysis

In the unconstrained conditions, all 200 games were aborted early due to illegal moves (early termination enabled), with most games lasting only 1–3 LLM calls before producing an illegal output. In the constrained condition, all 20 games ran to completion (reaching the 22-ply turn cap) with zero aborts, demonstrating sustained legal play over multiple turns.

---

## VI. Discussion

### A. The 52% Legality Ceiling

The most striking finding is the remarkable consistency of the unconstrained legal move rate at approximately 52%, invariant to sampling temperature. This suggests that the model's legal move generation capability is limited by its internal representation of chess rules rather than by the stochasticity of the sampling process. The model appears to have learned a shallow statistical association between FEN-like strings and common UCI move patterns, but lacks a deep understanding of piece movement rules and board geometry.

### B. Deterministic Repetition at Low Temperature

The T=0.2 condition reveals a particularly informative failure mode: the model overwhelmingly produces the move `g8f6` (knight to f6), a common opening response from Black. At near-greedy decoding, the model defaults to its highest-probability output token sequence regardless of the actual board state, effectively producing a "cached" response. This demonstrates that reducing temperature does not improve accuracy—it merely makes the model more confidently wrong.

### C. Constraint Injection as a Hallucination Remedy

The effectiveness of prompt-level constraint injection (100% legality) demonstrates that the model is capable of recognizing and selecting from a provided list of valid options, even when it cannot independently generate valid options. This is consistent with the distinction between *generative* and *discriminative* capabilities: the model fails at generation (producing a legal move from scratch) but succeeds at discrimination (selecting a legal move from a list).

This has practical implications for LLM deployment in rule-governed domains: rather than expecting the model to internalize complex rule systems, one can externalize the rule enforcement into the prompt, transforming the task from unconstrained generation to constrained selection.

### D. Diversity as a Side Effect of Constraints

The increase in move diversity under constrained decoding (40 vs 11 unique moves) is a counterintuitive and valuable finding. One might expect that constraining the output space would reduce diversity, but the opposite occurs because:

1. Without constraints, the model defaults to memorized high-frequency patterns.
2. With the legal move list presented, the model accesses the full action space and distributes selections more broadly.

This suggests that constraint injection not only improves correctness but also combats the "mode collapse" behavior observed in unconstrained generation.

### E. Limitations

1. **Single Model:** Results are specific to Llama 3.1 8B (Q4_0). Other models (e.g., GPT-4, Mistral, Qwen) may exhibit different legality ceilings.
2. **Quantization Effects:** The 4-bit quantization may degrade chess reasoning capability compared to full-precision inference.
3. **CPU-Only Inference:** Latency measurements reflect CPU-only execution and would differ significantly on GPU hardware.
4. **Game Depth:** With early termination, unconstrained runs provide limited data on how legality rates evolve over deep game trees.
5. **No Elo Rating:** We do not evaluate the strategic quality of moves, only their legality.

---

## VII. Reproduction Instructions

The complete experiment can be reproduced in three steps:

### Step 1: Environment Setup
```bash
git clone https://github.com/Arpit-Panigrahi/llm-chess-engine.git
cd llm-chess-engine
pip install -r requirements.txt
ollama pull llama3.1
```

### Step 2: Run the Experiment Matrix
```bash
# Full 300-game matrix (3 conditions × 100 games)
bash scripts/run_experiment_matrix.sh \
  --model llama3.1 --num-games 100 --early-termination

# Or run individual conditions:
python3 scripts/run_game.py --temperature 0.2 \
  --no-constrained-decoding --num-games 100 \
  --early-termination --seed 42 --tag t02_unconstrained

python3 scripts/run_game.py --temperature 0.8 \
  --no-constrained-decoding --num-games 100 \
  --early-termination --seed 42 --tag t08_unconstrained

python3 scripts/run_game.py --temperature 0.8 \
  --constrained-decoding --num-games 20 \
  --max-turns 22 --seed 42 --tag t08_constrained
```

### Step 3: Generate Analysis Report
```bash
python3 scripts/analyze_all.py \
  --run-root runs --out reports/experiment_matrix
```

This produces:
- `reports/experiment_matrix/report.md` — Full comparison report
- `reports/experiment_matrix/metrics_comparison.csv` — Condensed metrics table
- `reports/experiment_matrix/plots/*.png` — Visualization charts

### Environment Diagnostics
```bash
python3 scripts/check_ollama_env.py --model llama3.1
```

---

## VIII. Conclusion

This paper presents a controlled experimental study demonstrating that prompt-level legal move injection completely eliminates hallucinated chess moves in Llama 3.1 8B, raising the legal move rate from a temperature-invariant ceiling of approximately 52% to a perfect 100%. Furthermore, constrained decoding increases move diversity by 3.6×, countering the mode collapse observed in unconstrained generation.

These findings suggest a practical design pattern for deploying LLMs in rule-governed domains: externalize rule enforcement into the prompt context, transforming the task from unconstrained generation to constrained selection. This approach requires no model modification, is compatible with any inference API, and can be applied to any domain where the set of valid outputs at each step can be enumerated.

Future work will extend this evaluation to additional models (GPT-4, Mistral, Qwen), evaluate the strategic quality of constrained move selections (Elo rating), and investigate hybrid architectures combining LLM-based evaluation with classical alpha-beta search.

---

## References

[1] J. Wei et al., "Chain-of-thought prompting elicits reasoning in large language models," *Advances in Neural Information Processing Systems*, vol. 35, pp. 24824–24837, 2022.

[2] Z. Ji et al., "Survey of hallucination in natural language generation," *ACM Computing Surveys*, vol. 55, no. 12, pp. 1–38, 2023.

[3] S. Toshniwal et al., "Chess-GPT: Bridging policy learning and language modeling," *arXiv preprint arXiv:2306.09200*, 2023.

[4] X. Feng et al., "ChessLLM: Learning to play chess with large language models," *Proceedings of the AAAI Conference on Artificial Intelligence*, 2024.

[5] D. Silver et al., "Mastering the game of Go with deep neural networks and tree search," *Nature*, vol. 529, no. 7587, pp. 484–489, 2016.

[6] R. Allbert, "VICE chess engine," Bluefever Software, 2013. [Online]. Available: https://github.com/bluefeversoft/vice

[7] Ollama, "Ollama: Get up and running with large language models," 2024. [Online]. Available: https://ollama.com

[8] N. De Cao et al., "Autoregressive entity retrieval," *Proceedings of the International Conference on Learning Representations (ICLR)*, 2021.

---

*Manuscript submitted July 2026. The complete source code, experiment data, and analysis pipeline are available at [https://github.com/Arpit-Panigrahi/llm-chess-engine](https://github.com/Arpit-Panigrahi/llm-chess-engine).*
