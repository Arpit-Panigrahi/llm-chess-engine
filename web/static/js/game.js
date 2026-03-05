/**
 * LLM Chess Engine — Client-side Game Logic
 * Handles board rendering, piece interaction, and API communication.
 */

// ── Unicode Piece Symbols ─────────────────────────────────────
const PIECE_SYMBOLS = {
    'P': '♙', 'N': '♘', 'B': '♗', 'R': '♖', 'Q': '♕', 'K': '♔',
    'p': '♟', 'n': '♞', 'b': '♝', 'r': '♜', 'q': '♛', 'k': '♚'
};

// ── Game State ────────────────────────────────────────────────
let gameState = {
    gameId: null,
    fen: null,
    pieces: {},
    turn: 'white',
    legalMoves: [],
    selectedSquare: null,
    isGameOver: false,
    result: null,
    history: [],
    flipped: false,
    engineThinking: false,
    lastMove: null,
};

// ── File/Rank Helpers ─────────────────────────────────────────
const FILES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'];
const RANKS = ['1', '2', '3', '4', '5', '6', '7', '8'];

function squareName(col, row) {
    return FILES[col] + RANKS[row];
}

// ── Board Rendering ───────────────────────────────────────────
function renderBoard() {
    const boardEl = document.getElementById('chess-board');
    boardEl.innerHTML = '';
    boardEl.classList.remove('thinking');

    if (gameState.engineThinking) {
        boardEl.classList.add('thinking');
    }

    for (let displayRow = 0; displayRow < 8; displayRow++) {
        for (let displayCol = 0; displayCol < 8; displayCol++) {
            const col = gameState.flipped ? 7 - displayCol : displayCol;
            const row = gameState.flipped ? displayRow : 7 - displayRow;
            const sq = squareName(col, row);
            const isLight = (col + row) % 2 === 0;

            const squareEl = document.createElement('div');
            squareEl.className = `square ${isLight ? 'dark' : 'light'}`;
            squareEl.dataset.square = sq;

            // Highlight selected square
            if (gameState.selectedSquare === sq) {
                squareEl.classList.add('selected');
            }

            // Highlight last move
            if (gameState.lastMove) {
                const from = gameState.lastMove.substring(0, 2);
                const to = gameState.lastMove.substring(2, 4);
                if (sq === from || sq === to) {
                    squareEl.classList.add('last-move');
                }
            }

            // Show legal move indicators
            if (gameState.selectedSquare) {
                const movesFromSelected = gameState.legalMoves.filter(
                    m => m.startsWith(gameState.selectedSquare)
                );
                const targetSquares = movesFromSelected.map(m => m.substring(2, 4));
                if (targetSquares.includes(sq)) {
                    const hasPiece = gameState.pieces[sq];
                    squareEl.classList.add(hasPiece ? 'legal-target-capture' : 'legal-target');
                }
            }

            // Add piece
            const piece = gameState.pieces[sq];
            if (piece) {
                const pieceEl = document.createElement('span');
                pieceEl.className = `piece ${piece.color}-piece`;
                pieceEl.textContent = PIECE_SYMBOLS[piece.symbol];
                squareEl.appendChild(pieceEl);
            }

            // Click handler
            squareEl.addEventListener('click', () => onSquareClick(sq));

            boardEl.appendChild(squareEl);
        }
    }
}

// ── Square Click Handler ──────────────────────────────────────
function onSquareClick(sq) {
    if (gameState.isGameOver || gameState.engineThinking) return;
    if (gameState.turn !== 'white') return;  // Only allow moves on White's turn

    if (gameState.selectedSquare === null) {
        // Select a piece
        const piece = gameState.pieces[sq];
        if (piece && piece.color === 'white') {
            gameState.selectedSquare = sq;
            renderBoard();
        }
    } else if (gameState.selectedSquare === sq) {
        // Deselect
        gameState.selectedSquare = null;
        renderBoard();
    } else {
        // Try to move
        const moveUci = gameState.selectedSquare + sq;

        // Check if this is a valid move destination
        const validMoves = gameState.legalMoves.filter(
            m => m.startsWith(gameState.selectedSquare) && m.substring(2, 4) === sq
        );

        if (validMoves.length > 0) {
            // Use the first valid move (handles promotions — defaults to queen)
            const move = validMoves[0];
            gameState.selectedSquare = null;
            makeMove(move);
        } else {
            // Try selecting a different piece
            const piece = gameState.pieces[sq];
            if (piece && piece.color === 'white') {
                gameState.selectedSquare = sq;
            } else {
                gameState.selectedSquare = null;
            }
            renderBoard();
        }
    }
}

// ── API Calls ─────────────────────────────────────────────────

async function newGame() {
    try {
        const res = await fetch('/api/new-game', { method: 'POST' });
        const data = await res.json();

        gameState.gameId = data.game_id;
        gameState.fen = data.fen;
        gameState.pieces = data.pieces;
        gameState.turn = data.turn;
        gameState.legalMoves = data.legal_moves;
        gameState.selectedSquare = null;
        gameState.isGameOver = false;
        gameState.result = null;
        gameState.history = [];
        gameState.engineThinking = false;
        gameState.lastMove = null;

        // Hide hallucination alert
        document.getElementById('hallucination-alert').style.display = 'none';

        updateUI();
        updateStatus('Your turn! Click a white piece to move.');
    } catch (err) {
        updateStatus('Error starting new game: ' + err.message);
    }
}

async function makeMove(moveUci) {
    try {
        const res = await fetch('/api/move', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ game_id: gameState.gameId, move: moveUci }),
        });

        if (!res.ok) {
            const err = await res.json();
            updateStatus('Invalid move: ' + (err.error || 'Unknown error'));
            return;
        }

        const data = await res.json();
        updateGameState(data);
        gameState.lastMove = data.last_move || moveUci;

        // Record move in history
        gameState.history.push({
            move: moveUci,
            color: 'white'
        });

        updateUI();

        if (data.is_game_over) {
            showGameOver(data.result);
            return;
        }

        // Trigger engine move
        gameState.engineThinking = true;
        updateStatus('Engine is thinking...');
        renderBoard();

        // Delay slightly for UX
        setTimeout(() => requestEngineMove(), 200);

    } catch (err) {
        updateStatus('Error making move: ' + err.message);
    }
}

async function requestEngineMove() {
    try {
        const res = await fetch('/api/engine-move', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ game_id: gameState.gameId }),
        });

        const data = await res.json();
        gameState.engineThinking = false;

        updateGameState(data);
        gameState.lastMove = data.engine_move;

        // Record engine move
        if (data.engine_move) {
            gameState.history.push({
                move: data.engine_move,
                color: 'black'
            });
        }

        // Update engine badge
        const badge = document.getElementById('engine-badge');
        badge.textContent = 'Engine: ' + (data.engine_name || 'unknown');

        // Check for hallucination
        if (data.hallucination) {
            showHallucination('The LLM attempted an illegal move! Falling back to random move.');
        } else {
            document.getElementById('hallucination-alert').style.display = 'none';
        }

        updateUI();

        if (data.is_game_over) {
            showGameOver(data.result);
            return;
        }

        updateStatus('Your turn! Click a white piece to move.');

    } catch (err) {
        gameState.engineThinking = false;
        updateStatus('Engine error: ' + err.message);
        renderBoard();
    }
}

async function undoMove() {
    if (!gameState.gameId) return;

    try {
        const res = await fetch('/api/undo', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ game_id: gameState.gameId }),
        });

        const data = await res.json();
        updateGameState(data);
        gameState.lastMove = null;
        gameState.selectedSquare = null;
        gameState.engineThinking = false;

        // Remove last two moves from history
        if (gameState.history.length >= 2) {
            gameState.history.pop();
            gameState.history.pop();
        } else {
            gameState.history = [];
        }

        updateUI();
        updateStatus('Move undone. Your turn!');
    } catch (err) {
        updateStatus('Error undoing move: ' + err.message);
    }
}

function flipBoard() {
    gameState.flipped = !gameState.flipped;
    renderBoard();
}

// ── UI Update Helpers ─────────────────────────────────────────

function updateGameState(data) {
    gameState.fen = data.fen;
    gameState.pieces = data.pieces;
    gameState.turn = data.turn;
    gameState.legalMoves = data.legal_moves || [];
    gameState.isGameOver = data.is_game_over;
    gameState.result = data.result;
}

function updateUI() {
    renderBoard();
    updateTurnIndicator();
    updateMoveHistory();
}

function updateTurnIndicator() {
    const indicator = document.getElementById('turn-indicator');
    if (gameState.isGameOver) {
        indicator.textContent = 'Game Over';
        indicator.style.color = '#e94560';
    } else if (gameState.engineThinking) {
        indicator.textContent = 'Engine thinking...';
        indicator.style.color = '#f5c518';
    } else {
        indicator.textContent = gameState.turn === 'white' ? 'White to move' : 'Black to move';
        indicator.style.color = gameState.turn === 'white' ? '#fff' : '#aaa';
    }
}

function updateStatus(message) {
    document.getElementById('game-status').innerHTML = message;
}

function updateMoveHistory() {
    const historyEl = document.getElementById('move-history');

    if (gameState.history.length === 0) {
        historyEl.innerHTML = '<em>No moves yet</em>';
        return;
    }

    let html = '';
    for (let i = 0; i < gameState.history.length; i += 2) {
        const moveNum = Math.floor(i / 2) + 1;
        const whiteMove = gameState.history[i]?.move || '';
        const blackMove = gameState.history[i + 1]?.move || '';

        html += `<div class="move-pair">
            <span class="move-number">${moveNum}.</span>
            <span class="move-white">${whiteMove}</span>
            <span class="move-black">${blackMove}</span>
        </div>`;
    }

    historyEl.innerHTML = html;
    historyEl.scrollTop = historyEl.scrollHeight;
}

function showGameOver(result) {
    let message = '<span class="game-over">Game Over!</span><br>';
    if (result === '1-0') {
        message += 'White wins! 🎉';
    } else if (result === '0-1') {
        message += 'Black wins!';
    } else if (result === '1/2-1/2') {
        message += 'Draw!';
    } else {
        message += 'Result: ' + (result || 'Unknown');
    }
    updateStatus(message);
}

function showHallucination(msg) {
    const alertEl = document.getElementById('hallucination-alert');
    document.getElementById('hallucination-msg').textContent = msg;
    alertEl.style.display = 'block';
}

// ── Initialize ────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    renderBoard();
});
