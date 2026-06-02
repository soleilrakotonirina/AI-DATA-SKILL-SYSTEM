"""Démarre le serveur MCP ETL sur http://localhost:8001/mcp"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcp.etl_mcp.server import mcp

if __name__ == "__main__":
    print("ETL MCP Server → http://localhost:8001/mcp")
    mcp.run(transport="streamable-http", port=8001)