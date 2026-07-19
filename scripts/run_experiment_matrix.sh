#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# run_experiment_matrix.sh — Run the mandatory 3-condition experiment matrix
#
# Conditions:
#   1. t02_unconstrained  — temp=0.2, no legal-move constraint
#   2. t08_unconstrained  — temp=0.8, no legal-move constraint
#   3. t08_constrained    — temp=0.8, with legal-move constraint
#
# All conditions use the same model, seed, and game count for fairness.
#
# Usage:
#   bash scripts/run_experiment_matrix.sh
#   bash scripts/run_experiment_matrix.sh --num-games 100
#   bash scripts/run_experiment_matrix.sh --skip-preflight
# ──────────────────────────────────────────────────────────────

set -euo pipefail

# ── Defaults (override via args) ─────────────────────────────
MODEL="${LLM_MODEL:-llama3}"
SEED="${LLM_SEED:-42}"
NUM_GAMES="${NUM_GAMES:-50}"
OLLAMA_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"
EXTRA_ARGS=""

# Parse optional overrides
MAX_TURNS="${MAX_TURNS:-200}"
while [[ $# -gt 0 ]]; do
    case $1 in
        --num-games)    NUM_GAMES="$2"; shift 2 ;;
        --model)        MODEL="$2"; shift 2 ;;
        --seed)         SEED="$2"; shift 2 ;;
        --ollama-url)   OLLAMA_URL="$2"; shift 2 ;;
        --max-turns)    MAX_TURNS="$2"; shift 2 ;;
        --early-termination) EXTRA_ARGS="$EXTRA_ARGS --early-termination"; shift ;;
        --skip-preflight) EXTRA_ARGS="$EXTRA_ARGS --skip-preflight"; shift ;;
        --help|-h)
            echo "Usage: bash scripts/run_experiment_matrix.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --num-games N       Games per condition (default: 50)"
            echo "  --model NAME        Ollama model (default: llama3)"
            echo "  --seed N            Random seed (default: 42)"
            echo "  --ollama-url URL    Ollama server URL"
            echo "  --max-turns N       Maximum half-moves (ply) per game (default: 200)"
            echo "  --early-termination Abort game immediately on first hallucination (GUI style)"
            echo "  --skip-preflight    Skip connectivity check"
            echo "  --help              Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "============================================================"
echo "  LLM Chess Engine — Experiment Matrix"
echo "============================================================"
echo "  Model:     $MODEL"
echo "  Seed:      $SEED"
echo "  Games:     $NUM_GAMES per condition"
echo "  Ollama:    $OLLAMA_URL"
echo "  Conditions: 3 (t02_unconstrained, t08_unconstrained, t08_constrained)"
echo "============================================================"

# ── Preflight (once) ─────────────────────────────────────────
echo ""
echo "🔍 Running environment check..."
python3 "$SCRIPT_DIR/check_ollama_env.py" --url "$OLLAMA_URL" --model "$MODEL" || {
    echo ""
    echo "✗ Environment check failed. Fix the issues above before running the matrix."
    echo "  Or use --skip-preflight to bypass (not recommended)."
    if [[ "$EXTRA_ARGS" == *"--skip-preflight"* ]]; then
        echo "  (--skip-preflight set, continuing anyway...)"
    else
        exit 1
    fi
}

# ── Condition 1: temp=0.2, unconstrained ─────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  CONDITION 1/3: t02_unconstrained (Temp=0.2, No Constraint)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 "$SCRIPT_DIR/run_game.py" \
    --temperature 0.2 \
    --no-constrained-decoding \
    --seed "$SEED" \
    --model "$MODEL" \
    --ollama-url "$OLLAMA_URL" \
    --num-games "$NUM_GAMES" \
    --max-turns "$MAX_TURNS" \
    --tag t02_unconstrained \
    $EXTRA_ARGS

# ── Condition 2: temp=0.8, unconstrained ─────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  CONDITION 2/3: t08_unconstrained (Temp=0.8, No Constraint)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 "$SCRIPT_DIR/run_game.py" \
    --temperature 0.8 \
    --no-constrained-decoding \
    --seed "$SEED" \
    --model "$MODEL" \
    --ollama-url "$OLLAMA_URL" \
    --num-games "$NUM_GAMES" \
    --max-turns "$MAX_TURNS" \
    --tag t08_unconstrained \
    $EXTRA_ARGS

# ── Condition 3: temp=0.8, constrained ───────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  CONDITION 3/3: t08_constrained (Temp=0.8, Constrained)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 "$SCRIPT_DIR/run_game.py" \
    --temperature 0.8 \
    --constrained-decoding \
    --seed "$SEED" \
    --model "$MODEL" \
    --ollama-url "$OLLAMA_URL" \
    --num-games "$NUM_GAMES" \
    --max-turns "$MAX_TURNS" \
    --tag t08_constrained \
    $EXTRA_ARGS

# ── Generate Report ──────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  GENERATING ANALYSIS REPORT"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 "$SCRIPT_DIR/analyze_all.py" \
    --run-root "$PROJECT_ROOT/runs" \
    --out "$PROJECT_ROOT/reports/experiment_matrix" \
    --tags t02_unconstrained t08_unconstrained t08_constrained

echo ""
echo "============================================================"
echo "  ✅ EXPERIMENT MATRIX COMPLETE"
echo "============================================================"
echo "  Results: reports/experiment_matrix/"
echo "    • report.md            — Full comparison report"
echo "    • metrics_comparison.csv — Tabular metrics"
echo "    • plots/               — Visualization charts"
echo "============================================================"
