import { useEffect, useState } from "react";
import type { Macro } from "../../shared/types";
import { api } from "../api";
import { useAppStore } from "../store";
import { Modal } from "./Modal";

interface Props {
  open: boolean;
  onClose: () => void;
  macro: Macro | null;
}

// Edit or create a macro. If `macro` is null, the modal creates a new one;
// otherwise it edits the existing one (name becomes read-only since it is the
// identifier used by the bridge).
export function MacroEditModal({ open, onClose, macro }: Props) {
  const refreshMacros = useAppStore((s) => s.refreshMacros);
  const showToast = useAppStore((s) => s.showToast);

  const [name, setName] = useState("");
  const [actionsText, setActionsText] = useState("[]");
  const [metadataText, setMetadataText] = useState("{}");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    if (macro) {
      setName(macro.name);
      setActionsText(JSON.stringify(macro.actions ?? [], null, 2));
      setMetadataText(JSON.stringify(macro.metadata ?? {}, null, 2));
    } else {
      setName("");
      setActionsText("[]");
      setMetadataText("{}");
    }
  }, [open, macro]);

  const submit = async () => {
    if (!name.trim()) {
      showToast("error", "nom requis");
      return;
    }
    let parsedActions: unknown;
    let parsedMetadata: Record<string, unknown> | undefined;
    try {
      parsedActions = JSON.parse(actionsText);
      if (!Array.isArray(parsedActions)) throw new Error("actions doit être un tableau");
    } catch (e) {
      showToast("error", `JSON actions invalide : ${(e as Error).message}`);
      return;
    }
    try {
      const meta = metadataText.trim() ? JSON.parse(metadataText) : {};
      if (meta && typeof meta === "object" && !Array.isArray(meta)) {
        parsedMetadata = meta as Record<string, unknown>;
      } else {
        throw new Error("metadata doit être un objet");
      }
    } catch (e) {
      showToast("error", `JSON metadata invalide : ${(e as Error).message}`);
      return;
    }

    setSubmitting(true);
    try {
      await api().saveMacro({
        name: name.trim(),
        actions: parsedActions as unknown[],
        metadata: parsedMetadata,
      });
      await refreshMacros();
      showToast("success", "Macro enregistrée");
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
      title={macro ? `Éditer la macro — ${macro.name}` : "Nouvelle macro"}
      width="max-w-2xl"
      footer={
        <>
          <button type="button" className="btn-ghost" onClick={onClose}>Annuler</button>
          <button type="button" className="btn-primary" onClick={submit} disabled={submitting}>
            {submitting ? "Enregistrement..." : "Enregistrer"}
          </button>
        </>
      }
    >
      <div className="space-y-3">
        <div>
          <label className="block text-xs text-surface-100/60 mb-1">Nom</label>
          <input
            className="input"
            placeholder="ex. login-flow"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={!!macro}
          />
        </div>
        <div>
          <label className="block text-xs text-surface-100/60 mb-1">
            Actions (JSON — tableau)
          </label>
          <textarea
            className="input font-mono text-xs"
            rows={12}
            value={actionsText}
            onChange={(e) => setActionsText(e.target.value)}
          />
        </div>
        <div>
          <label className="block text-xs text-surface-100/60 mb-1">
            Métadonnées (JSON — objet, optionnel)
          </label>
          <textarea
            className="input font-mono text-xs"
            rows={4}
            value={metadataText}
            onChange={(e) => setMetadataText(e.target.value)}
          />
        </div>
      </div>
    </Modal>
  );
}
