"""Reuse the evaluator-wide PLC address parser without importing plant models."""
from pathlib import Path
import sys

sys.path.append(str(next(p for p in Path(__file__).resolve().parents if p.name == "evaluator")))
from device_address import parse_operand  # noqa: E402,F401
