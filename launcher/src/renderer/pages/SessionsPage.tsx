import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { StatusBadge } from "../components/Badge";
import { BatchLaunchModal } from "../components/BatchLaunchModal";
import { LaunchSessionModal } from "../components/LaunchSessionModal";
import { Modal } from "../components/Modal";
import { useAppStore } from "../store";

export function SessionsPage() {
  const {
    sessions, sessionsLoading, sessionsError, refreshSessions,
    profiles, refreshProfiles, refreshProxies, showToast,
    psutilAvailable,
  } = useAppStore();

  const profileMap = useMemo(
    () => new Map(profiles.map((p) => [p.id, p])),
    [profiles],
  );
  const [showLaunch, setShowLaunch] = useState(false);
  const [showBatch, setShowBatch] = useState(false);
  const [logFor, setLogFor] = useState<string | null>(null);
  const [logText, setLogText] = useState("");

  // Preload profiles and proxies for the batch modal.
  useEffect(() => {
    refreshProfiles();
    refreshProxies();
  }, [refreshProfiles, refreshProxies]);

  // Poll sessions every 2s so status transitions show up without a manual refresh.
  useEffect(() => {
    const tick = () => refreshSessions({ metrics: true });
    tick();
    const id = setInterval(tick, 2000);
    return () => clearInterval(id);
  }, [refreshSessions]);

  useEffect(() => {
    if (!logFor) return;
    let cancelled = false;
    const tick = async () => {
      try {
        const res = await api().sessionLog(logFor) as { log: string };
        if (!cancelled) setLogText(res.log || "(vide)");
      } catch (e) {
        if (!cancelled) setLogText(`erreur : ${(e as Error).message}`);
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
      showToast("success", "Session arrêtée");
    } catch (e) {
      showToast("error", (e as Error).message);
    }
  };

  const prune = async () => {
    try {
      const res = await api().pruneSessions() as { pruned: number };
      await refreshSessions();
      showToast("success", `${res.pruned} sessions arrêtées purgées`);
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
            {runningCount} actives / {sessions.length} total
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" className="btn-ghost" onClick={prune}>Purger arrêtées</button>
          <button type="button" className="btn-ghost" onClick={() => refreshSessions()} disabled={sessionsLoading}>
            Rafraîchir
          </button>
          <button type="button" className="btn-ghost" onClick={() => setShowBatch(true)}>
            + Lot
          </button>
          <button type="button" className="btn-primary" onClick={() => setShowLaunch(true)}>
            + Lancer
          </button>
        </div>
      </div>

      {sessionsError && (
        <div className="px-4 py-2 bg-red-900/60 text-red-200 text-sm border-b border-red-800">
          {sessionsError}
        </div>
      )}

      {!psutilAvailable && (
        <div className="px-4 py-2 bg-amber-900/40 text-amber-200 text-xs border-b border-amber-800">
          Installez psutil pour les métriques live : <code className="font-mono">pip install psutil</code>
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {sessions.length === 0 && !sessionsLoading && (
          <div className="p-8 text-center text-surface-100/50">
            Aucune session. Cliquez sur <b>+ Lancer</b> pour en démarrer une.
          </div>
        )}
        <table className="w-full text-sm">
          <thead className="text-xs uppercase text-surface-100/50 bg-surface-800/60 sticky top-0">
            <tr>
              <th className="text-left px-4 py-2 font-medium">Statut</th>
              <th className="text-left px-4 py-2 font-medium">ID</th>
              <th className="text-left px-4 py-2 font-medium">PID</th>
              <th className="text-right px-4 py-2 font-medium">CPU %</th>
              <th className="text-right px-4 py-2 font-medium">RAM</th>
              <th className="text-left px-4 py-2 font-medium">Profil</th>
              <th className="text-left px-4 py-2 font-medium">Proxy</th>
              <th className="text-left px-4 py-2 font-medium">URL</th>
              <th className="text-left px-4 py-2 font-medium">Démarrée</th>
              <th className="text-right px-4 py-2 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map((s) => (
              <tr key={s.id} className="table-row">
                <td className="px-4 py-2"><StatusBadge status={s.status} /></td>
                <td className="px-4 py-2 font-mono text-xs">{s.id}</td>
                <td className="px-4 py-2 font-mono text-xs">{s.pid}</td>
                <td className="px-4 py-2 text-right font-mono text-xs">
                  {formatCpu(s.metrics?.cpu_percent)}
                </td>
                <td className="px-4 py-2 text-right font-mono text-xs">
                  {formatBytes(s.metrics?.rss_bytes)}
                </td>
                <td className="px-4 py-2 text-xs" title={s.profile_id}>
                  {profileMap.get(s.profile_id)?.name ?? s.profile_id.slice(0, 8)}
                </td>
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
                        Arrêter
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
      <BatchLaunchModal open={showBatch} onClose={() => setShowBatch(false)} />

      <Modal
        open={logFor !== null}
        onClose={() => { setLogFor(null); setLogText(""); }}
        title={`Logs de session — ${logFor?.slice(0, 12) || ""}`}
        width="max-w-4xl"
      >
        <pre className="bg-surface-900 border border-surface-700 rounded p-3 text-xs font-mono overflow-auto max-h-[60vh] whitespace-pre-wrap">
          {logText}
        </pre>
      </Modal>
    </div>
  );
}

function formatCpu(v: number | undefined): string {
  if (v === undefined || v === null || Number.isNaN(v)) return "—";
  return `${v.toFixed(1)}`;
}

export function formatBytes(bytes: number | undefined): string {
  if (bytes === undefined || bytes === null || Number.isNaN(bytes)) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let v = bytes;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  const formatted = v >= 100 || i === 0 ? v.toFixed(0) : v.toFixed(1);
  return `${formatted} ${units[i]}`;
}
