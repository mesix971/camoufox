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
      showToast("error", "paste some proxy lines first");
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
        `${res.saved} saved, ${res.duplicates} duplicates, ${res.errors.length} errors`,
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
      title="Import proxies"
      width="max-w-2xl"
      footer={
        <>
          <button type="button" className="btn-ghost" onClick={close}>
            {result ? "Done" : "Cancel"}
          </button>
          <button type="button" className="btn-primary" onClick={submit} disabled={submitting}>
            {submitting ? "Importing..." : "Import"}
          </button>
        </>
      }
    >
      <div className="space-y-3">
        <p className="text-xs text-surface-100/70">
          Paste one proxy per line. Supported formats: URL (http://user:pass@host:port,
          socks5://...), flat (host:port:user:pass), @-form (user:pass@host:port),
          or no auth (host:port). iproyal / brightdata / smartproxy metadata is
          auto-extracted from the auth payload.
        </p>
        <textarea
          className="input font-mono text-xs"
          rows={12}
          placeholder="# any of:
http://u:p@198.51.100.1:8080
geo.iproyal.com:12321:user:pw_country-US_session-abc_lifetime-10m
host:port:user:pass"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <div>
          <label className="block text-xs text-surface-100/60 mb-1">Attach tag to all (optional)</label>
          <input className="input" placeholder="e.g. iproyal_us"
                 value={tag} onChange={(e) => setTag(e.target.value)} />
        </div>
        {result && (
          <div className="mt-2 p-3 bg-surface-900 border border-surface-700 rounded text-xs font-mono">
            <div>parsed: <b>{result.parsed}</b></div>
            <div>saved: <b className="text-green-400">{result.saved}</b></div>
            <div>duplicates: <b className="text-amber-400">{result.duplicates}</b></div>
            <div>errors: <b className="text-red-400">{result.errors.length}</b></div>
            {result.errors.length > 0 && (
              <ul className="mt-2 space-y-0.5 text-red-300/80 max-h-40 overflow-y-auto">
                {result.errors.slice(0, 15).map((e, i) => (
                  <li key={i}>line {e.line}: {e.error} — <code>{e.raw}</code></li>
                ))}
                {result.errors.length > 15 && <li>... ({result.errors.length - 15} more)</li>}
              </ul>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}
