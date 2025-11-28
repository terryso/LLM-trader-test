import io
import sys
from pathlib import Path
import tempfile
import unittest
from unittest import mock

# Make scripts/ importable so we can load recalculate_portfolio as a module
ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import recalculate_portfolio as rp


class RecalculatePortfolioCliTests(unittest.TestCase):
    def _write_sample_trades(self, trades_path: Path) -> None:
        trades_path.write_text(
            "timestamp,coin,action,side,quantity,price,profit_target,stop_loss,leverage,confidence,reason\n"
            "2024-01-01T00:00:00Z,BTC,ENTRY,long,1,100,120,90,2,0.5,AI entry | Fees: $1.00\n"
            "2024-01-01T01:00:00Z,BTC,CLOSE,long,1,120,,,2,,AI close | Fees: $2.00\n",
            encoding="utf-8",
        )

    def test_main_dry_run_prints_summary_and_does_not_write_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            trades_path = tmp_path / "trade_history.csv"
            state_path = tmp_path / "portfolio_state.json"
            self._write_sample_trades(trades_path)

            argv = [
                "recalculate_portfolio.py",
                "--trades",
                str(trades_path),
                "--state-json",
                str(state_path),
                "--start-capital",
                "1000",
                "--dry-run",
            ]

            buf = io.StringIO()
            with mock.patch.object(sys, "argv", argv), mock.patch("sys.stdout", buf):
                rp.main()

            output = buf.getvalue()
            self.assertIn("=== Portfolio Reconstruction ===", output)
            self.assertIn("Trades processed : 2", output)
            self.assertIn("-- Dry run: state file not updated --", output)
            self.assertFalse(state_path.exists())

    def test_main_writes_state_and_preserves_existing_iteration(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            trades_path = tmp_path / "trade_history.csv"
            state_path = tmp_path / "portfolio_state.json"
            self._write_sample_trades(trades_path)

            # Pre-existing state with non-zero iteration should be preserved.
            state_path.write_text(
                '{"balance": 500, "positions": {}, "iteration": 7}',
                encoding="utf-8",
            )

            argv = [
                "recalculate_portfolio.py",
                "--trades",
                str(trades_path),
                "--state-json",
                str(state_path),
                "--start-capital",
                "1000",
            ]

            buf = io.StringIO()
            with mock.patch.object(sys, "argv", argv), mock.patch("sys.stdout", buf):
                rp.main()

            output = buf.getvalue()
            self.assertIn("State written to", output)
            self.assertTrue(state_path.exists())

            import json

            data = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIn("balance", data)
            self.assertIn("positions", data)
            # Iteration should be carried over from existing file.
            self.assertEqual(data.get("iteration"), 7)
            self.assertIn("updated_at", data)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
