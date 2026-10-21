"""Public priority-backend entry point; physical task behavior stays frozen."""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "runtime"))

from engine.evaluate import evaluate  # noqa: E402,F401
