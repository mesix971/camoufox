import { useEffect, useState } from "react";
import type { ProfileSummary } from "../../shared/types";
import { api } from "../api";
import { useAppStore } from "../store";
import { Modal } from "./Modal";

interface Props {
  open: boolean;
  onClose: () => void;
  profile: ProfileSummary | null;
}

export function BindProxyModal({ open, onClose, profile }: Props) {
  const proxies = useAppStore((s) => s.proxies);
  const refreshProfiles = useAppStore((s) => s.refreshProfiles);
  const showToast = useAppStore((s) => s.showToast);

  const [proxyId, setProxyId] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [filter, setFilter] = useState<"all" | "active" | "untested">("all");

  useEffect(() => {
    if (open && profile) setProxyId(profile.proxy_id || "");
  }, [open, profile]);

  const submit = async () => {
    if (!profile) return;
    setSubmitting(true);
    try {
      await api().bindProfileProxy({
        profile_id: profile.id,
        proxy_id: proxyId || null,
      });
      await refreshProfiles();
      showToast("success", proxyId ? "Proxy bound" : "Proxy unbound");
      onClose();
    } catch (e) {
      showToast("error", (e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const visibleProxies = proxies.filter((p) => {
    if (p.status === "dead") return false;
    if (filter === "active") return p.status === "active";
    if (filter === "untested") return p.status === "untested";
    return true;
  });

  return (
    <Modal
      open={open && profile !== null}
      onClose={onClose}
      title={profile ? `Bind proxy — ${profile.name}` : "Bind proxy"}
      footer={
        <>
          <button type="button" className="btn-ghost" onClick={onClose}>Cancel</button>
          <button type="button" className="btn-primary" onClick={submit} disabled={submitting}>
            {submitting ? "Saving..." : (proxyId ? "Bind" : "Unbind")}
          </button>
        </>
      }
    >
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <label className="text-xs text-surface-100/60">Filter:</label>
          <select
            className="input !w-auto !py-1 !text-xs"
            value={filter}
            onChange={(e) => setFilter(e.target.value as typeof filter)}
          >
            <option value="all">all (excl. dead)</option>
            <option value="active">active only</option>
            <option value="untested">untested only</option>
          </select>
        </div>

        <div>
          <label className="block text-xs text-surface-100/60 mb-1">Proxy</label>
          <select
            className="input"
            value={proxyId}
            onChange={(e) => setProxyId(e.target.value)}
            size={Math.min(10, visibleProxies.length + 1)}
          >
            <option value="">— unbind —</option>
            {visibleProxies.map((p) => (
              <option key={p.id} value={p.id}>
                [{p.status}] {p.label} — {p.provider} {p.observed_country || p.country || ""}
                {p.latency_ms != null ? ` — ${Math.round(p.latency_ms)}ms` : ""}
              </option>
            ))}
          </select>
          <p className="text-xs text-surface-100/40 mt-1">
            {visibleProxies.length} proxies shown. Dead proxies are hidden.
          </p>
        </div>

        {profile?.locale && (
          <div className="text-xs text-surface-100/60">
            Profile locale: <b>{profile.locale}</b>. Picking a proxy from a
            country that doesn't match this locale is a fingerprint
            inconsistency.
          </div>
        )}
      </div>
    </Modal>
  );
}
