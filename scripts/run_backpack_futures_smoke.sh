#!/usr/bin/env bash
set -euo pipefail

# Backpack USDC perpetual futures live trading smoke test wrapper.
#
# This is a thin convenience wrapper around scripts/manual_backpack_futures_smoke.py.
# It does NOT change any trading logic; it only:
#   - Resolves the project root
#   - Ensures we run the Python script from the repo root
#   - Forwards all CLI arguments as-is
#
# WARNING:
#   This script can submit REAL ORDERS on Backpack futures when valid API
#   credentials are configured. Make sure you understand and double-check:
#     - BACKPACK_API_PUBLIC_KEY
#     - BACKPACK_API_SECRET_SEED
#     - Coin, size, and side parameters
#   before running it.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${SCRIPT_DIR%/scripts}"
cd "${ROOT_DIR}"

# Keep output unbuffered for easier monitoring
export PYTHONUNBUFFERED=1

# Default behaviour: rely on manual_backpack_futures_smoke.py's own defaults.
# Examples:
#   ./scripts/run_backpack_futures_smoke.sh
#   ./scripts/run_backpack_futures_smoke.sh --coin BTC --size 0.001 --side long

python scripts/manual_backpack_futures_smoke.py "$@"
