from mcp.server.fastmcp import FastMCP


def run() -> None:
    from mcp_server.tools import register
    mcp = FastMCP("automation-framework")
    register(mcp)
    mcp.run(transport="stdio")
