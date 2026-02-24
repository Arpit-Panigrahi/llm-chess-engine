import tkinter as tk
from tkinter import messagebox
import chess
import chess.engine
import sys
import csv          # NEW
import os           # NEW
from datetime import datetime # NEW


# --- CONFIGURATION ---
BOARD_SIZE = 600
SQUARE_SIZE = BOARD_SIZE // 8
# CHANGED: Updated for Linux/WSL path — engine binary lives in Source/
import os
ENGINE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Source", "vice")

# Unicode Pieces for visuals
PIECE_SYMBOLS = {
    'P': '♙', 'N': '♘', 'B': '♗', 'R': '♖', 'Q': '♕', 'K': '♔',
    'p': '♟', 'n': '♞', 'b': '♝', 'r': '♜', 'q': '♛', 'k': '♚'
}

class ChessGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("LLM Chess Engine (built on VICE by Bluefever Software)")
        
        # 1. Initialize Engine
        try:
            self.engine = chess.engine.SimpleEngine.popen_uci(ENGINE_PATH)
        except FileNotFoundError:
            messagebox.showerror("Error", f"Engine not found at: {ENGINE_PATH}\nMake sure you compiled 'vice' in this folder!")
            sys.exit(1)

        self.board = chess.Board()
        self.selected_square = None

        # --- RESEARCH TRACKING SETUP ---
        self.games_played = 0
        self.max_games = 100
        self.csv_filename = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "llm_hallucinations.csv")
        
        # Create CSV and write headers if it is a new file
        if not os.path.exists(self.csv_filename):
            with open(self.csv_filename, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(["Timestamp", "Game_Number", "Turn_Number", "FEN", "Error_Message"])

        # 2. Setup Canvas
        self.canvas = tk.Canvas(root, width=BOARD_SIZE, height=BOARD_SIZE)
        self.canvas.pack()
        
        # 3. Bind Clicks
        self.canvas.bind("<Button-1>", self.on_click)
        self.draw_board()

        # 4. ADD THE AUTO-TEST BUTTON HERE
        self.auto_btn = tk.Button(
            self.root, 
            text="▶ Run Auto-Test (100 Games)", 
            font=("Arial", 14, "bold"), 
            bg="#4CAF50",      # A nice green color
            fg="white", 
            command=self.run_automated_test
        )
        self.auto_btn.pack(pady=10) # pady adds a little empty space above the button
    




    def run_automated_test(self):
        """Automatically plays White (random) vs Black (Llama-3)"""
        if self.board.is_game_over():
            result = self.board.result()
            print(f"Game {self.games_played + 1} Over! Result: {result}")
            self.games_played += 1
            if self.games_played < self.max_games:
                print(f"Starting game {self.games_played + 1} in 1 second...")
                self.board.reset()
                self.draw_board()
                self.root.after(1000, self.run_automated_test)
            else:
                print("\n🎉 TOURNAMENT COMPLETE! All games finished.")
                messagebox.showinfo("Done", f"Research run complete!\n{self.games_played} games played.\nCheck {self.csv_filename}")
            return

        # --- WHITE'S TURN (Random Move) ---
        if self.board.turn == chess.WHITE:
            import random
            legal_moves = list(self.board.legal_moves)
            random_move = random.choice(legal_moves)
            self.board.push(random_move)
            self.draw_board()
            
            # Schedule Black's turn in 100ms
            self.root.after(100, self.run_automated_test)

        # --- BLACK'S TURN (Llama-3 Engine) ---
        else:
            try:
                result = self.engine.play(self.board, chess.engine.Limit(time=15.0))
                self.board.push(result.move)
                self.draw_board()
                
                # Schedule White's turn in 100ms
                self.root.after(100, self.run_automated_test)
                
            except chess.engine.EngineError as e:
                print(f"\n--- HALLUCINATION IN GAME {self.games_played + 1} ---")
                
                # 1. Log the failure to our CSV file
                with open(self.csv_filename, mode='a', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow([
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        self.games_played + 1,
                        self.board.fullmove_number,
                        self.board.fen(),
                        str(e)
                    ])
                print(f"Data saved to {self.csv_filename}")
                
                # 2. Reset the board for the next game
                self.games_played += 1
                if self.games_played < self.max_games:
                    print("Resetting board for next game in 1 second...")
                    self.board.reset()
                    self.draw_board()
                    # Wait 1 second, then start the next game
                    self.root.after(1000, self.run_automated_test) 
                else:
                    print("\n🎉 TOURNAMENT COMPLETE! 100 games logged.")
                    messagebox.showinfo("Done", f"Research run complete!\nCheck {self.csv_filename}")
            except Exception as e:
                # Catch-all: engine crashed or connection lost — restart it
                print(f"\n--- ENGINE CRASH IN GAME {self.games_played + 1}: {e} ---")
                try:
                    self.engine.quit()
                except:
                    pass
                try:
                    self.engine = chess.engine.SimpleEngine.popen_uci(ENGINE_PATH)
                    print("Engine restarted successfully.")
                except Exception as restart_err:
                    print(f"FATAL: Could not restart engine: {restart_err}")
                    messagebox.showerror("Engine Crashed", f"Could not restart engine:\n{restart_err}")
                    return
                self.games_played += 1
                if self.games_played < self.max_games:
                    self.board.reset()
                    self.draw_board()
                    self.root.after(1000, self.run_automated_test)
                else:
                    print("\n🎉 TOURNAMENT COMPLETE!")
                    messagebox.showinfo("Done", f"Research run complete!\nCheck {self.csv_filename}")

    def draw_board(self):
        self.canvas.delete("all")
        colors = ["#F0D9B5", "#B58863"] # Classic wood colors

        for r in range(8):
            for c in range(8):
                color = colors[(r + c) % 2]
                x1 = c * SQUARE_SIZE
                y1 = r * SQUARE_SIZE
                x2 = x1 + SQUARE_SIZE
                y2 = y1 + SQUARE_SIZE
                
                # Draw Square
                self.canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline="")

                # Highlight Selection
                square_idx = chess.square(c, 7-r)
                if self.selected_square == square_idx:
                    self.canvas.create_rectangle(x1, y1, x2, y2, fill="#BACA44", outline="")

                # Draw Piece
                piece = self.board.piece_at(square_idx)
                if piece:
                    symbol = PIECE_SYMBOLS[piece.symbol()]
                    font_color = "black"
                    # Center text
                    self.canvas.create_text(x1 + SQUARE_SIZE//2, y1 + SQUARE_SIZE//2, 
                                          text=symbol, font=("DejaVu Sans", 36), fill=font_color)

    def on_click(self, event):
        if self.board.is_game_over():
            return

        col = event.x // SQUARE_SIZE
        row = event.y // SQUARE_SIZE
        clicked_square = chess.square(col, 7-row)

        if self.selected_square is None:
            # Select piece (only if it's white/human turn)
            piece = self.board.piece_at(clicked_square)
            if piece and piece.color == chess.WHITE:
                self.selected_square = clicked_square
                self.draw_board()
        else:
            # Move piece
            move = chess.Move(self.selected_square, clicked_square)
            
            # Auto-promote to Queen
            if move not in self.board.legal_moves:
                move = chess.Move(self.selected_square, clicked_square, promotion=chess.QUEEN)

            if move in self.board.legal_moves:
                self.board.push(move)
                self.selected_square = None
                self.draw_board()
                self.root.update() # Force update screen before engine thinks
                
                # Trigger Engine Move
                self.root.after(100, self.engine_move)
            else:
                # Deselect or select new piece
                self.selected_square = None
                self.draw_board()

    def engine_move(self):
        if self.board.is_game_over():
            return
            
        try:
            # We ask the engine for a move
            result = self.engine.play(self.board, chess.engine.Limit(depth=5))
            
            # If the move is valid, push it to the board
            self.board.push(result.move)
            self.draw_board()
            
        except chess.engine.EngineError as e:
            # If the engine (Llama-3) hallucinates an illegal move, catch the crash!
            print(f"\n--- HALLUCINATION DETECTED ---")
            print(f"Error Details: {e}")
            
            # Show a pop-up warning without closing the whole app
            messagebox.showwarning(
                "LLM Hallucination!", 
                f"Llama-3 attempted an illegal move!\n\nEngine output: {e}\n\nThe game will now stop."
            )

    def close(self):
        self.engine.quit()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    gui = ChessGUI(root)
    root.protocol("WM_DELETE_WINDOW", gui.close)
    root.mainloop()