"""
mcp/viz_mcp/start.py
Démarre le serveur MCP Visualization sur http://localhost:8002/mcp
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from mcp.viz_mcp.server import mcp  # noqa: E402

if __name__ == "__main__":
    print("[VIZ MCP] Serveur démarré → http://localhost:8002/mcp")
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8002)