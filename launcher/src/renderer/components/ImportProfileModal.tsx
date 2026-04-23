// Paste exported-profile JSON, validate, and import via import-profile.

import { useEffect, useState } from "react";
import { api } from "../api";
import { useAppStore } from "../store";
import { Modal } from "./Modal";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function ImportProfileModal({ open, onClose }: Props) {
  const refreshProfiles = useAppStore((s) => s.refreshProfiles);
  const showToast = useAppStore((s) => s.showToast);
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) setText("");
  }, [open]);

  const submit = async () => {
    let parsed: Record<string, unknown>;
    try {
      const raw = JSON.parse(text);
      // Accept either the full export object {profile, export_version} or just a profile dict.
      if (raw && typeof raw === "object" && "profile" in raw) {
        parsed = (raw as { profile: Record<string, unknown> }).profile;
      } else {
        parsed = raw as Record<string, unknown>;
      }
      if (!parsed || typeof parsed !== "object") {
        throw new Error("l'objet JSON doit être un profil");
      }
    } catch (e) {
      showToast("error", `JSON invalide : ${(e as Error).message}`);
      return;
    }
    setSubmitting(true);
    try {
      await api().importProfile({ profile: parsed, rename: true });
      await refreshProfiles();
      showToast("success", "Profil importé");
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
      title="Importer un profil"
      width="max-w-2xl"
      footer={
        <>
          <button type="button" className="btn-ghost" onClick={onClose}>Annuler</button>
          <button
            type="button"
            className="btn-primary"
            onClick={submit}
            disabled={submitting || !text.trim()}
          >
            {submitting ? "Import..." : "Importer"}
          </button>
        </>
      }
    >
      <div className="space-y-2">
        <p className="text-xs text-surface-100/60">
          Collez le JSON exporté depuis un autre launcher. Le profil reçoit un nouvel
          identifiant afin d'éviter toute collision.
        </p>
        <textarea
          className="input font-mono text-xs"
          rows={14}
          placeholder="Coller le JSON"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </div>
    </Modal>
  );
}
