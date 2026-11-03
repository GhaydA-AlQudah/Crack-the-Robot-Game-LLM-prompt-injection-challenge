# config.py
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

EVALS_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVALS_DIR / "results"

MODEL_NAME = "gemini-flash-lite-latest"

# Optional prices, expressed as USD per one million tokens.
# Leave unset until you verify the correct pricing for this model.
INPUT_PRICE_PER_MILLION = os.getenv(
    "GEMINI_INPUT_USD_PER_MILLION"
)
OUTPUT_PRICE_PER_MILLION = os.getenv(
    "GEMINI_OUTPUT_USD_PER_MILLION"
)

def get_price(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None

    price = float(value)

    if price < 0:
        raise ValueError("Token prices cannot be negative.")

    return price

INPUT_PRICE = get_price(INPUT_PRICE_PER_MILLION)
OUTPUT_PRICE = get_price(OUTPUT_PRICE_PER_MILLION)
