// Compose a new queued task: picks a profile, a URL, and an optional delay + tags.
// Action payload stays simple — worker-side dispatch is out of scope for this modal.

import { useEffect, useState } from "react";
import { api } from "../api";
import { useAppStore } from "../store";
import { Modal } from "./Modal";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function NewTaskModal({ open, onClose }: Props) {
  const profiles = useAppStore((s) => s.profiles);
  const refreshProfiles = useAppStore((s) => s.refreshProfiles);
  const refreshTasks = useAppStore((s) => s.refreshTasks);
  const showToast = useAppStore((s) => s.showToast);

  const [profileId, setProfileId] = useState("");
  const [url, setUrl] = useState("");
  const [delay, setDelay] = useState<number>(0);
  const [tags, setTags] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setProfileId("");
      setUrl("");
      setDelay(0);
      setTags("");
      if (profiles.length === 0) refreshProfiles();
    }
  }, [open, profiles.length, refreshProfiles]);

  const submit = async () => {
    if (!profileId) {
      showToast("error", "choisir un profil");
      return;
    }
    setSubmitting(true);
    try {
      const action: Record<string, unknown> = {
        type: "launch-session",
        profile_id: profileId,
      };
      if (url) action.url = url;
      const args: Parameters<typeof window.api.enqueueTask>[0] = { action };
      if (delay && delay > 0) args.delay_seconds = Number(delay);
      const parsedTags = tags.split(",").map((t) => t.trim()).filter(Boolean);
      if (parsedTags.length) args.tags = parsedTags;
      await api().enqueueTask(args);
      await refreshTasks();
      showToast("success", "Tâche ajoutée à la file");
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
      title="Nouvelle tâche"
      footer={
        <>
          <button type="button" className="btn-ghost" onClick={onClose}>Annuler</button>
          <button type="button" className="btn-primary" onClick={submit} disabled={submitting}>
            {submitting ? "Ajout..." : "Ajouter"}
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
          <label className="block text-xs text-surface-100/60 mb-1">URL (optionnelle)</label>
          <input
            className="input"
            placeholder="https://example.com"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-xs text-surface-100/60 mb-1">
            Délai avant exécution (secondes)
          </label>
          <input
            type="number"
            min={0}
            className="input"
            value={delay}
            onChange={(e) => setDelay(Number(e.target.value) || 0)}
          />
        </div>
        <div>
          <label className="block text-xs text-surface-100/60 mb-1">
            Tags (séparés par des virgules)
          </label>
          <input
            className="input"
            placeholder="ex. night-run,fr"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
          />
        </div>
      </div>
    </Modal>
  );
}
