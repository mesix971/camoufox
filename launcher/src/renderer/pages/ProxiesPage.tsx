import { useEffect, useState } from "react";
import { api } from "../api";
import { StatusBadge } from "../components/Badge";
import { ImportProxiesModal } from "../components/ImportProxiesModal";
import { useAppStore } from "../store";

export function ProxiesPage() {
  const { proxies, proxiesLoading, proxiesError, refreshProxies, showToast } = useAppStore();
  const [showImport, setShowImport] = useState(false);
  const [checking, setChecking] = useState(false);
  const [filter, setFilter] = useState<"all" | "active" | "flagged" | "dead" | "untested">("all");

  useEffect(() => { refreshProxies(); }, [refreshProxies]);

  const remove = async (id: string) => {
    if (!confirm(`Delete proxy ${id}?`)) return;
    try {
      await api().deleteProxy(id);
      await refreshProxies();
      showToast("success", "Proxy deleted");
    } catch (e) {
      showToast("error", (e as Error).message);
    }
  };

  const checkOne = async (id: string) => {
    try {
      await api().checkProxy(id);
      await refreshProxies();
      showToast("success", "Checked");
    } catch (e) {
      showToast("error", (e as Error).message);
    }
  };

  const checkAll = async () => {
    setChecking(true);
    try {
      const res = await api().checkProxiesAll({ workers: 20 }) as { checked: number; ok: number };
      await refreshProxies();
      showToast("success", `${res.ok}/${res.checked} healthy`);
    } catch (e) {
      showToast("error", (e as Error).message);
    } finally {
      setChecking(false);
    }
  };

  const rotate = async (id: string) => {
    try {
      await api().rotateProxySession({ id });
      await refreshProxies();
      showToast("success", "Session rotated");
    } catch (e) {
      showToast("error", (e as Error).message);
    }
  };

  const visible = filter === "all" ? proxies : proxies.filter((p) => p.status === filter);

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between px-4 py-3 border-b border-surface-700">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold">Proxies</h2>
          <span className="text-xs text-surface-100/60">
            {visible.length} / {proxies.length}
          </span>
          <select
            className="input !w-auto !py-1 !text-xs"
            value={filter}
            onChange={(e) => setFilter(e.target.value as typeof filter)}
          >
            <option value="all">all</option>
            <option value="active">active</option>
            <option value="untested">untested</option>
            <option value="flagged">flagged</option>
            <option value="dead">dead</option>
          </select>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" className="btn-ghost" onClick={checkAll} disabled={checking}>
            {checking ? "Checking..." : "Check all"}
          </button>
          <button type="button" className="btn-ghost" onClick={() => refreshProxies()} disabled={proxiesLoading}>
            Refresh
          </button>
          <button type="button" className="btn-primary" onClick={() => setShowImport(true)}>
            + Import
          </button>
        </div>
      </div>

      {proxiesError && (
        <div className="px-4 py-2 bg-red-900/60 text-red-200 text-sm border-b border-red-800">
          {proxiesError}
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {visible.length === 0 && !proxiesLoading && (
          <div className="p-8 text-center text-surface-100/50">
            No proxies. Click <b>+ Import</b> to paste a list.
          </div>
        )}
        <table className="w-full text-sm">
          <thead className="text-xs uppercase text-surface-100/50 bg-surface-800/60 sticky top-0">
            <tr>
              <th className="text-left px-4 py-2 font-medium">Status</th>
              <th className="text-left px-4 py-2 font-medium">Provider</th>
              <th className="text-left px-4 py-2 font-medium">Host:Port</th>
              <th className="text-left px-4 py-2 font-medium">Country</th>
              <th className="text-right px-4 py-2 font-medium">Latency</th>
              <th className="text-left px-4 py-2 font-medium">Tags</th>
              <th className="text-left px-4 py-2 font-medium">Last check</th>
              <th className="text-right px-4 py-2 font-medium">Uses</th>
              <th className="text-right px-4 py-2 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((p) => (
              <tr key={p.id} className="table-row">
                <td className="px-4 py-2"><StatusBadge status={p.status} /></td>
                <td className="px-4 py-2 text-xs">{p.provider}</td>
                <td className="px-4 py-2 font-mono text-xs">{p.host}:{p.port}</td>
                <td className="px-4 py-2 text-xs">{p.observed_country || p.country || "-"}</td>
                <td className="px-4 py-2 text-right text-xs">
                  {p.latency_ms != null ? `${Math.round(p.latency_ms)} ms` : "-"}
                </td>
                <td className="px-4 py-2 text-xs">{p.tags.join(", ") || "-"}</td>
                <td className="px-4 py-2 text-xs text-surface-100/60">
                  {p.last_checked_at ? new Date(p.last_checked_at).toLocaleString() : "-"}
                </td>
                <td className="px-4 py-2 text-right">{p.use_count}</td>
                <td className="px-4 py-2 text-right">
                  <div className="flex items-center justify-end gap-1">
                    <button type="button" className="btn-ghost !py-1 !text-xs" onClick={() => checkOne(p.id)}>
                      Check
                    </button>
                    {p.provider === "iproyal" && (
                      <button type="button" className="btn-ghost !py-1 !text-xs" onClick={() => rotate(p.id)}>
                        Rotate
                      </button>
                    )}
                    <button type="button" className="btn-danger !py-1 !text-xs" onClick={() => remove(p.id)}>
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ImportProxiesModal open={showImport} onClose={() => setShowImport(false)} />
    </div>
  );
}
