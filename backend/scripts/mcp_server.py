from app.mcp_server import mcp
from app.observability import configure_telemetry

if __name__ == "__main__":
    configure_telemetry("supplymind-mcp")
    mcp.run(transport="streamable-http")
