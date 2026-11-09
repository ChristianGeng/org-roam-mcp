"""Org-roam MCP server entry point."""

import argparse
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
import sys

from mcp.server.fastmcp import FastMCP

from . import tools_emacs
from . import tools_roam


mcp = FastMCP("org-roam")

tools_emacs.register(mcp)
tools_roam.register(mcp)

DESCRIPTION = """\
An MCP server that gives an AI agent read access to an org-roam knowledge
graph: find and read nodes, follow links and backlinks, and run graph
algorithms. Without arguments it starts and talks MCP over standard input and
output, so an MCP client (for example Claude Code) starts it; it is not used by
hand."""

EPILOG = """\
How the database is found, in this order:
  1. A running Emacs is asked for org-roam-db-location through emacsclient:
     the default server (or the TCP server in EMACS_SERVER_FILE), then the
     server named by EMACS_SOCKET_NAME (passed as --socket-name), then the
     default sockets.
  2. ORG_ROAM_DB, if set.
  3. The standard places, for vanilla Emacs and Doom:
     ~/.emacs.d/org-roam.db
     ~/.emacs.d/.local/cache/org-roam.db
     $XDG_CONFIG_HOME/emacs/org-roam.db (default ~/.config/emacs/...)
     $XDG_CONFIG_HOME/emacs/.local/cache/org-roam.db

Environment variables:
  ORG_ROAM_DB        full path of org-roam.db
  EMACS_SOCKET_NAME  name or path of an Emacs server socket (passed as --socket-name)
  EMACS_SERVER_FILE  server file of a TCP Emacs server (read by emacsclient)
  XDG_CONFIG_HOME    base of the second Emacs folder (default ~/.config)"""


def _version() -> str:
    """Return the installed package version."""
    try:
        return package_version("org-roam-mcp")
    except PackageNotFoundError:
        return "unknown"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line; --help and --version print and exit."""
    parser = argparse.ArgumentParser(
        prog="org-roam-mcp",
        description=DESCRIPTION,
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"org-roam-mcp {_version()}",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None):
    """Start the MCP server, unless --help or --version was given."""
    parse_args(sys.argv[1:] if argv is None else argv)
    mcp.run()


if __name__ == "__main__":
    main()
