from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
import chess
import chess.svg
import random



# Modern x402 setup (testnet, Base Sepolia)
from x402.http import FacilitatorConfig, HTTPFacilitatorClient, PaymentOption
from x402.http.middleware.fastapi import PaymentMiddlewareASGI
from x402.http.types import RouteConfig
from x402.mechanisms.evm.exact import ExactEvmServerScheme
from x402.server import x402ResourceServer

app = FastAPI(title="Adaptive Chess Puzzle Tutor - Testnet")

# === YOUR PHANTOM WALLET ADDRESS ON BASE SEPOLIA ===
PAY_TO_ADDRESS = "0xaDFD51c4cd7CB2C70C26ea58e62EFd354329475A"  # Paste exactly (0x...)

# Testnet facilitator (works for Base Sepolia)
facilitator = HTTPFacilitatorClient(
    FacilitatorConfig(url="https://x402.org/facilitator")  # Testnet facilitator
)
# Register EVM scheme for Base Sepolia (CAIP-2 format)
resource_server = x402ResourceServer(facilitator)
resource_server.register("eip155:84532", ExactEvmServerScheme())

# Define which routes require payment
protected_routes: dict[str, RouteConfig] = {
    "/hint": RouteConfig(
        accepts=[
            PaymentOption(
                scheme="exact",
                pay_to=PAY_TO_ADDRESS,
                price="$0.005",  # Test USDC amount (facilitator handles conversion)
                network="eip155:84532",
            )
        ],
        mime_type="text/html",  # Matches your HTML hint response
        description="Pay $0.005 USDC for chess puzzle hint (level 1-3)",
    )
}

# Apply the middleware to the entire app
app.add_middleware(
    PaymentMiddlewareASGI,
    routes=protected_routes,
    server=resource_server
)

# Sample puzzles (expand later)
PUZZLES = [
    {"fen": "1K1k4/1Q6/4n3/8/8/8/3q4/3r4 w - - 0 1", "theme": "Mate in 1 (Queen sac)"},
    {"fen": "rnbqkbnr/pppp1ppp/5N2/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2", "theme": "Queen trap"},
    # Add more FENs from lichess.org/training
]

piece_values = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}

def evaluate_board(board):
    if board.is_game_over():
        return 10000 if board.result() == "1-0" else -10000 if board.result() == "0-1" else 0
    score = sum(piece_values.get(p.piece_type, 0) * (1 if p.color == chess.WHITE else -1)
                for p in board.piece_map().values())
    return score

def minimax(board, depth, alpha, beta, maximizing):
    if depth == 0 or board.is_game_over():
        return evaluate_board(board)
    if maximizing:
        max_eval = -float('inf')
        for move in board.legal_moves:
            board.push(move)
            eval_score = minimax(board, depth-1, alpha, beta, False)
            board.pop()
            max_eval = max(max_eval, eval_score)
            alpha = max(alpha, eval_score)
            if beta <= alpha: break
        return max_eval
    else:
        min_eval = float('inf')
        for move in board.legal_moves:
            board.push(move)
            eval_score = minimax(board, depth-1, alpha, beta, True)
            board.pop()
            min_eval = min(min_eval, eval_score)
            beta = min(beta, eval_score)
            if beta <= alpha: break
        return min_eval

def find_best_move(board, depth=4):
    best_move = None
    best_value = -float('inf')
    for move in list(board.legal_moves):
        board.push(move)
        value = minimax(board, depth-1, -float('inf'), float('inf'), False)
        board.pop()
        if value > best_value:
            best_value = value
            best_move = move
    return best_move

def generate_hint(board, best_move, level):
    piece = board.piece_at(best_move.from_square)
    from_sq = chess.square_name(best_move.from_square)
    to_sq = chess.square_name(best_move.to_square)
    if level == 1:
        return f"Try moving your {piece.symbol().lower()} from {from_sq}."
    elif level == 2:
        return f"{piece.symbol().upper()}{from_sq} to {to_sq} – {'captures!' if board.is_capture(best_move) else 'checks!' if board.gives_check(best_move) else 'good move'}"
    else:
        san = board.san(best_move)
        board.push(best_move)
        outcome = board.outcome()
        board.pop()
        return f"Solution: {san} ({best_move.uci()}). {'Mate!' if outcome and outcome.winner else 'Winning line!'}"

@app.get("/puzzle", response_class=HTMLResponse)  # FREE
def get_puzzle():
    puzzle = random.choice(PUZZLES)
    board = chess.Board(puzzle["fen"])
    svg = chess.svg.board(board=board, size=400)
    return f"""
    <h1>Free Chess Puzzle: {puzzle['theme']}</h1>
    <div>{svg}</div>
    <p>FEN: {puzzle['fen']}</p>
    <p>Pay $0.005 for hints: <a href="/hint?fen={puzzle['fen']}&level=1">Hint 1</a> | Level 2 | Solution</p>
    """

from typing import Dict, Any  # Add this import if not already there

from fastapi.responses import HTMLResponse

from fastapi import HTTPException

@app.get("/hint", response_model=None)
def get_hint(
    fen: str,
    level: Annotated[int, Query(ge=1, le=3)] = 1,
    format: str = Query("html", description="Output format: html or json")
):
    try:
        board = chess.Board(fen)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid FEN string")
    
    best_move = find_best_move(board)
    hint_text = generate_hint(board, best_move, level)
    san = board.san(best_move)
    uci = best_move.uci()
    
    # Simple shallow evaluation
    eval_score = minimax(board, depth=4, alpha=-float('inf'), beta=float('inf'), maximizing=True)
    
    if format.lower() == "json":
        return {
            "level": level,
            "hint": hint_text,
            "san": san,
            "uci": uci,
            "board_svg": chess.svg.board(board=board, size=400),
            "evaluation": f"{eval_score / 100:.2f}",
            "fen": fen
        }
    else:
        # HTML response
        svg = chess.svg.board(board=board, size=400)
        html = f"""
        <!DOCTYPE html>
        <html>
        <head><title>Chess Hint - Level {level}</title>
        <style>svg {{ max-width: 400px; display: block; margin: 20px auto; }}</style></head>
        <body style="font-family: Arial; text-align: center;">
            <h1>Hint Level {level}</h1>
            <p><strong>Hint:</strong> {hint_text}</p>
            <p><strong>SAN:</strong> {san}</p>
            <p><strong>UCI:</strong> {uci}</p>
            <div>{svg}</div>
            <p><a href="/puzzle">Back to new puzzle</a></p>
        </body>
        </html>
        """
        return HTMLResponse(content=html)

@app.get("/")
def home():
    return {"message": "Chess Puzzle Tutor running! Go to /puzzle for a free puzzle."}