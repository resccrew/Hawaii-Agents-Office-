"use client";

import { useEffect, useRef, useState } from "react";
import { useGitStore } from "@/stores/gitStore";

// The git bar docked under the office: connect a GitHub account, pick any of
// its repositories to work on, and push with one click. Sits between the two
// side panels, directly below the office canvas.
export function GitBar() {
  const {
    active,
    repos,
    pushing,
    lastPush,
    error,
    github,
    githubRepos,
    connecting,
    selecting,
    refresh,
    setActive,
    push,
    clearPushResult,
    fetchGithub,
    connectGithub,
    selectGithub,
  } = useGitStore();

  const [message, setMessage] = useState("");
  const [showConnect, setShowConnect] = useState(false);
  const [token, setToken] = useState("");
  const tokenRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    void refresh();
    void fetchGithub();
  }, [refresh, fetchGithub]);

  useEffect(() => {
    if (showConnect) tokenRef.current?.focus();
  }, [showConnect]);

  useEffect(() => {
    if (!lastPush) return;
    const t = window.setTimeout(() => clearPushResult(), 8000);
    return () => window.clearTimeout(t);
  }, [lastPush, clearPushResult]);

  const connected = !!github?.connected;
  const activeRepo = repos.find((r) => r.path === active) ?? null;
  const activeName = active ? active.split("/").pop() : null;
  // Which GitHub repo (if any) corresponds to the active local checkout.
  const selectedFullName =
    githubRepos.find((r) => r.fullName.split("/").pop() === activeName)?.fullName ?? "";

  const submitConnect = async () => {
    const t = token.trim();
    if (!t) return;
    const ok = await connectGithub(t);
    if (ok) {
      setToken("");
      setShowConnect(false);
    }
  };

  const handlePush = () => {
    setMessage("");
    void push(message);
  };

  const dirty = activeRepo?.dirty ?? 0;
  const ahead = activeRepo?.ahead ?? 0;

  return (
    <div className="git-bar">
      <span className="git-bar-glyph" title="git" aria-hidden="true">⎇</span>

      {/* --- account --- */}
      {connected ? (
        <span className="git-bar-account" title={`connected as ${github?.login}`}>
          <span className="git-bar-dot git-bar-dot-clean" />@{github?.login}
        </span>
      ) : showConnect ? (
        <div className="git-bar-add">
          <input
            ref={tokenRef}
            className="git-bar-add-input"
            type="password"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void submitConnect();
              if (e.key === "Escape") setShowConnect(false);
            }}
            placeholder="paste a GitHub token (repo scope)"
          />
          <button className="git-bar-btn" onClick={() => void submitConnect()} disabled={connecting}>
            {connecting ? "…" : "connect"}
          </button>
          <button className="git-bar-btn git-bar-btn-ghost" onClick={() => setShowConnect(false)}>
            cancel
          </button>
        </div>
      ) : (
        <button className="git-bar-btn" onClick={() => setShowConnect(true)} title="connect a GitHub account">
          Connect GitHub
        </button>
      )}

      {/* --- repo picker --- */}
      {connected && !showConnect && (
        <>
          <select
            className="git-bar-select"
            value={selectedFullName}
            onChange={(e) => {
              const repo = githubRepos.find((r) => r.fullName === e.target.value);
              if (repo) void selectGithub(repo);
            }}
            title="choose a repository from your GitHub account"
            disabled={!!selecting}
          >
            <option value="">
              {selecting ? `cloning ${selecting.split("/").pop()}…` : "select a repository…"}
            </option>
            {githubRepos.map((r) => (
              <option key={r.fullName} value={r.fullName}>
                {r.fullName}
                {r.private ? " 🔒" : ""}
              </option>
            ))}
          </select>
          {activeRepo && (
            <span className="git-bar-status" title={activeRepo.remote ?? "no remote"}>
              <span className={`git-bar-dot ${dirty > 0 ? "git-bar-dot-dirty" : "git-bar-dot-clean"}`} />
              {activeName}
              {activeRepo.branch ? ` · ${activeRepo.branch}` : ""}
              {dirty > 0 ? ` · ${dirty} change${dirty === 1 ? "" : "s"}` : ""}
              {ahead > 0 ? ` · ${ahead} to push` : ""}
            </span>
          )}
        </>
      )}

      {/* --- not connected: fall back to local repo list so the bar still works --- */}
      {!connected && !showConnect && repos.length > 0 && (
        <>
          <select
            className="git-bar-select"
            value={active ?? ""}
            onChange={(e) => void setActive(e.target.value)}
            title="local repository"
          >
            {repos.map((r) => (
              <option key={r.path} value={r.path}>
                {r.name}
                {r.branch ? ` (${r.branch})` : ""}
              </option>
            ))}
          </select>
          {activeRepo && (
            <span className="git-bar-status" title={activeRepo.remote ?? "no remote"}>
              <span className={`git-bar-dot ${dirty > 0 ? "git-bar-dot-dirty" : "git-bar-dot-clean"}`} />
              {dirty > 0 ? `${dirty} change${dirty === 1 ? "" : "s"}` : "clean"}
              {ahead > 0 ? ` · ${ahead} to push` : ""}
            </span>
          )}
        </>
      )}

      <div className="git-bar-spacer" />

      {lastPush && (
        <span
          className={`git-bar-result ${lastPush.ok ? "git-bar-result-ok" : "git-bar-result-err"}`}
          title={lastPush.output}
        >
          {lastPush.ok ? "✓ pushed to GitHub" : `✗ ${lastPush.output.split("\n")[0].slice(0, 60)}`}
        </span>
      )}
      {error && !lastPush && (
        <span className="git-bar-result git-bar-result-err" title={error}>
          {error.slice(0, 60)}
        </span>
      )}

      {!showConnect && (
        <>
          <input
            className="git-bar-msg"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handlePush()}
            placeholder="commit message (optional)"
          />
          <button
            className="git-bar-push"
            onClick={handlePush}
            disabled={pushing || !activeRepo}
            title="commit all changes and push to GitHub"
          >
            {pushing ? "pushing…" : "⬆ Push to GitHub"}
          </button>
        </>
      )}
    </div>
  );
}
