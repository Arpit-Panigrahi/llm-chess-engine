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


# ── Cache for Research Data ──────────────────────────────────
_research_cache = {
    "last_loaded": 0,
    "log": [],
    "hallucinations": [],
    "conditions": {},
    "stats": {},
}


# ── Helper Functions ──────────────────────────────────────────

def get_board_state(board):
    """Return a JSON-serializable representation of the board."""
    pieces = {}
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece:
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


def try_engine_move(board, time_limit=5.0):
    """
    Try to get a move from the VICE engine.
    Falls back to a random legal move if the engine is unavailable.
    Returns (move, engine_name, hallucination_detected).
    """
    if LLM_ENGINE_ENABLED and os.path.exists(ENGINE_PATH):
        engine = None
        try:
            engine = chess.engine.SimpleEngine.popen_uci(ENGINE_PATH, timeout=10)
            result = engine.play(board, chess.engine.Limit(time=time_limit))
            return result.move, "vice-llm", False
        except chess.engine.EngineError:
            return None, "vice-llm", True
        except Exception:
            pass
        finally:
            if engine is not None:
                try:
                    engine.quit()
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


def load_research_data(force_reload=False):
    """Load research data dynamically from runs/ directory with caching."""
    global _research_cache
    now = datetime.now().timestamp()

    # Reuse cache if loaded within the last 15 seconds and not forced
    if not force_reload and (now - _research_cache["last_loaded"]) < 15 and _research_cache["log"]:
        return _research_cache["log"], _research_cache["hallucinations"], _research_cache["conditions"], _research_cache["stats"]

    research_log = []
    hallucinations = []
    conditions = {
        "t02_unconstrained": {"total": 0, "legal": 0},
        "t08_unconstrained": {"total": 0, "legal": 0},
        "t08_constrained": {"total": 0, "legal": 0}
    }

    runs_dir = os.path.join(PROJECT_ROOT, "runs")
    if os.path.isdir(runs_dir):
        run_entries = []
        for entry in os.listdir(runs_dir):
            run_path = os.path.join(runs_dir, entry)
            if os.path.isdir(run_path):
                raw_path = os.path.join(run_path, "raw_outputs.jsonl")
                if os.path.isfile(raw_path):
                    run_entries.append((entry, raw_path))

        run_entries.sort(reverse=True)

        for run_id, raw_path in run_entries:
            try:
                with open(raw_path, "r") as f:
                    for line in f:
                        line_str = line.strip()
                        if not line_str:
                            continue
                        try:
                            record = json.loads(line_str)
                            is_legal_val = record.get("is_legal", 0)
                            temp = record.get("temperature", 0.0)
                            constrained = record.get("constrained_decoding", False)

                            research_log.append({
                                "timestamp": record.get("timestamp", ""),
                                "fen": record.get("fen", ""),
                                "temperature": str(temp),
                                "latency_ms": str(record.get("latency_ms", "")),
                                "move": record.get("extracted_move", ""),
                                "is_legal": str(is_legal_val),
                                "fallback_used": str(record.get("fallback_used", "")),
                            })

                            if is_legal_val == 0:
                                hallucinations.append({
                                    "Timestamp": record.get("timestamp", ""),
                                    "Game_Number": str(record.get("game_id", "")),
                                    "Turn_Number": str(record.get("turn_number", "")),
                                    "FEN": record.get("fen", ""),
                                    "Error_Message": f"Illegal move: '{record.get('extracted_move')}' (raw: '{record.get('raw_response')}')",
                                })

                            if temp == 0.2 and not constrained:
                                cond_key = "t02_unconstrained"
                            elif temp == 0.8 and not constrained:
                                cond_key = "t08_unconstrained"
                            elif temp == 0.8 and constrained:
                                cond_key = "t08_constrained"
                            else:
                                cond_key = None

                            if cond_key:
                                conditions[cond_key]["total"] += 1
                                if is_legal_val == 1:
                                    conditions[cond_key]["legal"] += 1

                        except (json.JSONDecodeError, KeyError):
                            continue
            except Exception:
                continue

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

    _research_cache = {
        "last_loaded": now,
        "log": research_log,
        "hallucinations": hallucinations,
        "conditions": conditions,
        "stats": stats,
    }

    return research_log, hallucinations, conditions, stats


# ── Routes ────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the main chess game page."""
    return render_template("index.html")


@app.route("/research")
def research():
    """Serve the research data visualization page."""
    research_log, hallucinations, _, stats = load_research_data()

    return render_template(
        "research.html",
        stats=stats,
        research_log=research_log[:100],  # Limit to latest 100 for fast rendering
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
    """Handle a player's move with stateless FEN fallback for serverless."""
    data = request.get_json() or {}
    game_id = data.get("game_id")
    move_uci = data.get("move")
    client_fen = data.get("fen")

    if not move_uci:
        return jsonify({"error": "Missing move parameter"}), 400

    if not game_id:
        game_id = str(uuid.uuid4())[:8]

    game = games.get(game_id)
    if not game:
        # Stateless recovery: initialize board from client FEN or default startpos
        board = chess.Board(client_fen) if client_fen else chess.Board()
        game = {
            "board": board,
            "history": [],
            "hallucinations": [],
            "start_time": datetime.now().isoformat(),
        }
        games[game_id] = game
    else:
        board = game["board"]
        # If client passed a newer FEN, sync board
        if client_fen and board.fen() != client_fen:
            try:
                board = chess.Board(client_fen)
                game["board"] = board
            except Exception:
                pass

    if board.is_game_over():
        state = get_board_state(board)
        state["game_id"] = game_id
        return jsonify(state)

    try:
        move = chess.Move.from_uci(move_uci)

        # Check if the move is legal; try queen promotion if not specified
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
    """Get the engine's response move with stateless FEN fallback."""
    data = request.get_json() or {}
    game_id = data.get("game_id")
    client_fen = data.get("fen")

    if not game_id:
        game_id = str(uuid.uuid4())[:8]

    game = games.get(game_id)
    if not game:
        board = chess.Board(client_fen) if client_fen else chess.Board()
        game = {
            "board": board,
            "history": [],
            "hallucinations": [],
            "start_time": datetime.now().isoformat(),
        }
        games[game_id] = game
    else:
        board = game["board"]
        if client_fen and board.fen() != client_fen:
            try:
                board = chess.Board(client_fen)
                game["board"] = board
            except Exception:
                pass

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
    data = request.get_json() or {}
    game_id = data.get("game_id")
    client_fen = data.get("fen")

    game = games.get(game_id) if game_id else None
    if not game:
        if client_fen:
            board = chess.Board(client_fen)
            if board.move_stack:
                board.pop()
            state = get_board_state(board)
            state["game_id"] = game_id or str(uuid.uuid4())[:8]
            return jsonify(state)
        return jsonify({"error": "Game not found"}), 404

    board = game["board"]

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
    research_log, hallucinations, conditions, stats = load_research_data()

    return jsonify({
        "total_calls": stats["total_calls"],
        "legal_moves": stats["legal_moves"],
        "illegal_moves": stats["illegal_moves"],
        "success_rate": stats["success_rate"],
        "total_hallucinations": stats["total_hallucinations"],
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
