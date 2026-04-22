import { useEffect, useState } from "react";
import { api } from "../api";
import { StatusBadge } from "../components/Badge";
import { LaunchSessionModal } from "../components/LaunchSessionModal";
import { Modal } from "../components/Modal";
import { useAppStore } from "../store";

export function SessionsPage() {
  const { sessions, sessionsLoading, sessionsError, refreshSessions, showToast } = useAppStore();
  const [showLaunch, setShowLaunch] = useState(false);
  const [logFor, setLogFor] = useState<string | null>(null);
  const [logText, setLogText] = useState("");

  // Poll sessions every 2s so status transitions show up without a manual refresh.
  useEffect(() => {
    refreshSessions();
    const id = setInterval(refreshSessions, 2000);
    return () => clearInterval(id);
  }, [refreshSessions]);

  useEffect(() => {
    if (!logFor) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const res = await api().sessionLog(logFor) as { log: string };
        if (!cancelled) setLogText(res.log || "(empty)");
      } catch (e) {
        if (!cancelled) setLogText(`error: ${(e as Error).message}`);
      }
    };
    tick();
    const id = setInterval(tick, 1500);
    return () => { cancelled = true; clearInterval(id); };
  }, [logFor]);

  const kill = async (id: string) => {
    try {
      await api().killSession(id);
      await refreshSessions();
      showToast("success", "Session killed");
    } catch (e) {
      showToast("error", (e as Error).message);
    }
  };

  const prune = async () => {
    try {
      const res = await api().pruneSessions() as { pruned: number };
      await refreshSessions();
      showToast("success", `${res.pruned} stopped sessions cleared`);
    } catch (e) {
      showToast("error", (e as Error).message);
    }
  };

  const runningCount = sessions.filter((s) => s.status === "running" || s.status === "starting").length;

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between px-4 py-3 border-b border-surface-700">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold">Sessions</h2>
          <span className="text-xs text-surface-100/60">
            {runningCount} running / {sessions.length} total
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" className="btn-ghost" onClick={prune}>Prune stopped</button>
          <button type="button" className="btn-ghost" onClick={() => refreshSessions()} disabled={sessionsLoading}>
            Refresh
          </button>
          <button type="button" className="btn-primary" onClick={() => setShowLaunch(true)}>
            + Launch
          </button>
        </div>
      </div>

      {sessionsError && (
        <div className="px-4 py-2 bg-red-900/60 text-red-200 text-sm border-b border-red-800">
          {sessionsError}
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {sessions.length === 0 && !sessionsLoading && (
          <div className="p-8 text-center text-surface-100/50">
            No sessions. Click <b>+ Launch</b> to start one.
          </div>
        )}
        <table className="w-full text-sm">
          <thead className="text-xs uppercase text-surface-100/50 bg-surface-800/60 sticky top-0">
            <tr>
              <th className="text-left px-4 py-2 font-medium">Status</th>
              <th className="text-left px-4 py-2 font-medium">ID</th>
              <th className="text-left px-4 py-2 font-medium">PID</th>
              <th className="text-left px-4 py-2 font-medium">Profile</th>
              <th className="text-left px-4 py-2 font-medium">Proxy</th>
              <th className="text-left px-4 py-2 font-medium">URL</th>
              <th className="text-left px-4 py-2 font-medium">Started</th>
              <th className="text-right px-4 py-2 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map((s) => (
              <tr key={s.id} className="table-row">
                <td className="px-4 py-2"><StatusBadge status={s.status} /></td>
                <td className="px-4 py-2 font-mono text-xs">{s.id}</td>
                <td className="px-4 py-2 font-mono text-xs">{s.pid}</td>
                <td className="px-4 py-2 text-xs">{s.profile_id}</td>
                <td className="px-4 py-2 text-xs">{s.proxy_id || "-"}</td>
                <td className="px-4 py-2 text-xs truncate max-w-xs">{s.url || "-"}</td>
                <td className="px-4 py-2 text-xs text-surface-100/60">
                  {new Date(s.started_at).toLocaleString()}
                </td>
                <td className="px-4 py-2 text-right">
                  <div className="flex items-center justify-end gap-1">
                    <button type="button" className="btn-ghost !py-1 !text-xs" onClick={() => setLogFor(s.id)}>
                      Logs
                    </button>
                    {(s.status === "running" || s.status === "starting") && (
                      <button type="button" className="btn-danger !py-1 !text-xs" onClick={() => kill(s.id)}>
                        Kill
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <LaunchSessionModal open={showLaunch} onClose={() => setShowLaunch(false)} />

      <Modal
        open={logFor !== null}
        onClose={() => { setLogFor(null); setLogText(""); }}
        title={`Session logs — ${logFor?.slice(0, 12) || ""}`}
        width="max-w-4xl"
      >
        <pre className="bg-surface-900 border border-surface-700 rounded p-3 text-xs font-mono overflow-auto max-h-[60vh] whitespace-pre-wrap">
          {logText}
        </pre>
      </Modal>
    </div>
  );
}
