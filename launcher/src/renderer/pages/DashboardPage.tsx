import { useEffect, useState } from "react";
import type { DashboardSummary, SessionMetricsReport } from "../../shared/types";
import { api } from "../api";
import { StatusBadge } from "../components/Badge";
import { formatBytes } from "./SessionsPage";
import { useAppStore } from "../store";

export function DashboardPage() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<SessionMetricsReport | null>(null);
  const setTab = useAppStore((s) => s.setTab);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const s = await api().dashboardSummary() as DashboardSummary;
        if (!cancelled) { setSummary(s); setError(null); }
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    };
    load();
    const id = setInterval(load, 3000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const m = await api().sessionMetrics() as SessionMetricsReport;
        if (!cancelled) setMetrics(m);
      } catch {
        // Non-blocking: system panel just shows a placeholder.
      }
    };
    load();
    const id = setInterval(load, 5000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  if (error) {
    return (
      <div className="p-8 text-red-300">
        <p>échec du chargement du tableau de bord : {error}</p>
      </div>
    );
  }

  if (!summary) {
    return <div className="p-8 text-surface-100/50">chargement...</div>;
  }

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6">
      <div className="grid grid-cols-3 gap-4">
        <Stat
          title="Profils"
          big={summary.profiles.total}
          sub={`${summary.profiles.bound_to_proxy} liés à un proxy`}
          onClick={() => setTab("profiles")}
        />
        <Stat
          title="Proxies"
          big={summary.proxies.total}
          sub={Object.entries(summary.proxies.by_status)
            .map(([k, v]) => `${v} ${k}`).join(" • ") || "aucun"}
          onClick={() => setTab("proxies")}
        />
        <Stat
          title="Sessions en cours"
          big={summary.sessions.running}
          sub={`${summary.sessions.total} total (depuis toujours)`}
          onClick={() => setTab("sessions")}
          accent
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Panel title="Profils par OS">
          <BarList entries={summary.profiles.by_os} />
        </Panel>
        <Panel title="État des proxies">
          <div className="space-y-2">
            {Object.entries(summary.proxies.by_status).map(([status, count]) => (
              <div key={status} className="flex items-center justify-between">
                <StatusBadge status={status} />
                <span className="font-mono text-sm">{count}</span>
              </div>
            ))}
            {Object.keys(summary.proxies.by_status).length === 0 && (
              <div className="text-surface-100/40 text-sm">aucun proxy</div>
            )}
          </div>
        </Panel>
        <Panel title="Sessions par statut">
          <div className="space-y-2">
            {Object.entries(summary.sessions.by_status).map(([status, count]) => (
              <div key={status} className="flex items-center justify-between">
                <StatusBadge status={status} />
                <span className="font-mono text-sm">{count}</span>
              </div>
            ))}
            {Object.keys(summary.sessions.by_status).length === 0 && (
              <div className="text-surface-100/40 text-sm">aucune session pour le moment</div>
            )}
          </div>
        </Panel>
        <Panel title="Actions rapides">
          <div className="flex flex-col gap-2">
            <button type="button" className="btn-primary w-fit" onClick={() => setTab("sessions")}>
              Lancer une session
            </button>
            <button type="button" className="btn-ghost w-fit" onClick={() => setTab("profiles")}>
              Gérer les profils
            </button>
            <button type="button" className="btn-ghost w-fit" onClick={() => setTab("proxies")}>
              Gérer les proxies
            </button>
          </div>
        </Panel>
        <Panel title="Système">
          <SystemPanel metrics={metrics} />
        </Panel>
      </div>
    </div>
  );
}

function SystemPanel({ metrics }: { metrics: SessionMetricsReport | null }) {
  if (!metrics) {
    return <div className="text-surface-100/40 text-sm">chargement...</div>;
  }
  if (!metrics.psutil_available) {
    return (
      <div className="text-xs text-amber-300/90">
        Installez psutil pour les métriques live :{" "}
        <code className="font-mono">pip install psutil</code>
      </div>
    );
  }
  const sys = metrics.system || {};
  const memUsed = typeof sys.memory_used_bytes === "number" ? sys.memory_used_bytes : undefined;
  const memTotal = typeof sys.memory_total_bytes === "number" ? sys.memory_total_bytes : undefined;
  const running = metrics.sessions.filter(
    (s) => s.status === "running" || s.status === "starting",
  ).length;
  return (
    <div className="space-y-2 text-sm">
      <Row label="CPU total">
        <span className="font-mono">{(sys.cpu_percent ?? 0).toFixed(1)} %</span>
      </Row>
      <Row label="Mémoire">
        <span className="font-mono">
          {memUsed !== undefined && memTotal !== undefined
            ? `${formatBytes(memUsed)} / ${formatBytes(memTotal)}`
            : `${(sys.memory_percent ?? 0).toFixed(1)} %`}
        </span>
      </Row>
      <Row label="Sessions actives">
        <span className="font-mono">{running}</span>
      </Row>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-surface-100/60 text-xs">{label}</span>
      {children}
    </div>
  );
}

function Stat({ title, big, sub, onClick, accent = false }: {
  title: string; big: number | string; sub: string; onClick?: () => void; accent?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`text-left p-4 rounded-lg border transition-colors
        ${accent
          ? "bg-accent-600/10 border-accent-600/40 hover:border-accent-500"
          : "bg-surface-800 border-surface-700 hover:border-surface-200/40"}`}
    >
      <div className="text-xs text-surface-100/60 uppercase tracking-wide">{title}</div>
      <div className={`text-4xl font-bold mt-1 ${accent ? "text-accent-500" : "text-surface-100"}`}>
        {big}
      </div>
      <div className="text-xs text-surface-100/50 mt-2">{sub}</div>
    </button>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="p-4 rounded-lg bg-surface-800 border border-surface-700">
      <div className="text-xs text-surface-100/60 uppercase tracking-wide mb-3">{title}</div>
      {children}
    </div>
  );
}

function BarList({ entries }: { entries: Record<string, number> }) {
  const pairs = Object.entries(entries).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...pairs.map(([, v]) => v));
  if (pairs.length === 0) return <div className="text-surface-100/40 text-sm">aucune donnée</div>;
  return (
    <div className="space-y-2">
      {pairs.map(([k, v]) => (
        <div key={k}>
          <div className="flex justify-between text-xs">
            <span>{k}</span>
            <span className="text-surface-100/60 font-mono">{v}</span>
          </div>
          <div className="w-full h-2 mt-1 rounded-full bg-surface-900 overflow-hidden">
            <div
              className="h-full bg-accent-600"
              style={{ width: `${(v / max) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
