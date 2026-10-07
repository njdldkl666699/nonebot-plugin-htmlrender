"""Terminal state hygiene for host processes running an interactive session.

Playwright's node driver inherits the host process' stderr, which usually
points at the controlling terminal. The driver snapshots the terminal
state when it starts; if it starts while a TUI owns the terminal (raw
mode) and is later killed by a terminal-delivered ``SIGINT`` (drivers
share the foreground process group with the host), its exit path writes
the stale raw snapshot back to the terminal.

The terminal is then left with ``ISIG``/``ICANON``/``ECHO`` disabled:
later ``Ctrl+C`` presses no longer raise ``SIGINT`` and the next session
started on that terminal cannot be stopped from the keyboard.

This module snapshots the terminal state during plugin import (before any
TUI or child process can alter it) and restores it at the end of the
driver shutdown sequence, which runs after the child processes are gone
and before the interactive shell resumes ownership of the terminal.
"""

from __future__ import annotations

import os

from nonebot.log import logger

try:
    import termios
except ImportError:  # pragma: no cover - Windows lacks termios
    termios = None  # type: ignore[assignment]

_STDERR_FILENO = 2


class _TerminalState:
    """Holder for the snapshot; ``None`` until :func:`save_terminal_state` runs."""

    def __init__(self) -> None:
        self.saved: tuple | None = None


_state = _TerminalState()


def _take_snapshot(fd: int = _STDERR_FILENO) -> tuple | None:
    """Return the current termios settings of ``fd`` if it is a tty."""
    if termios is None:
        return None
    try:
        if not os.isatty(fd):
            return None
        return termios.tcgetattr(fd)
    except (OSError, termios.error):
        return None


def save_terminal_state(fd: int = _STDERR_FILENO) -> None:
    """Snapshot the terminal state attached to the host's stderr.

    Must run before any component (TUI frontends, Playwright drivers)
    can switch the terminal into raw mode; the plugin import sequence
    guarantees that.
    """
    _state.saved = _take_snapshot(fd)


def restore_terminal_state(fd: int = _STDERR_FILENO) -> None:
    """Re-apply the snapshot taken by :func:`save_terminal_state`.

    Skipped when no snapshot exists (no terminal, non-tty stderr, or
    platforms without ``termios``). Only writes when the current state
    actually differs from the snapshot.
    """
    if termios is None or _state.saved is None:
        return
    try:
        if not os.isatty(fd):
            return
        current = termios.tcgetattr(fd)
        if current != _state.saved:
            termios.tcsetattr(fd, termios.TCSANOW, _state.saved)
            logger.debug("Restored terminal state altered by child processes.")
    except (OSError, termios.error):
        pass


__all__ = ["restore_terminal_state", "save_terminal_state"]
