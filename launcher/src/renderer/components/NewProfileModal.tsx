import { useEffect, useState } from "react";
import { api } from "../api";
import { useAppStore } from "../store";
import { Modal } from "./Modal";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function NewProfileModal({ open, onClose }: Props) {
  const archetypes = useAppStore((s) => s.archetypes);
  const loadArchetypes = useAppStore((s) => s.loadArchetypes);
  const refreshProfiles = useAppStore((s) => s.refreshProfiles);
  const showToast = useAppStore((s) => s.showToast);

  const [archetypeId, setArchetypeId] = useState<string>("");
  const [os, setOs] = useState<string>("");
  const [locale, setLocale] = useState<string>("");
  const [name, setName] = useState<string>("");
  const [tags, setTags] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => { if (open) loadArchetypes(); }, [open, loadArchetypes]);

  const submit = async () => {
    setSubmitting(true);
    try {
      const args: Parameters<typeof window.api.newProfile>[0] = {};
      if (archetypeId) args.archetype = archetypeId;
      else if (os) args.os = os;
      if (locale) args.locale = locale;
      if (name) args.name = name;
      if (tags) args.tags = tags.split(",").map((t) => t.trim()).filter(Boolean);
      await api().newProfile(args);
      await refreshProfiles();
      showToast("success", "Profil créé");
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
      title="Nouveau profil"
      footer={
        <>
          <button type="button" className="btn-ghost" onClick={onClose}>Annuler</button>
          <button type="button" className="btn-primary" onClick={submit} disabled={submitting}>
            {submitting ? "Génération..." : "Générer"}
          </button>
        </>
      }
    >
      <div className="space-y-3">
        <div>
          <label className="block text-xs text-surface-100/60 mb-1">Archétype</label>
          <select className="input" value={archetypeId} onChange={(e) => setArchetypeId(e.target.value)}>
            <option value="">(aucun — filtrer par OS ci-dessous)</option>
            {archetypes.map((a) => (
              <option key={a.id} value={a.id}>{a.id}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs text-surface-100/60 mb-1">OS (uniquement si aucun archétype)</label>
          <select className="input" value={os} onChange={(e) => setOs(e.target.value)} disabled={!!archetypeId}>
            <option value="">(aléatoire, pondéré)</option>
            <option value="windows">windows</option>
            <option value="macos">macos</option>
            <option value="linux">linux</option>
          </select>
        </div>
        <div>
          <label className="block text-xs text-surface-100/60 mb-1">Locale</label>
          <input className="input" placeholder="ex. fr-FR (laisser vide pour un aléatoire pondéré)"
                 value={locale} onChange={(e) => setLocale(e.target.value)} />
        </div>
        <div>
          <label className="block text-xs text-surface-100/60 mb-1">Nom (optionnel)</label>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <label className="block text-xs text-surface-100/60 mb-1">Tags (séparés par des virgules)</label>
          <input className="input" placeholder="ex. adonis,btc,eu"
                 value={tags} onChange={(e) => setTags(e.target.value)} />
        </div>
      </div>
    </Modal>
  );
}
