"""Org-roam MCP server entry point."""

from mcp.server.fastmcp import FastMCP

from . import tools_emacs
from . import tools_roam


mcp = FastMCP("org-roam")

tools_emacs.register(mcp)
tools_roam.register(mcp)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
