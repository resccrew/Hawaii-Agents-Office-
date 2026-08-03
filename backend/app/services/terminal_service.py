"""Real, long-lived PTY-backed processes — the piece the rest of this
codebase has deliberately avoided until now. `claude_cli_service.py`'s own
docstring notes a visible terminal-per-turn was "tried and reverted"; this
is a different shape of the same idea done properly: one persistent PTY the
backend owns and multiplexes over a WebSocket (see
api/routes/terminal.py), not a one-shot subprocess per message.

Stdlib only (`pty` + `fcntl`/`termios`/`struct`/`signal`) — no `pexpect`/
`ptyprocess` dependency, matching the project's existing "shell out
directly" style already used in git_ops.py, and keeping the zero-PTY-deps
footprint at zero.
"""

from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import pty
import signal
import struct
import termios
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger("studio_ops.terminal")

OutputHandler = Callable[[bytes], None]
ExitHandler = Callable[[], None]

READ_CHUNK = 4096
# How long to wait after SIGTERM before escalating to SIGKILL — mirrors the
# same terminate-then-kill escalation the Tauri sidecar's own shutdown path
# (src-tauri/src/lib.rs) uses for the backend process itself.
KILL_ESCALATION_SECONDS = 2.0


@dataclass
class PtyProcess:
    pid: int
    fd: int


def _set_nonblocking(fd: int) -> None:
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)


def spawn(cwd: str, command: list[str] | None = None) -> PtyProcess:
    """Forks a child with a real controlling TTY. Defaults to the user's own
    $SHELL; pass `command` (e.g. ["claude"]) to run something else
    interactively instead — no `-p`, so it gets its own normal TUI, unlike
    every other Claude invocation in this codebase."""
    argv = command or [os.environ.get("SHELL", "/bin/zsh")]
    pid, fd = pty.fork()
    if pid == 0:  # child — replaced by argv, or exits before returning here
        try:
            # When spawned from a daemon with no TTY (like the Tauri bundle),
            # the OS may not provide sane PTY defaults. Ensure VERASE is 127
            # (^?) so backspace from xterm.js isn't echoed as a literal space.
            # ALSO critically enable IUTF8 so multi-byte characters (like Cyrillic)
            # are erased as a single character, not half a byte (which corrupts UTF-8).
            try:
                import termios
                attrs = termios.tcgetattr(0)
                attrs[3] |= termios.ECHOE
                attrs[6][termios.VERASE] = b'\x7f'
                if hasattr(termios, 'IUTF8'):
                    attrs[0] |= termios.IUTF8
                termios.tcsetattr(0, termios.TCSANOW, attrs)
            except Exception:
                pass
            
            os.environ["TERM"] = "xterm-256color"
            os.environ["COLORTERM"] = "truecolor"
            os.environ["FORCE_COLOR"] = "1"
            os.environ["CLICOLOR_FORCE"] = "1"
            if "LANG" not in os.environ:
                os.environ["LANG"] = "en_US.UTF-8"
            os.chdir(cwd)
            os.execvp(argv[0], argv)
        except OSError:
            os._exit(127)
    _set_nonblocking(fd)
    return PtyProcess(pid=pid, fd=fd)


def write(proc: PtyProcess, data: bytes) -> None:
    try:
        os.write(proc.fd, data)
    except OSError:
        pass  # pane is closing/closed — the read loop's on_exit already handles that


def resize(proc: PtyProcess, rows: int, cols: int) -> None:
    try:
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(proc.fd, termios.TIOCSWINSZ, winsize)
    except OSError:
        pass


def start_reading(proc: PtyProcess, on_output: OutputHandler, on_exit: ExitHandler) -> None:
    """Registers a `loop.add_reader` callback that streams PTY output to
    `on_output` as it arrives. `loop.add_reader` (not a thread-per-pane) so
    this scales to many simultaneous panes without a thread each — it works
    for PTY master fds on POSIX exactly like it does for pipes/sockets.
    Fires `on_exit` and reaps the child once the PTY closes (EOF, i.e. the
    shell/process exited)."""
    loop = asyncio.get_event_loop()

    def _readable() -> None:
        try:
            data = os.read(proc.fd, READ_CHUNK)
        except OSError:
            data = b""
        if not data:
            loop.remove_reader(proc.fd)
            try:
                os.close(proc.fd)
            except OSError:
                pass
            asyncio.create_task(_reap(proc.pid))
            on_exit()
            return
        on_output(data)

    loop.add_reader(proc.fd, _readable)


async def _reap(pid: int) -> None:
    """waitpid blocks, so it runs off the event loop thread — otherwise one
    pane exiting would stall every other request for however long the OS
    takes to reap the zombie."""
    try:
        await asyncio.to_thread(os.waitpid, pid, 0)
    except ChildProcessError:
        pass  # already reaped


def kill(proc: PtyProcess) -> None:
    """SIGTERM now, SIGKILL shortly after if it's still around."""
    try:
        os.kill(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return

    async def _escalate() -> None:
        await asyncio.sleep(KILL_ESCALATION_SECONDS)
        try:
            os.kill(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass  # already exited (and reaped) — SIGTERM alone was enough

    asyncio.create_task(_escalate())
