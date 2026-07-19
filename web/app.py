"""
Flask web application for the LLM Chess Engine.
Converts the Tkinter-based GUI into a browser-based interface.
"""

import os
import sys
import csv
import random
import uuid
from datetime import datetime

import json
from flask import Flask, render_template, jsonify, request

# Add parent directory to path so we can access project data
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chess
import chess.engine

app = Flask(__name__)
# In production, set the SECRET_KEY environment variable for persistent sessions.
# The fallback random key is sufficient for local development but resets on restart.
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24).hex())

# --- Configuration ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_PATH = os.path.join(PROJECT_ROOT, "Source", "vice")
LLM_ENGINE_ENABLED = os.environ.get("LLM_ENGINE_ENABLED", "").lower() in {"1", "true", "yes", "on"}

# In-memory game store (keyed by game_id)
games = {}


# ── Helper Functions ──────────────────────────────────────────

def get_board_state(board):
    """Return a JSON-serializable representation of the board."""
    pieces = {}
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece:
            col = chess.square_file(sq)
            row = chess.square_rank(sq)
            pieces[chess.square_name(sq)] = {
                "symbol": piece.symbol(),
                "color": "white" if piece.color == chess.WHITE else "black",
            }

    return {
        "fen": board.fen(),
        "pieces": pieces,
        "turn": "white" if board.turn == chess.WHITE else "black",
        "legal_moves": [m.uci() for m in board.legal_moves],
        "is_game_over": board.is_game_over(),
        "result": board.result() if board.is_game_over() else None,
        "is_check": board.is_check(),
        "is_checkmate": board.is_checkmate(),
        "is_stalemate": board.is_stalemate(),
        "fullmove_number": board.fullmove_number,
    }


def try_engine_move(board):
    """
    Try to get a move from the VICE engine.
    Falls back to a random legal move if the engine is unavailable.
    Returns (move, engine_name, hallucination_detected).
    """
    # Try the VICE engine first (only when explicitly enabled)
    if LLM_ENGINE_ENABLED and os.path.exists(ENGINE_PATH):
        try:
            engine = chess.engine.SimpleEngine.popen_uci(ENGINE_PATH)
            try:
                result = engine.play(board, chess.engine.Limit(time=5.0))
                move = result.move
                engine.quit()
                return move, "vice-llm", False
            except chess.engine.EngineError as e:
                engine.quit()
                return None, "vice-llm", True
        except Exception:
            pass

    # Fallback: random legal move
    legal_moves = list(board.legal_moves)
    if legal_moves:
        engine_name = "random"
        if not LLM_ENGINE_ENABLED:
            engine_name = "random (LLM disabled)"
        return random.choice(legal_moves), engine_name, False
    return None, "none", False


def load_research_data():
    """Load research data dynamically from runs/ directory."""
    research_log = []
    hallucinations = []

    runs_dir = os.path.join(PROJECT_ROOT, "runs")
    if not os.path.isdir(runs_dir):
        return research_log, hallucinations

    # Find all run directories
    run_entries = []
    for entry in os.listdir(runs_dir):
        run_path = os.path.join(runs_dir, entry)
        if os.path.isdir(run_path):
            raw_path = os.path.join(run_path, "raw_outputs.jsonl")
            if os.path.isfile(raw_path):
                run_entries.append((entry, raw_path))

    # Sort runs chronologically (latest first)
    run_entries.sort(reverse=True)

    # Load records from raw_outputs.jsonl of all runs
    for run_id, raw_path in run_entries:
        try:
            with open(raw_path, "r") as f:
                for line in f:
                    try:
                        record = json.loads(line.strip())
                        # Map to research log format
                        research_log.append({
                            "timestamp": record.get("timestamp", ""),
                            "fen": record.get("fen", ""),
                            "temperature": str(record.get("temperature", "")),
                            "latency_ms": str(record.get("latency_ms", "")),
                            "move": record.get("extracted_move", ""),
                            "is_legal": str(record.get("is_legal", "")),
                            "fallback_used": str(record.get("fallback_used", "")),
                        })
                        # If illegal, map to hallucination log format
                        if record.get("is_legal") == 0:
                            hallucinations.append({
                                "Timestamp": record.get("timestamp", ""),
                                "Game_Number": str(record.get("game_id", "")),
                                "Turn_Number": str(record.get("turn_number", "")),
                                "FEN": record.get("fen", ""),
                                "Error_Message": f"Illegal move: '{record.get('extracted_move')}' (raw: '{record.get('raw_response')}')",
                            })
                    except (json.JSONDecodeError, KeyError):
                        continue
        except Exception:
            continue

    # Limit to latest 500 entries to prevent page bloat
    return research_log[:500], hallucinations[:500]


# ── Routes ────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the main chess game page."""
    return render_template("index.html")


@app.route("/research")
def research():
    """Serve the research data visualization page."""
    research_log, hallucinations = load_research_data()

    # Compute summary stats
    total = len(research_log)
    legal_count = sum(1 for r in research_log if r["is_legal"] == "1")
    illegal_count = total - legal_count
    success_rate = (legal_count / total * 100) if total > 0 else 0

    stats = {
        "total_calls": total,
        "legal_moves": legal_count,
        "illegal_moves": illegal_count,
        "success_rate": round(success_rate, 1),
        "total_hallucinations": len(hallucinations),
    }

    return render_template(
        "research.html",
        stats=stats,
        research_log=research_log[:100],  # Limit to latest 100 for performance
        hallucinations=hallucinations[:50],
    )


# ── API Endpoints ─────────────────────────────────────────────

@app.route("/api/new-game", methods=["POST"])
def new_game():
    """Start a new chess game."""
    game_id = str(uuid.uuid4())[:8]
    board = chess.Board()

    games[game_id] = {
        "board": board,
        "history": [],
        "hallucinations": [],
        "start_time": datetime.now().isoformat(),
    }

    state = get_board_state(board)
    state["game_id"] = game_id
    return jsonify(state)


@app.route("/api/move", methods=["POST"])
def make_move():
    """Handle a player's move."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    game_id = data.get("game_id")
    move_uci = data.get("move")

    if not game_id or not move_uci:
        return jsonify({"error": "Missing game_id or move"}), 400

    game = games.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    board = game["board"]

    if board.is_game_over():
        state = get_board_state(board)
        state["game_id"] = game_id
        return jsonify(state)

    try:
        move = chess.Move.from_uci(move_uci)

        # Check if the move is legal; try promotion to queen if not
        if move not in board.legal_moves:
            promo_move = chess.Move.from_uci(move_uci + "q")
            if promo_move in board.legal_moves:
                move = promo_move
            else:
                return jsonify({"error": "Illegal move"}), 400

        board.push(move)
        game["history"].append(move.uci())

        state = get_board_state(board)
        state["game_id"] = game_id
        state["last_move"] = move.uci()
        return jsonify(state)

    except ValueError as e:
        return jsonify({"error": f"Invalid move format: {e}"}), 400


@app.route("/api/engine-move", methods=["POST"])
def engine_move():
    """Get the engine's response move."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    game_id = data.get("game_id")
    game = games.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    board = game["board"]

    if board.is_game_over():
        state = get_board_state(board)
        state["game_id"] = game_id
        return jsonify(state)

    move, engine_name, hallucination = try_engine_move(board)

    if hallucination:
        game["hallucinations"].append({
            "fen": board.fen(),
            "turn": board.fullmove_number,
            "timestamp": datetime.now().isoformat(),
        })

    if move and move in board.legal_moves:
        board.push(move)
        game["history"].append(move.uci())

    state = get_board_state(board)
    state["game_id"] = game_id
    state["engine_move"] = move.uci() if move else None
    state["engine_name"] = engine_name
    state["hallucination"] = hallucination
    return jsonify(state)


@app.route("/api/game-state", methods=["GET"])
def game_state():
    """Get current game state."""
    game_id = request.args.get("game_id")
    game = games.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    state = get_board_state(game["board"])
    state["game_id"] = game_id
    state["history"] = game["history"]
    state["hallucinations"] = game["hallucinations"]
    return jsonify(state)


@app.route("/api/undo", methods=["POST"])
def undo_move():
    """Undo the last move (or last two for a full turn)."""
    data = request.get_json()
    game_id = data.get("game_id") if data else None
    game = games.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    board = game["board"]

    # Undo engine's move and player's move (one full turn)
    moves_undone = 0
    while board.move_stack and moves_undone < 2:
        board.pop()
        if game["history"]:
            game["history"].pop()
        moves_undone += 1

    state = get_board_state(board)
    state["game_id"] = game_id
    return jsonify(state)


@app.route("/api/research-stats", methods=["GET"])
def research_stats():
    """Return research statistics as JSON."""
    research_log, hallucinations = load_research_data()

    total = len(research_log)
    legal = sum(1 for r in research_log if r["is_legal"] == "1")

    # Condition breakdown
    conditions = {
        "t02_unconstrained": {"total": 0, "legal": 0},
        "t08_unconstrained": {"total": 0, "legal": 0},
        "t08_constrained": {"total": 0, "legal": 0}
    }

    # Re-read raw data to classify by constrained_decoding flag
    runs_dir = os.path.join(PROJECT_ROOT, "runs")
    if os.path.isdir(runs_dir):
        for entry in os.listdir(runs_dir):
            run_path = os.path.join(runs_dir, entry)
            if os.path.isdir(run_path):
                raw_path = os.path.join(run_path, "raw_outputs.jsonl")
                if os.path.isfile(raw_path):
                    try:
                        with open(raw_path, "r") as f:
                            for line in f:
                                try:
                                    record = json.loads(line.strip())
                                    temp = record.get("temperature", 0.0)
                                    constrained = record.get("constrained_decoding", False)
                                    is_legal = record.get("is_legal", 0)

                                    if temp == 0.2 and not constrained:
                                        key = "t02_unconstrained"
                                    elif temp == 0.8 and not constrained:
                                        key = "t08_unconstrained"
                                    elif temp == 0.8 and constrained:
                                        key = "t08_constrained"
                                    else:
                                        continue

                                    conditions[key]["total"] += 1
                                    if is_legal == 1:
                                        conditions[key]["legal"] += 1
                                except Exception:
                                    continue
                    except Exception:
                        continue

    return jsonify({
        "total_calls": total,
        "legal_moves": legal,
        "illegal_moves": total - legal,
        "success_rate": round(legal / total * 100, 1) if total > 0 else 0,
        "total_hallucinations": len(hallucinations),
        "conditions": conditions,
    })


# ── Main ──────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("  LLM Chess Engine — Web Interface")
    print("=" * 50)
    print(f"  Engine path: {ENGINE_PATH}")
    print(f"  Engine available: {os.path.exists(ENGINE_PATH)}")
    print(f"  LLM engine enabled: {LLM_ENGINE_ENABLED}")
    print(f"  Starting on http://127.0.0.1:5000")
    print("=" * 50)
    app.run(debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true",
            host="127.0.0.1", port=5000)
