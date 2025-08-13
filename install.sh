#!/usr/bin/env bash
set -euo pipefail

echo "🚀 Installing OCI MCP Server..."

if ! command -v python3 >/dev/null; then
  echo "❌ Python3 not found"; exit 1
fi

python3 - <<'PY'
import sys
from sys import version_info as v
assert v >= (3,10), f"Python 3.10+ required, found {sys.version}"
print("✅ Python version OK:", sys.version.split()[0])
PY

python3 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

echo "🔎 Checking OCI SDK import..."
python - <<'PY'
import oci
print("✅ OCI SDK imported")
from mcp.server.fastmcp import FastMCP
print("✅ MCP FastMCP imported")
PY

echo "🎉 Done. Next:"
echo "  1) Configure OCI:  oci setup config"
echo "  2) Copy .env.example to .env and adjust if needed"
echo "  3) Run server:     python oci_mcp_server.py"
echo "  4) Add to Claude:  see README.md"
