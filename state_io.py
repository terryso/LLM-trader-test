"""
State persistence utilities.

COMPATIBILITY LAYER: This module re-exports from core.persistence.
Please import from core.persistence directly in new code.
"""
from core.persistence import (
    load_equity_history_from_csv,
    init_csv_files_for_paths,
    save_state_to_json,
    load_state_from_json,
    append_portfolio_state_row,
    append_trade_row,
)

__all__ = [
    "load_equity_history_from_csv",
    "init_csv_files_for_paths",
    "save_state_to_json",
    "load_state_from_json",
    "append_portfolio_state_row",
    "append_trade_row",
]
