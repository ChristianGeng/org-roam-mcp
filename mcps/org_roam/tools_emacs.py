"""Layer 1: General-purpose Emacs bridge tool."""

from mcp.server.fastmcp import FastMCP

from . import emacs


def register(mcp: FastMCP) -> None:
    """Register the emacs_eval tool."""

    @mcp.tool()
    def emacs_eval(expr: str) -> str:
        """Evaluate an arbitrary Elisp expression via emacsclient.

        Requires a running Emacs server (M-x server-start).

        Args:
            expr: Any Elisp expression, e.g. "(+ 1 2)" or "(org-roam-db-sync)"

        """
        result, error = emacs.emacs_eval(expr)
        if error:
            return f"Error: {error}\nOutput: {result}"
        return result
