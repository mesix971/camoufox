import { useEffect, useState } from "react";
import type { LaunchOptions } from "../../shared/types";
import { api } from "../api";
import { useAppStore } from "../store";
import { AdvancedLaunchOptions } from "./AdvancedLaunchOptions";
import { Modal } from "./Modal";

interface Props {
  open: boolean;
  onClose: () => void;
  initialProfileId?: string | null;
}

export function LaunchSessionModal({ open, onClose, initialProfileId }: Props) {
  const profiles = useAppStore((s) => s.profiles);
  const proxies = useAppStore((s) => s.proxies);
  const refreshSessions = useAppStore((s) => s.refreshSessions);
  const showToast = useAppStore((s) => s.showToast);

  const [profileId, setProfileId] = useState("");
  const [proxyId, setProxyId] = useState("");
  const [url, setUrl] = useState("");
  const [headless, setHeadless] = useState(false);
  const [advanced, setAdvanced] = useState<LaunchOptions>({});
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setProfileId(initialProfileId || "");
      setProxyId("");
      setUrl("");
      setHeadless(false);
      setAdvanced({});
    }
  }, [open, initialProfileId]);

  // Auto-suggest: if the selected profile has a bound proxy, pre-pick it.
  useEffect(() => {
    const prof = profiles.find((p) => p.id === profileId);
    if (prof && prof.proxy_id) setProxyId(prof.proxy_id);
  }, [profileId, profiles]);

  const submit = async () => {
    if (!profileId) {
      showToast("error", "choisir un profil");
      return;
    }
    setSubmitting(true);
    try {
      const args: Parameters<typeof window.api.launchSession>[0] = {
        profile_id: profileId,
        headless,
      };
      if (proxyId) args.proxy_id = proxyId;
      if (url) args.url = url;
      if (advanced.warmup) args.warmup = true;
      if (advanced.persistent) args.persistent = true;
      if (advanced.queue_monitor) args.queue_monitor = true;
      if (advanced.auto_refresh) args.auto_refresh = advanced.auto_refresh;
      if (advanced.rate_limit) args.rate_limit = advanced.rate_limit;
      if (advanced.humanlike) args.humanlike = true;
      if (advanced.run_macro) args.run_macro = advanced.run_macro;
      await api().launchSession(args);
      await refreshSessions();
      showToast("success", "Session démarrée");
      onClose();
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
      title="Lancer une session"
      footer={
        <>
          <button type="button" className="btn-ghost" onClick={onClose}>Annuler</button>
          <button type="button" className="btn-primary" onClick={submit} disabled={submitting}>
            {submitting ? "Démarrage..." : "Lancer"}
          </button>
        </>
      }
    >
      <div className="space-y-3">
        <div>
          <label className="block text-xs text-surface-100/60 mb-1">Profil</label>
          <select className="input" value={profileId} onChange={(e) => setProfileId(e.target.value)}>
            <option value="">— sélectionner —</option>
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.os}, {p.locale})
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-surface-100/60 mb-1">Proxy (optionnel)</label>
          <select className="input" value={proxyId} onChange={(e) => setProxyId(e.target.value)}>
            <option value="">(aucun proxy)</option>
            {proxies.filter((p) => p.status !== "dead").map((p) => (
              <option key={p.id} value={p.id}>
                {p.label} [{p.status}] {p.observed_country || p.country || ""}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-surface-100/60 mb-1">URL initiale (optionnelle)</label>
          <input className="input" placeholder="https://example.com"
                 value={url} onChange={(e) => setUrl(e.target.value)} />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={headless} onChange={(e) => setHeadless(e.target.checked)} />
          Headless (sans interface)
        </label>

        <AdvancedLaunchOptions value={advanced} onChange={setAdvanced} />
      </div>
    </Modal>
  );
}
