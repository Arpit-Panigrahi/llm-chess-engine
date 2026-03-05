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

from flask import Flask, render_template, jsonify, request

# Add parent directory to path so we can access project data
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chess
import chess.engine

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24).hex())

# --- Configuration ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE_PATH = os.path.join(PROJECT_ROOT, "Source", "vice")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
HALLUCINATION_CSV = os.path.join(DATA_DIR, "llm_hallucinations.csv")
RESEARCH_LOG_CSV = os.path.join(DATA_DIR, "llm_research_log.csv")

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
    # Try the VICE engine first
    if os.path.exists(ENGINE_PATH):
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
        return random.choice(legal_moves), "random", False
    return None, "none", False


def load_research_data():
    """Load research data from CSV files for the research page."""
    research_log = []
    hallucinations = []

    # Load research log
    if os.path.exists(RESEARCH_LOG_CSV):
        with open(RESEARCH_LOG_CSV, "r") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 7:
                    research_log.append({
                        "timestamp": row[0],
                        "fen": row[1],
                        "temperature": row[2],
                        "latency_ms": row[3],
                        "move": row[4],
                        "is_legal": row[5],
                        "fallback_used": row[6],
                    })

    # Load hallucination log
    if os.path.exists(HALLUCINATION_CSV):
        with open(HALLUCINATION_CSV, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                hallucinations.append(row)

    return research_log, hallucinations


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

    # Session breakdown
    sessions = {"T1": {"total": 0, "legal": 0}, "T2": {"total": 0, "legal": 0}, "T3": {"total": 0, "legal": 0}}
    for r in research_log:
        temp = r.get("temperature", "")
        try:
            temp_val = float(temp)
        except (ValueError, TypeError):
            continue

        if temp_val == 0.1:
            sessions["T1"]["total"] += 1
            if r["is_legal"] == "1":
                sessions["T1"]["legal"] += 1
        elif temp_val == 0.8:
            # Simple heuristic — later entries are T3
            if sessions["T2"]["total"] < 200:
                sessions["T2"]["total"] += 1
                if r["is_legal"] == "1":
                    sessions["T2"]["legal"] += 1
            else:
                sessions["T3"]["total"] += 1
                if r["is_legal"] == "1":
                    sessions["T3"]["legal"] += 1

    return jsonify({
        "total_calls": total,
        "legal_moves": legal,
        "illegal_moves": total - legal,
        "success_rate": round(legal / total * 100, 1) if total > 0 else 0,
        "total_hallucinations": len(hallucinations),
        "sessions": sessions,
    })


# ── Main ──────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("  LLM Chess Engine — Web Interface")
    print("=" * 50)
    print(f"  Engine path: {ENGINE_PATH}")
    print(f"  Engine available: {os.path.exists(ENGINE_PATH)}")
    print(f"  Data dir: {DATA_DIR}")
    print(f"  Starting on http://127.0.0.1:5000")
    print("=" * 50)
    app.run(debug=True, host="127.0.0.1", port=5000)
