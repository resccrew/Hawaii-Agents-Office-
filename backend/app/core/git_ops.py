"""Git integration — lets the human pick a working repository and push it to
GitHub with one click from the UI (the git bar under the office).

Deliberately thin: every operation shells out to the real `git` binary in the
selected repo's directory (the user's own git config + credentials do the
auth, exactly as if they ran the command themselves). We never prompt — env
`GIT_TERMINAL_PROMPT=0` makes a missing credential fail fast with a readable
error instead of hanging the request.

The set of selectable repos and which one is active persists to
~/studio-ops/state/git.json so the choice survives restarts. On first run it
seeds itself with the studio-ops repo this backend lives in, so there's always
at least one sensible option.
"""

from __future__ import annotations

import base64
import json
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.core.settings_store import get_settings_store

STATE_FILE = Path.home() / "studio-ops" / "state" / "git.json"
# GitHub repos selected from the account get cloned here so agents have a
# real local working tree to operate on and push from.
REPOS_DIR = Path.home() / "studio-ops" / "repos"
GITHUB_API = "https://api.github.com"

# This file: .../studio-ops/backend/app/core/git_ops.py — parents[3] is the
# studio-ops repo root, used as the default seeded repository.
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _run(args: list[str], cwd: str, *, timeout: float = 60.0) -> tuple[int, str, str]:
    """Run a git command in `cwd`. Never raises for a non-zero exit — returns
    (returncode, stdout, stderr) so callers decide what a failure means."""
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={"GIT_TERMINAL_PROMPT": "0", **_git_env()},
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except FileNotFoundError:
        return 127, "", "git binary not found on PATH"
    except subprocess.TimeoutExpired:
        return 124, "", "git command timed out (possibly waiting on credentials)"


def _git_env() -> dict[str, str]:
    import os

    # Inherit the user's environment so credential helpers / SSH agents / PATH
    # work exactly as in their own shell.
    return dict(os.environ)


def _token() -> str | None:
    return get_settings_store().get("github_token")


def _auth_args(token: str | None) -> list[str]:
    """`git -c http.extraheader=...` args that authenticate an HTTPS git
    operation with a GitHub token without persisting it to disk (unlike a
    token-in-URL remote). Empty when there's no token — git then falls back
    to the user's own credential helper."""
    if not token:
        return []
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return ["-c", f"http.extraheader=Authorization: Basic {basic}"]


def is_git_repo(path: str) -> bool:
    p = Path(path).expanduser()
    if not p.is_dir():
        return False
    rc, out, _ = _run(["rev-parse", "--is-inside-work-tree"], str(p))
    return rc == 0 and out == "true"


@dataclass
class GitConfig:
    active: str | None = None
    repos: list[str] = field(default_factory=list)


def _load() -> GitConfig:
    cfg = GitConfig()
    if STATE_FILE.exists():
        try:
            raw = json.loads(STATE_FILE.read_text())
            cfg.active = raw.get("active")
            cfg.repos = [str(r) for r in raw.get("repos", [])]
        except (OSError, json.JSONDecodeError):
            pass
    # Seed the studio-ops repo on first run so there's always an option.
    if not cfg.repos and is_git_repo(str(_REPO_ROOT)):
        cfg.repos = [str(_REPO_ROOT)]
        cfg.active = str(_REPO_ROOT)
        _save(cfg)
    if cfg.active is None and cfg.repos:
        cfg.active = cfg.repos[0]
    return cfg


def _save(cfg: GitConfig) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps({"active": cfg.active, "repos": cfg.repos}, indent=2))
        tmp.replace(STATE_FILE)
    except OSError:
        pass


def repo_status(path: str) -> dict:
    """A compact status for one repo: branch, remote, dirty file count, and
    ahead/behind vs upstream (None when there's no upstream yet)."""
    p = str(Path(path).expanduser())
    name = Path(p).name
    if not is_git_repo(p):
        return {"path": path, "name": name, "valid": False}

    _, branch, _ = _run(["rev-parse", "--abbrev-ref", "HEAD"], p)
    _, remote, _ = _run(["config", "--get", "remote.origin.url"], p)
    _, porcelain, _ = _run(["status", "--porcelain"], p)
    dirty = len([ln for ln in porcelain.splitlines() if ln.strip()])
    _, last, _ = _run(["log", "-1", "--format=%h %s"], p)

    ahead: int | None = None
    behind: int | None = None
    rc_u, upstream, _ = _run(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], p)
    if rc_u == 0 and upstream:
        rc_c, counts, _ = _run(["rev-list", "--left-right", "--count", f"{upstream}...HEAD"], p)
        if rc_c == 0 and "\t" in counts:
            b, a = counts.split("\t")[:2]
            behind, ahead = int(b), int(a)

    return {
        "path": p,
        "name": name,
        "valid": True,
        "branch": branch or None,
        "remote": remote or None,
        "dirty": dirty,
        "ahead": ahead,
        "behind": behind,
        "hasUpstream": rc_u == 0,
        "lastCommit": last or None,
    }


def list_state() -> dict:
    cfg = _load()
    return {
        "active": cfg.active,
        "repos": [repo_status(r) for r in cfg.repos],
    }


def add_repo(path: str) -> dict:
    p = str(Path(path).expanduser().resolve())
    if not is_git_repo(p):
        raise ValueError(f"not a git repository: {p}")
    cfg = _load()
    if p not in cfg.repos:
        cfg.repos.append(p)
    cfg.active = p  # selecting a freshly added repo is the obvious intent
    _save(cfg)
    return list_state()


def set_active(path: str) -> dict:
    p = str(Path(path).expanduser().resolve())
    cfg = _load()
    if p not in cfg.repos:
        raise ValueError(f"repo not in the list: {p}")
    cfg.active = p
    _save(cfg)
    return list_state()


def remove_repo(path: str) -> dict:
    p = str(Path(path).expanduser().resolve())
    cfg = _load()
    cfg.repos = [r for r in cfg.repos if r != p]
    if cfg.active == p:
        cfg.active = cfg.repos[0] if cfg.repos else None
    _save(cfg)
    return list_state()


# ------------------------------- GitHub account --------------------------
async def github_status() -> dict:
    """Who the configured token authenticates as. {connected: False} when no
    token is set or it's invalid — the UI uses this to show a connect prompt."""
    token = _token()
    if not token:
        return {"connected": False, "reason": "no_token"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{GITHUB_API}/user",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            )
        if resp.status_code == 200:
            data = resp.json()
            return {"connected": True, "login": data.get("login"), "avatar": data.get("avatar_url")}
        return {"connected": False, "reason": f"github returned {resp.status_code}"}
    except httpx.HTTPError as exc:
        return {"connected": False, "reason": str(exc)}


async def list_github_repos(limit: int = 200) -> list[dict]:
    """All repositories the token can access (owned, collaborator, org),
    most-recently-pushed first. Paginated up to `limit`."""
    token = _token()
    if not token:
        return []
    repos: list[dict] = []
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            page = 1
            while len(repos) < limit and page <= 10:
                resp = await client.get(
                    f"{GITHUB_API}/user/repos",
                    params={"per_page": 100, "page": page, "sort": "pushed", "affiliation": "owner,collaborator,organization_member"},
                    headers=headers,
                )
                if resp.status_code != 200:
                    break
                batch = resp.json()
                if not batch:
                    break
                for r in batch:
                    repos.append(
                        {
                            "fullName": r.get("full_name"),
                            "cloneUrl": r.get("clone_url"),
                            "private": r.get("private", False),
                            "pushedAt": r.get("pushed_at"),
                        }
                    )
                page += 1
    except httpx.HTTPError:
        return repos
    return repos[:limit]


async def select_github_repo(full_name: str, clone_url: str | None = None) -> dict:
    """Make a GitHub repo the active working repo: clone it locally under
    REPOS_DIR (token-authed, no secret persisted to the clone) if it isn't
    already, then register + activate that local path."""
    token = _token()
    repo_name = full_name.split("/")[-1]
    dest = REPOS_DIR / repo_name
    url = clone_url or f"https://github.com/{full_name}.git"

    if not is_git_repo(str(dest)):
        REPOS_DIR.mkdir(parents=True, exist_ok=True)

        def _clone() -> tuple[int, str, str]:
            return _run([*_auth_args(token), "clone", url, str(dest)], str(REPOS_DIR), timeout=600.0)

        rc, out, err = await _to_thread(_clone)
        if rc != 0:
            raise RuntimeError((err or out) or "clone failed")

    return add_repo(str(dest))


async def _to_thread(fn):
    import asyncio

    return await asyncio.to_thread(fn)


def _looks_like_auth_error(err: str) -> bool:
    low = err.lower()
    return any(
        s in low
        for s in ("authentication", "could not read username", "403", "permission denied", "terminal prompts disabled")
    )


def push(message: str | None = None) -> dict:
    """Stage everything, commit (if there's anything to commit), and push the
    active repo's current branch to origin — creating the upstream on first
    push. Returns a structured result; `ok` is the only thing the UI needs to
    branch on, `output` is the raw git text for detail/toasts."""
    cfg = _load()
    if not cfg.active:
        return {"ok": False, "step": "select", "output": "no active repository selected"}
    p = cfg.active
    if not is_git_repo(p):
        return {"ok": False, "step": "select", "output": f"active path is not a git repo: {p}"}

    msg = (message or "").strip() or f"Update from Hawaii Agents Office — {datetime.now(UTC):%Y-%m-%d %H:%M UTC}"

    _run(["add", "-A"], p)
    _, porcelain, _ = _run(["status", "--porcelain"], p)
    committed = False
    if porcelain.strip():
        rc, out, err = _run(["commit", "-m", msg], p)
        if rc != 0:
            return {"ok": False, "step": "commit", "output": (err or out) or "commit failed"}
        committed = True

    _, branch, _ = _run(["rev-parse", "--abbrev-ref", "HEAD"], p)
    rc_u, _, _ = _run(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], p)
    push_args = ["push"] if rc_u == 0 else ["push", "-u", "origin", branch or "HEAD"]

    # First try with the user's own git credentials. If that fails on auth and
    # a GitHub token is configured, retry with the token (covers freshly cloned
    # repos and machines with no credential helper).
    rc, out, err = _run(push_args, p, timeout=120.0)
    if rc != 0 and _token() and _looks_like_auth_error(err):
        rc, out, err = _run([*_auth_args(_token()), *push_args], p, timeout=120.0)

    output = (out + ("\n" + err if err else "")).strip()
    return {
        "ok": rc == 0,
        "step": "push" if rc != 0 else None,
        "committed": committed,
        "branch": branch or None,
        "output": output[:4000] or ("pushed" if rc == 0 else "push failed"),
    }
