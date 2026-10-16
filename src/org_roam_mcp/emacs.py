"""Emacsclient subprocess wrapper."""

import subprocess


def emacs_eval(expr: str, timeout: int = 30) -> tuple[str, str | None]:
    """Evaluate an Elisp expression via emacsclient --eval.

    Returns (stdout, stderr_or_none).
    Raises RuntimeError if emacsclient is not found.
    """
    try:
        result = subprocess.run(
            ["emacsclient", "--eval", expr],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        raise RuntimeError("emacsclient not found. Is Emacs installed?")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"emacsclient timed out after {timeout}s")

    error = result.stderr.strip() if result.returncode != 0 else None
    return result.stdout.strip(), error
