import { useEffect, useState } from "react";
import {
  Users, Globe, Monitor, Cpu, MemoryStick, Activity,
  Zap, ArrowUpRight, LayoutDashboard, type LucideIcon,
} from "lucide-react";
import type { DashboardSummary, SessionMetricsReport } from "../../shared/types";
import { api } from "../api";
import { StatusBadge } from "../components/Badge";
import { PageHeader } from "../components/PageHeader";
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
    <div className="h-full overflow-y-auto">
      <PageHeader
        title="Tableau de bord"
        subtitle="Vue d'ensemble — profils, proxies, sessions et état du système."
        icon={LayoutDashboard}
        badge={
          summary.sessions.running > 0
            ? { label: `${summary.sessions.running} en cours`, tone: "success" }
            : undefined
        }
      />

      <div className="p-6 space-y-6">
      <div className="grid grid-cols-3 gap-4">
        <Stat
          title="Profils"
          big={summary.profiles.total}
          sub={`${summary.profiles.bound_to_proxy} liés à un proxy`}
          icon={Users}
          onClick={() => setTab("profiles")}
        />
        <Stat
          title="Proxies"
          big={summary.proxies.total}
          sub={Object.entries(summary.proxies.by_status)
            .map(([k, v]) => `${v} ${k}`).join(" • ") || "aucun"}
          icon={Globe}
          onClick={() => setTab("proxies")}
        />
        <Stat
          title="Sessions en cours"
          big={summary.sessions.running}
          sub={`${summary.sessions.total} total (depuis toujours)`}
          icon={Monitor}
          onClick={() => setTab("sessions")}
          accent
          pulse={summary.sessions.running > 0}
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
              <Zap size={14} strokeWidth={2.5} />
              Lancer une session
            </button>
            <button type="button" className="btn-ghost w-fit" onClick={() => setTab("profiles")}>
              <Users size={14} strokeWidth={2} />
              Gérer les profils
            </button>
            <button type="button" className="btn-ghost w-fit" onClick={() => setTab("proxies")}>
              <Globe size={14} strokeWidth={2} />
              Gérer les proxies
            </button>
          </div>
        </Panel>
        <Panel title="Système">
          <SystemPanel metrics={metrics} />
        </Panel>
      </div>
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
  const cpu = sys.cpu_percent ?? 0;
  const memPct = memUsed !== undefined && memTotal !== undefined && memTotal > 0
    ? (memUsed / memTotal) * 100
    : (sys.memory_percent ?? 0);

  return (
    <div className="space-y-3 text-sm">
      <MetricRow
        icon={Cpu}
        label="CPU"
        value={`${cpu.toFixed(1)} %`}
        percent={cpu}
      />
      <MetricRow
        icon={MemoryStick}
        label="Mémoire"
        value={memUsed !== undefined && memTotal !== undefined
          ? `${formatBytes(memUsed)} / ${formatBytes(memTotal)}`
          : `${memPct.toFixed(1)} %`}
        percent={memPct}
      />
      <MetricRow
        icon={Activity}
        label="Sessions actives"
        value={String(running)}
      />
    </div>
  );
}

function MetricRow({ icon: Icon, label, value, percent }: {
  icon: LucideIcon;
  label: string;
  value: string;
  percent?: number;
}) {
  const pct = Math.max(0, Math.min(100, percent ?? 0));
  // Color shifts as load increases.
  const barClass = pct > 85 ? "bg-red-500" : pct > 65 ? "bg-amber-400" : "bg-accent-500";
  return (
    <div>
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-surface-100/60 text-xs">
          <Icon size={12} strokeWidth={2.2} />
          {label}
        </span>
        <span className="font-mono text-xs tabular-nums">{value}</span>
      </div>
      {percent !== undefined && (
        <div className="w-full h-1.5 mt-1.5 rounded-full bg-surface-900 overflow-hidden">
          <div
            className={`h-full ${barClass} transition-all duration-500`}
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
    </div>
  );
}

function Stat({ title, big, sub, onClick, accent = false, icon, pulse = false }: {
  title: string;
  big: number | string;
  sub: string;
  onClick?: () => void;
  accent?: boolean;
  icon?: LucideIcon;
  pulse?: boolean;
}) {
  const Icon = icon;
  return (
    <button
      type="button"
      onClick={onClick}
      className={`group relative text-left p-5 rounded-lg border transition-all overflow-hidden
        ${accent
          ? "bg-accent-600/10 border-accent-600/40 hover:border-accent-500 hover:shadow-glow"
          : "bg-surface-800 border-surface-700 hover:border-surface-200/40"}`}
    >
      {/* radial accent glow visible on hover */}
      <span
        aria-hidden="true"
        className={`pointer-events-none absolute -top-12 -right-12 w-40 h-40 rounded-full
          bg-accent-500/20 blur-3xl opacity-0 transition-opacity duration-300
          group-hover:opacity-100 ${accent ? "opacity-60" : ""}`}
      />
      <div className="relative flex items-start justify-between">
        <div className="flex items-center gap-2">
          {Icon && (
            <span className={`inline-flex items-center justify-center w-7 h-7 rounded-md
              ${accent ? "bg-accent-500/20 text-accent-500" : "bg-surface-900 text-surface-100/70"}`}>
              <Icon size={14} strokeWidth={2.5} />
            </span>
          )}
          <div className="text-xs text-surface-100/60 uppercase tracking-wide font-medium">
            {title}
          </div>
        </div>
        <ArrowUpRight
          size={14}
          className="text-surface-100/30 group-hover:text-surface-100/70 transition-colors"
        />
      </div>
      <div className={`relative text-4xl font-bold mt-3 tabular-nums tracking-tight
        ${accent ? "text-accent-500" : "text-surface-100"}`}>
        {big}
        {pulse && (
          <span className="ml-2 inline-block w-2 h-2 rounded-full bg-green-400 align-middle
            animate-pulse shadow-[0_0_8px] shadow-green-400" />
        )}
      </div>
      <div className="relative text-xs text-surface-100/50 mt-2">{sub}</div>
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
  const total = pairs.reduce((s, [, v]) => s + v, 0);
  if (pairs.length === 0) return <div className="text-surface-100/40 text-sm">aucune donnée</div>;
  return (
    <div className="space-y-3">
      {pairs.map(([k, v]) => {
        const pct = (v / max) * 100;
        const share = total > 0 ? ((v / total) * 100).toFixed(0) : "0";
        return (
          <div key={k}>
            <div className="flex justify-between text-xs mb-1">
              <span className="font-medium">{k}</span>
              <span className="text-surface-100/60 font-mono tabular-nums">
                {v}
                <span className="text-surface-100/30 ml-1.5">{share}%</span>
              </span>
            </div>
            <div className="w-full h-2 rounded-full bg-surface-900 overflow-hidden">
              <div
                className="h-full rounded-full bg-gradient-to-r from-accent-600 to-accent-500
                  transition-all duration-700 ease-out"
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
