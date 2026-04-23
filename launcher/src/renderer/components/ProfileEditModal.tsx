// Edit a subset of profile fields (the ones most useful to tweak manually).
// Submits a sparse `updates` dict via update-profile.

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

interface FullProfile {
  name?: string;
  tags?: string[];
  user_agent?: string;
  locale?: string;
  timezone?: string;
  screen_width?: number;
  screen_height?: number;
  cpu_cores?: number;
  [k: string]: unknown;
}

export function ProfileEditModal({ open, onClose, profile }: Props) {
  const refreshProfiles = useAppStore((s) => s.refreshProfiles);
  const showToast = useAppStore((s) => s.showToast);

  const [name, setName] = useState("");
  const [tags, setTags] = useState("");
  const [userAgent, setUserAgent] = useState("");
  const [locale, setLocale] = useState("");
  const [timezone, setTimezone] = useState("");
  const [screenW, setScreenW] = useState<number>(0);
  const [screenH, setScreenH] = useState<number>(0);
  const [cpu, setCpu] = useState<number>(0);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open || !profile) return;
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const res = await api().showProfile(profile.id) as { profile: FullProfile };
        if (cancelled) return;
        const p = res.profile;
        setName(String(p.name ?? ""));
        setTags(((p.tags as string[] | undefined) ?? []).join(", "));
        setUserAgent(String(p.user_agent ?? ""));
        setLocale(String(p.locale ?? ""));
        setTimezone(String(p.timezone ?? ""));
        setScreenW(Number(p.screen_width ?? 0));
        setScreenH(Number(p.screen_height ?? 0));
        setCpu(Number(p.cpu_cores ?? 0));
      } catch (e) {
        if (!cancelled) showToast("error", (e as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [open, profile, showToast]);

  const submit = async () => {
    if (!profile) return;
    setSubmitting(true);
    try {
      const updates: Record<string, unknown> = {
        name,
        tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
        user_agent: userAgent,
        locale,
        timezone,
        screen_width: Number(screenW) || 0,
        screen_height: Number(screenH) || 0,
        cpu_cores: Number(cpu) || 0,
      };
      await api().updateProfile({ id: profile.id, updates });
      await refreshProfiles();
      showToast("success", "Profil mis à jour");
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
      title={`Éditer le profil ${profile?.name ?? ""}`}
      footer={
        <>
          <button type="button" className="btn-ghost" onClick={onClose}>Annuler</button>
          <button
            type="button"
            className="btn-primary"
            onClick={submit}
            disabled={submitting || loading}
          >
            {submitting ? "Enregistrement..." : "Enregistrer"}
          </button>
        </>
      }
    >
      {loading ? (
        <div className="text-surface-100/50 text-sm">chargement...</div>
      ) : (
        <div className="space-y-3">
          <div>
            <label className="block text-xs text-surface-100/60 mb-1">Nom</label>
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs text-surface-100/60 mb-1">
              Tags (séparés par des virgules)
            </label>
            <input className="input" value={tags} onChange={(e) => setTags(e.target.value)} />
          </div>
          <div>
            <label className="block text-xs text-surface-100/60 mb-1">User-Agent</label>
            <input className="input" value={userAgent} onChange={(e) => setUserAgent(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-surface-100/60 mb-1">Locale</label>
              <input className="input" value={locale} onChange={(e) => setLocale(e.target.value)} />
            </div>
            <div>
              <label className="block text-xs text-surface-100/60 mb-1">Fuseau horaire</label>
              <input
                className="input"
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs text-surface-100/60 mb-1">Largeur écran</label>
              <input
                type="number"
                className="input"
                value={screenW}
                onChange={(e) => setScreenW(Number(e.target.value))}
              />
            </div>
            <div>
              <label className="block text-xs text-surface-100/60 mb-1">Hauteur écran</label>
              <input
                type="number"
                className="input"
                value={screenH}
                onChange={(e) => setScreenH(Number(e.target.value))}
              />
            </div>
            <div>
              <label className="block text-xs text-surface-100/60 mb-1">Cœurs CPU</label>
              <input
                type="number"
                className="input"
                value={cpu}
                onChange={(e) => setCpu(Number(e.target.value))}
              />
            </div>
          </div>
        </div>
      )}
    </Modal>
  );
}
