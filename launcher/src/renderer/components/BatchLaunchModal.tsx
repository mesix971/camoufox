import { useEffect, useMemo, useState } from "react";
import type {
  BatchLaunchResult, LaunchOptions, ProxyStrategy,
} from "../../shared/types";
import { api } from "../api";
import { useAppStore } from "../store";
import { AdvancedLaunchOptions } from "./AdvancedLaunchOptions";
import { Modal } from "./Modal";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function BatchLaunchModal({ open, onClose }: Props) {
  const profiles = useAppStore((s) => s.profiles);
  const proxies = useAppStore((s) => s.proxies);
  const refreshSessions = useAppStore((s) => s.refreshSessions);
  const showToast = useAppStore((s) => s.showToast);

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [strategy, setStrategy] = useState<ProxyStrategy>("bound");
  const [fixedProxyId, setFixedProxyId] = useState<string>("");
  const [url, setUrl] = useState("");
  const [headless, setHeadless] = useState(false);
  const [countryFilter, setCountryFilter] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<BatchLaunchResult | null>(null);
  const [osFilter, setOsFilter] = useState<string>("");
  const [tagFilter, setTagFilter] = useState<string>("");
  const [advanced, setAdvanced] = useState<LaunchOptions>({});

  useEffect(() => {
    if (open) {
      setSelected(new Set());
      setResult(null);
      setAdvanced({});
    }
  }, [open]);

  const visibleProfiles = useMemo(
    () => profiles.filter((p) => {
      if (osFilter && p.os !== osFilter) return false;
      if (tagFilter && !p.tags.includes(tagFilter)) return false;
      return true;
    }),
    [profiles, osFilter, tagFilter],
  );

  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };

  const selectAllVisible = () =>
    setSelected(new Set(visibleProfiles.map((p) => p.id)));

  const clearAll = () => setSelected(new Set());

  const submit = async () => {
    if (selected.size === 0) {
      showToast("error", "choisir au moins un profil");
      return;
    }
    if (strategy === "fixed" && !fixedProxyId) {
      showToast("error", "la stratégie fixe nécessite un proxy");
      return;
    }
    setSubmitting(true);
    try {
      const args: Parameters<typeof window.api.batchLaunchSession>[0] = {
        profile_ids: Array.from(selected),
        strategy,
        headless,
      };
      if (url) args.url = url;
      if (strategy === "fixed") args.proxy_id = fixedProxyId;
      if (strategy === "round-robin" && countryFilter) {
        args.proxy_filter = { country: countryFilter };
      }
      if (advanced.warmup) args.warmup = true;
      if (advanced.persistent) args.persistent = true;
      if (advanced.queue_monitor) args.queue_monitor = true;
      if (advanced.auto_refresh) args.auto_refresh = advanced.auto_refresh;
      if (advanced.rate_limit) args.rate_limit = advanced.rate_limit;
      const res = await api().batchLaunchSession(args) as BatchLaunchResult;
      setResult(res);
      await refreshSessions();
      showToast(
        res.failures.length ? "info" : "success",
        `lancées ${res.count}/${selected.size}`,
      );
    } catch (e) {
      showToast("error", (e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Lancement en lot"
      width="max-w-3xl"
      footer={
        <>
          <button type="button" className="btn-ghost" onClick={onClose}>
            {result ? "Terminé" : "Annuler"}
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={submit}
            disabled={submitting || selected.size === 0}
          >
            {submitting ? "Lancement..." : `Lancer ${selected.size}`}
          </button>
        </>
      }
    >
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <select className="input !w-auto !py-1" value={osFilter} onChange={(e) => setOsFilter(e.target.value)}>
            <option value="">tout OS</option>
            <option value="windows">windows</option>
            <option value="macos">macos</option>
            <option value="linux">linux</option>
          </select>
          <input
            className="input !w-auto !py-1"
            placeholder="filtre par tag"
            value={tagFilter}
            onChange={(e) => setTagFilter(e.target.value)}
          />
          <button type="button" className="btn-ghost !py-1 !text-xs" onClick={selectAllVisible}>
            Tout sélectionner
          </button>
          <button type="button" className="btn-ghost !py-1 !text-xs" onClick={clearAll}>
            Effacer
          </button>
          <span className="text-xs text-surface-100/60">
            {selected.size} / {visibleProfiles.length} sélectionnés
          </span>
        </div>

        <div className="border border-surface-700 rounded max-h-56 overflow-y-auto">
          <table className="w-full text-xs">
            <tbody>
              {visibleProfiles.map((p) => (
                <tr
                  key={p.id}
                  onClick={() => toggle(p.id)}
                  className={`cursor-pointer border-b border-surface-700/40 ${
                    selected.has(p.id) ? "bg-accent-600/20" : "hover:bg-surface-800/50"
                  }`}
                >
                  <td className="px-2 py-1 w-6">
                    <input type="checkbox" checked={selected.has(p.id)} readOnly />
                  </td>
                  <td className="px-2 py-1">{p.name}</td>
                  <td className="px-2 py-1">{p.os}</td>
                  <td className="px-2 py-1">{p.locale}</td>
                  <td className="px-2 py-1 text-surface-100/60">
                    {p.proxy_id ? "lié" : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-surface-100/60 mb-1">Stratégie de proxy</label>
            <select
              className="input"
              value={strategy}
              onChange={(e) => setStrategy(e.target.value as ProxyStrategy)}
            >
              <option value="bound">lié (utiliser le proxy_id de chaque profil)</option>
              <option value="round-robin">tourniquet sur le pool</option>
              <option value="fixed">fixe (même proxy pour tous)</option>
              <option value="none">aucun proxy</option>
            </select>
          </div>
          {strategy === "fixed" && (
            <div>
              <label className="block text-xs text-surface-100/60 mb-1">Proxy fixe</label>
              <select className="input" value={fixedProxyId} onChange={(e) => setFixedProxyId(e.target.value)}>
                <option value="">— sélectionner —</option>
                {proxies.filter((p) => p.status !== "dead").map((p) => (
                  <option key={p.id} value={p.id}>{p.label} [{p.status}]</option>
                ))}
              </select>
            </div>
          )}
          {strategy === "round-robin" && (
            <div>
              <label className="block text-xs text-surface-100/60 mb-1">Filtre par pays (optionnel)</label>
              <input className="input" placeholder="ex. US" value={countryFilter}
                     onChange={(e) => setCountryFilter(e.target.value)} />
            </div>
          )}
          <div className="col-span-2">
            <label className="block text-xs text-surface-100/60 mb-1">URL initiale (optionnelle, appliquée à toutes)</label>
            <input className="input" placeholder="https://example.com" value={url}
                   onChange={(e) => setUrl(e.target.value)} />
          </div>
          <label className="flex items-center gap-2 text-sm col-span-2">
            <input type="checkbox" checked={headless} onChange={(e) => setHeadless(e.target.checked)} />
            Headless (sans interface)
          </label>
          <div className="col-span-2">
            <AdvancedLaunchOptions value={advanced} onChange={setAdvanced} />
          </div>
        </div>

        {result && (
          <div className="mt-2 p-3 bg-surface-900 border border-surface-700 rounded text-xs">
            <div>lancées : <b className="text-green-400">{result.count}</b></div>
            <div>échecs : <b className="text-red-400">{result.failures.length}</b></div>
            {result.failures.length > 0 && (
              <ul className="mt-2 space-y-0.5 text-red-300/80 max-h-28 overflow-y-auto">
                {result.failures.map((f, i) => (
                  <li key={i}><code>{f.profile_id}</code> : {f.error}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}
