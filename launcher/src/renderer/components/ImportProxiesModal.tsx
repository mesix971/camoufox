import { useState } from "react";
import type { ImportResult } from "../../shared/types";
import { api } from "../api";
import { useAppStore } from "../store";
import { Modal } from "./Modal";

interface Props {
  open: boolean;
  onClose: () => void;
}

export function ImportProxiesModal({ open, onClose }: Props) {
  const refreshProxies = useAppStore((s) => s.refreshProxies);
  const showToast = useAppStore((s) => s.showToast);

  const [text, setText] = useState("");
  const [tag, setTag] = useState("");
  const [result, setResult] = useState<ImportResult | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const submit = async () => {
    if (!text.trim()) {
      showToast("error", "collez d'abord des lignes de proxy");
      return;
    }
    setSubmitting(true);
    try {
      const res = await api().importProxies({
        text,
        ...(tag ? { tag } : {}),
      }) as ImportResult;
      setResult(res);
      await refreshProxies();
      showToast(
        res.errors.length ? "info" : "success",
        `${res.saved} enregistrés, ${res.duplicates} doublons, ${res.errors.length} erreurs`,
      );
    } catch (e) {
      showToast("error", (e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const close = () => {
    setText("");
    setTag("");
    setResult(null);
    onClose();
  };

  return (
    <Modal
      open={open}
      onClose={close}
      title="Importer des proxies"
      width="max-w-2xl"
      footer={
        <>
          <button type="button" className="btn-ghost" onClick={close}>
            {result ? "Terminé" : "Annuler"}
          </button>
          <button type="button" className="btn-primary" onClick={submit} disabled={submitting}>
            {submitting ? "Importation..." : "Importer"}
          </button>
        </>
      }
    >
      <div className="space-y-3">
        <p className="text-xs text-surface-100/70">
          Collez un proxy par ligne. Formats supportés : URL (http://user:pass@host:port,
          socks5://...), à plat (host:port:user:pass), forme @ (user:pass@host:port),
          ou sans authentification (host:port). Les métadonnées iproyal / brightdata / smartproxy
          sont extraites automatiquement depuis la charge d'authentification.
        </p>
        <textarea
          className="input font-mono text-xs"
          rows={12}
          placeholder="# n'importe lequel :
http://u:p@198.51.100.1:8080
geo.iproyal.com:12321:user:pw_country-US_session-abc_lifetime-10m
host:port:user:pass"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <div>
          <label className="block text-xs text-surface-100/60 mb-1">Attacher un tag à tous (optionnel)</label>
          <input className="input" placeholder="ex. iproyal_us"
                 value={tag} onChange={(e) => setTag(e.target.value)} />
        </div>
        {result && (
          <div className="mt-2 p-3 bg-surface-900 border border-surface-700 rounded text-xs font-mono">
            <div>analysés : <b>{result.parsed}</b></div>
            <div>enregistrés : <b className="text-green-400">{result.saved}</b></div>
            <div>doublons : <b className="text-amber-400">{result.duplicates}</b></div>
            <div>erreurs : <b className="text-red-400">{result.errors.length}</b></div>
            {result.errors.length > 0 && (
              <ul className="mt-2 space-y-0.5 text-red-300/80 max-h-40 overflow-y-auto">
                {result.errors.slice(0, 15).map((e, i) => (
                  <li key={i}>ligne {e.line} : {e.error} — <code>{e.raw}</code></li>
                ))}
                {result.errors.length > 15 && <li>... ({result.errors.length - 15} de plus)</li>}
              </ul>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}
