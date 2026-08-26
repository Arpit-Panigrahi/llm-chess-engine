/**
 * LLM Chess Engine — Client-side Game Logic
 * Handles board rendering, piece interaction, Web Audio synthesis, and API communication.
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
    pendingPromotion: null,
    soundEnabled: true,
};

// ── Web Audio Synthesizer ─────────────────────────────────────
let audioCtx = null;

function getAudioContext() {
    if (!audioCtx) {
        const AudioContextClass = window.AudioContext || window.webkitAudioContext;
        if (AudioContextClass) {
            audioCtx = new AudioContextClass();
        }
    }
    if (audioCtx && audioCtx.state === 'suspended') {
        audioCtx.resume();
    }
    return audioCtx;
}

function playSound(type) {
    if (!gameState.soundEnabled) return;
    try {
        const ctx = getAudioContext();
        if (!ctx) return;

        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);

        const now = ctx.currentTime;

        if (type === 'move') {
            osc.frequency.setValueAtTime(440, now);
            osc.frequency.exponentialRampToValueAtTime(330, now + 0.08);
            gain.gain.setValueAtTime(0.15, now);
            gain.gain.exponentialRampToValueAtTime(0.01, now + 0.08);
            osc.start(now);
            osc.stop(now + 0.08);
        } else if (type === 'capture') {
            osc.frequency.setValueAtTime(600, now);
            osc.frequency.exponentialRampToValueAtTime(250, now + 0.12);
            gain.gain.setValueAtTime(0.25, now);
            gain.gain.exponentialRampToValueAtTime(0.01, now + 0.12);
            osc.start(now);
            osc.stop(now + 0.12);
        } else if (type === 'check') {
            osc.frequency.setValueAtTime(800, now);
            osc.frequency.setValueAtTime(1000, now + 0.08);
            gain.gain.setValueAtTime(0.2, now);
            gain.gain.exponentialRampToValueAtTime(0.01, now + 0.2);
            osc.start(now);
            osc.stop(now + 0.2);
        } else if (type === 'gameover') {
            osc.frequency.setValueAtTime(523.25, now);
            osc.frequency.setValueAtTime(659.25, now + 0.1);
            osc.frequency.setValueAtTime(783.99, now + 0.2);
            gain.gain.setValueAtTime(0.2, now);
            gain.gain.exponentialRampToValueAtTime(0.01, now + 0.4);
            osc.start(now);
            osc.stop(now + 0.4);
        }
    } catch (e) {
        // Audio playback failure should not interrupt game loop
    }
}

function toggleSound() {
    gameState.soundEnabled = !gameState.soundEnabled;
    const btn = document.getElementById('btn-sound');
    if (btn) {
        btn.textContent = gameState.soundEnabled ? '🔊 Sound: ON' : '🔇 Sound: OFF';
    }
}

// ── File/Rank Helpers ─────────────────────────────────────────
const FILES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'];
const RANKS = ['1', '2', '3', '4', '5', '6', '7', '8'];

function squareName(col, row) {
    return FILES[col] + RANKS[row];
}

// ── Board Rendering ───────────────────────────────────────────
function renderBoard() {
    const boardEl = document.getElementById('chess-board');
    if (!boardEl) return;
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
            const isDark = (col + row) % 2 === 0;

            const squareEl = document.createElement('div');
            squareEl.className = `square ${isDark ? 'dark' : 'light'}`;
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
    if (gameState.pendingPromotion) return;

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
        const fromSq = gameState.selectedSquare;
        const toSq = sq;
        const movePrefix = fromSq + toSq;

        // Check if this is a valid move destination
        const validMoves = gameState.legalMoves.filter(
            m => m.startsWith(movePrefix)
        );

        if (validMoves.length > 0) {
            // Check if this is a pawn promotion (moving to rank 8)
            const piece = gameState.pieces[fromSq];
            if (piece && piece.symbol === 'P' && toSq[1] === '8') {
                // Show promotion selector
                gameState.pendingPromotion = { from: fromSq, to: toSq, moves: validMoves };
                const promoModal = document.getElementById('promotion-modal');
                if (promoModal) promoModal.style.display = 'flex';
                return;
            }

            const move = validMoves[0];
            gameState.selectedSquare = null;
            makeMove(move);
        } else {
            // Try selecting a different white piece
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

function selectPromotion(pieceLetter) {
    if (!gameState.pendingPromotion) return;
    const { from, to, moves } = gameState.pendingPromotion;
    const targetMove = from + to + pieceLetter.toLowerCase();

    const promoModal = document.getElementById('promotion-modal');
    if (promoModal) promoModal.style.display = 'none';

    gameState.pendingPromotion = null;
    gameState.selectedSquare = null;

    // Verify move is in legal moves or fallback to first
    const moveToSend = moves.includes(targetMove) ? targetMove : (moves[0] || targetMove);
    makeMove(moveToSend);
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
        gameState.pendingPromotion = null;

        const promoModal = document.getElementById('promotion-modal');
        if (promoModal) promoModal.style.display = 'none';

        // Hide hallucination alert
        const alertBox = document.getElementById('hallucination-alert');
        if (alertBox) alertBox.style.display = 'none';

        updateUI();
        updateStatus('Your turn! Click a white piece to move.');
        playSound('move');
    } catch (err) {
        updateStatus('Error starting new game: ' + err.message);
    }
}

async function makeMove(moveUci) {
    try {
        const isCapture = gameState.pieces[moveUci.substring(2, 4)] !== undefined;

        const res = await fetch('/api/move', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                game_id: gameState.gameId, 
                move: moveUci,
                fen: gameState.fen 
            }),
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

        if (data.is_check) {
            playSound('check');
        } else if (isCapture) {
            playSound('capture');
        } else {
            playSound('move');
        }

        updateUI();

        if (data.is_game_over) {
            showGameOver(data.result);
            playSound('gameover');
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
            body: JSON.stringify({ 
                game_id: gameState.gameId,
                fen: gameState.fen
            }),
        });

        const data = await res.json();
        gameState.engineThinking = false;

        const wasCapture = data.engine_move && gameState.pieces[data.engine_move.substring(2, 4)] !== undefined;

        updateGameState(data);
        gameState.lastMove = data.engine_move;

        // Record engine move
        if (data.engine_move) {
            gameState.history.push({
                move: data.engine_move,
                color: 'black'
            });

            if (data.is_check) {
                playSound('check');
            } else if (wasCapture) {
                playSound('capture');
            } else {
                playSound('move');
            }
        }

        // Update engine badge
        const badge = document.getElementById('engine-badge');
        if (badge) {
            badge.textContent = 'Engine: ' + (data.engine_name || 'unknown');
        }

        // Check for hallucination
        if (data.hallucination) {
            showHallucination('The LLM attempted an illegal move! Falling back to classical search.');
        } else {
            const alertBox = document.getElementById('hallucination-alert');
            if (alertBox) alertBox.style.display = 'none';
        }

        updateUI();

        if (data.is_game_over) {
            showGameOver(data.result);
            playSound('gameover');
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
    if (!gameState.gameId && !gameState.fen) return;

    try {
        const res = await fetch('/api/undo', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                game_id: gameState.gameId,
                fen: gameState.fen 
            }),
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
        playSound('move');
    } catch (err) {
        updateStatus('Error undoing move: ' + err.message);
    }
}

function flipBoard() {
    gameState.flipped = !gameState.flipped;
    renderBoard();
}

function copyFEN() {
    if (!gameState.fen) {
        updateStatus('No game in progress to copy FEN.');
        return;
    }
    navigator.clipboard.writeText(gameState.fen).then(() => {
        updateStatus('✓ FEN copied to clipboard: <code>' + gameState.fen + '</code>');
    }).catch(() => {
        updateStatus('FEN: ' + gameState.fen);
    });
}

function copyPGN() {
    if (!gameState.history || gameState.history.length === 0) {
        updateStatus('No moves to copy PGN.');
        return;
    }
    let pgn = '';
    for (let i = 0; i < gameState.history.length; i += 2) {
        const moveNum = Math.floor(i / 2) + 1;
        const white = gameState.history[i]?.move || '';
        const black = gameState.history[i + 1]?.move || '';
        pgn += `${moveNum}. ${white} ${black} `.trim() + ' ';
    }
    if (gameState.result) {
        pgn += gameState.result;
    }
    navigator.clipboard.writeText(pgn.trim()).then(() => {
        updateStatus('✓ PGN copied to clipboard!');
    }).catch(() => {
        updateStatus('PGN: ' + pgn);
    });
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
    if (!indicator) return;
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
    const statusEl = document.getElementById('game-status');
    if (statusEl) statusEl.innerHTML = message;
}

function updateMoveHistory() {
    const historyEl = document.getElementById('move-history');
    const countEl = document.getElementById('move-count');
    if (!historyEl) return;

    if (countEl) {
        countEl.textContent = `${gameState.history.length} plies`;
    }

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
    const msgEl = document.getElementById('hallucination-msg');
    if (msgEl) msgEl.textContent = msg;
    if (alertEl) alertEl.style.display = 'block';
}

// ── Keyboard Shortcuts ────────────────────────────────────────
document.addEventListener('keydown', (e) => {
    // Avoid triggering while typing in inputs
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    if (e.key === 'n' || e.key === 'N') {
        newGame();
    } else if (e.key === 'f' || e.key === 'F') {
        flipBoard();
    } else if (e.key === 'z' || e.key === 'Z' || e.key === 'u' || e.key === 'U') {
        undoMove();
    } else if (e.key === 'm' || e.key === 'M') {
        toggleSound();
    }
});

// ── Initialize ────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    newGame();
});
