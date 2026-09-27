"""git_ops._run must always run git with GIT_TERMINAL_PROMPT=0, even if the
process's own environment already sets GIT_TERMINAL_PROMPT to something
else (e.g. a developer's shell has it =1) — otherwise git could hang
waiting on a credential prompt nothing can answer, defeating the whole
point of the "fail fast, don't hang" guarantee the module docstring
promises.
"""

from __future__ import annotations

import subprocess

from app.core import git_ops


def test_git_terminal_prompt_cannot_be_overridden_by_user_env(monkeypatch, tmp_path) -> None:
    # Simulate a user environment that already sets GIT_TERMINAL_PROMPT=1 —
    # _git_env() inherits os.environ verbatim, so this is exactly the
    # scenario the fix guards against.
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "1")

    captured: dict = {}

    def fake_run(args, cwd, capture_output, text, timeout, env):
        captured["env"] = env
        return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")

    monkeypatch.setattr(git_ops.subprocess, "run", fake_run)

    rc, out, err = git_ops._run(["status"], cwd=str(tmp_path))

    assert rc == 0
    assert captured["env"]["GIT_TERMINAL_PROMPT"] == "0"


def test_git_env_merge_order_puts_terminal_prompt_last() -> None:
    """Regression guard on the dict literal itself: GIT_TERMINAL_PROMPT
    must be the last key in the merge so it always wins over whatever
    _git_env() (which spreads os.environ) provides."""
    import inspect

    source = inspect.getsource(git_ops._run)
    # The safe ordering is **_git_env(), "GIT_TERMINAL_PROMPT": "0" — the
    # override must appear textually after the spread of _git_env().
    spread_idx = source.index("**_git_env()")
    override_idx = source.index('"GIT_TERMINAL_PROMPT"')
    assert spread_idx < override_idx
