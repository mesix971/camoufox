import { useEffect, useState } from "react";
import { api } from "../api";
import { useAppStore } from "../store";
import { Modal } from "./Modal";

interface Props {
  open: boolean;
  onClose: () => void;
  // If provided, runs that macro; otherwise acts as a recorder that saves a
  // freshly-recorded session under `recordName` (mode = "record").
  macroName?: string | null;
  mode?: "run" | "record";
}

export function RunMacroModal({ open, onClose, macroName, mode = "run" }: Props) {
  const profiles = useAppStore((s) => s.profiles);
  const refreshProfiles = useAppStore((s) => s.refreshProfiles);
  const refreshSessions = useAppStore((s) => s.refreshSessions);
  const refreshMacros = useAppStore((s) => s.refreshMacros);
  const showToast = useAppStore((s) => s.showToast);

  const [profileId, setProfileId] = useState("");
  const [url, setUrl] = useState("");
  const [recordName, setRecordName] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    refreshProfiles();
    setProfileId("");
    setUrl("");
    setRecordName("");
  }, [open, refreshProfiles]);

  const submit = async () => {
    if (!profileId) {
      showToast("error", "choisir un profil");
      return;
    }
    if (mode === "record" && !recordName.trim()) {
      showToast("error", "nom de macro requis");
      return;
    }
    setSubmitting(true);
    try {
      const args: Parameters<typeof window.api.launchSession>[0] = {
        profile_id: profileId,
      };
      if (url) args.url = url;
      if (mode === "run" && macroName) args.run_macro = macroName;
      if (mode === "record") args.record_macro = recordName.trim();
      await api().launchSession(args);
      await refreshSessions();
      if (mode === "record") await refreshMacros();
      showToast(
        "success",
        mode === "record" ? "Enregistrement démarré" : "Macro lancée",
      );
      onClose();
    } catch (e) {
      showToast("error", (e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const title = mode === "record"
    ? "Enregistrer une macro"
    : `Exécuter la macro — ${macroName ?? ""}`;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <button type="button" className="btn-ghost" onClick={onClose}>Annuler</button>
          <button type="button" className="btn-primary" onClick={submit} disabled={submitting}>
            {submitting ? "Démarrage..." : mode === "record" ? "Enregistrer" : "Exécuter"}
          </button>
        </>
      }
    >
      <div className="space-y-3">
        {mode === "record" && (
          <div>
            <label className="block text-xs text-surface-100/60 mb-1">
              Nom de la macro à enregistrer
            </label>
            <input
              className="input"
              placeholder="ex. login-flow"
              value={recordName}
              onChange={(e) => setRecordName(e.target.value)}
            />
          </div>
        )}
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
          <label className="block text-xs text-surface-100/60 mb-1">URL initiale (optionnelle)</label>
          <input
            className="input"
            placeholder="https://example.com"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        </div>
      </div>
    </Modal>
  );
}
