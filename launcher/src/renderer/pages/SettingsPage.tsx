import { useEffect, useState } from "react";
import { PanelTop, PanelLeft } from "lucide-react";
import type { RatelimitStats } from "../../shared/types";
import { api } from "../api";
import { useAppStore } from "../store";
import { ThemePicker } from "../components/ThemePicker";
import type { LayoutId } from "../themes";

function LayoutPicker() {
  const current = useAppStore((s) => s.layout);
  const setLayout = useAppStore((s) => s.setLayout);
  const opts: { id: LayoutId; label: string; Icon: typeof PanelTop; hint: string }[] = [
    { id: "topbar",  label: "Barre supérieure", Icon: PanelTop,  hint: "Dense, classique" },
    { id: "sidebar", label: "Barre latérale",   Icon: PanelLeft, hint: "Plus de place pour les pages denses" },
  ];
  return (
    <div className="grid grid-cols-2 gap-3">
      {opts.map(({ id, label, Icon, hint }) => {
        const active = id === current;
        return (
          <button
            key={id}
            type="button"
            onClick={() => setLayout(id)}
            className={`text-left rounded-lg border p-3 transition-all hover:scale-[1.01] ${
              active
                ? "border-accent-500 ring-2 ring-accent-500/30 bg-surface-800"
                : "border-surface-700 bg-surface-800/50 hover:bg-surface-800"
            }`}
          >
            <div className="flex items-center gap-2 mb-1.5">
              <Icon size={16} className="text-accent-500" />
              <span className="font-medium text-surface-100">{label}</span>
              {active && (
                <span className="text-[10px] uppercase tracking-wide text-accent-500 ml-auto">
                  actif
                </span>
              )}
            </div>
            <div className="text-xs text-surface-100/60">{hint}</div>
          </button>
        );
      })}
    </div>
  );
}

function maskWebhook(url: string): string {
  // Discord webhooks look like https://discord.com/api/webhooks/<id>/<token>.
  // Preserve the id but hide the token to avoid shoulder-surfing exposure.
  const m = url.match(/^(https?:\/\/[^/]+\/api\/webhooks\/\d+\/)([^/?]+)(.*)$/i);
  if (!m) return url;
  const token = m[2];
  const masked = token.length > 6
    ? `${token.slice(0, 3)}...${token.slice(-3)}`
    : "***";
  return `${m[1]}${masked}${m[3]}`;
}

export function SettingsPage() {
  const showToast = useAppStore((s) => s.showToast);

  // Webhook state
  const [webhookUrl, setWebhookUrl] = useState("");
  const [savedWebhook, setSavedWebhook] = useState<string | null>(null);
  const [webhookBusy, setWebhookBusy] = useState(false);

  // Ratelimit state
  const [stats, setStats] = useState<RatelimitStats>({});
  const [rlHost, setRlHost] = useState("");
  const [rlMax, setRlMax] = useState<number>(60);
  const [rlBusy, setRlBusy] = useState(false);

  const loadWebhook = async () => {
    try {
      const res = await api().getWebhook() as { url: string | null };
      setSavedWebhook(res.url || null);
      setWebhookUrl(res.url || "");
    } catch (e) {
      showToast("error", (e as Error).message);
    }
  };

  const loadStats = async () => {
    try {
      const res = await api().ratelimitStats() as { hosts: RatelimitStats };
      setStats(res.hosts || {});
    } catch (e) {
      showToast("error", (e as Error).message);
    }
  };

  useEffect(() => {
    loadWebhook();
    loadStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const saveWebhook = async () => {
    if (!webhookUrl.trim()) {
      showToast("error", "URL requise");
      return;
    }
    setWebhookBusy(true);
    try {
      await api().setWebhook({ url: webhookUrl.trim() });
      await loadWebhook();
      showToast("success", "Webhook enregistré");
    } catch (e) {
      showToast("error", (e as Error).message);
    } finally {
      setWebhookBusy(false);
    }
  };

  const testWebhook = async () => {
    setWebhookBusy(true);
    try {
      const res = await api().testWebhook({
        content: "Camoufox webhook test — it works.",
      }) as { delivered: boolean };
      if (res.delivered) {
        showToast("success", "Message de test envoyé");
      } else {
        showToast("error", "Échec de livraison du test");
      }
    } catch (e) {
      showToast("error", (e as Error).message);
    } finally {
      setWebhookBusy(false);
    }
  };

  const saveRatelimit = async () => {
    if (!rlHost.trim()) {
      showToast("error", "hôte requis");
      return;
    }
    if (!Number.isFinite(rlMax) || rlMax < 0) {
      showToast("error", "limite invalide");
      return;
    }
    setRlBusy(true);
    try {
      await api().ratelimitSet({
        host: rlHost.trim(),
        max_per_minute: Number(rlMax) || 0,
      });
      await loadStats();
      setRlHost("");
      showToast("success", "Limite enregistrée");
    } catch (e) {
      showToast("error", (e as Error).message);
    } finally {
      setRlBusy(false);
    }
  };

  const hostRows = Object.entries(stats).sort((a, b) => a[0].localeCompare(b[0]));

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6 max-w-3xl">
      <section className="p-4 rounded-lg bg-surface-800 border border-surface-700 space-y-3">
        <div className="text-xs text-surface-100/60 uppercase tracking-wide">
          Apparence
        </div>
        <p className="text-xs text-surface-100/60">
          Choisissez le thème visuel de l'application. Le changement est immédiat
          et mémorisé pour vos prochaines sessions.
        </p>
        <ThemePicker />

        <div className="pt-2">
          <div className="text-xs text-surface-100/60 mb-2">Disposition</div>
          <LayoutPicker />
        </div>
      </section>

      <section className="p-4 rounded-lg bg-surface-800 border border-surface-700 space-y-3">
        <div className="text-xs text-surface-100/60 uppercase tracking-wide">
          Webhook Discord
        </div>
        <p className="text-xs text-surface-100/60">
          Reçoit des notifications sur les échecs de session, retries et événements critiques.
        </p>
        <div>
          <label className="block text-xs text-surface-100/60 mb-1">URL du webhook</label>
          <input
            className="input"
            placeholder="https://discord.com/api/webhooks/..."
            value={webhookUrl}
            onChange={(e) => setWebhookUrl(e.target.value)}
          />
        </div>
        {savedWebhook && (
          <div className="text-xs text-surface-100/50 font-mono">
            Configuré actuellement : {maskWebhook(savedWebhook)}
          </div>
        )}
        <div className="flex gap-2">
          <button
            type="button"
            className="btn-primary"
            onClick={saveWebhook}
            disabled={webhookBusy}
          >
            Enregistrer
          </button>
          <button
            type="button"
            className="btn-ghost"
            onClick={testWebhook}
            disabled={webhookBusy || !savedWebhook}
          >
            Tester
          </button>
        </div>
      </section>

      <section className="p-4 rounded-lg bg-surface-800 border border-surface-700 space-y-3">
        <div className="text-xs text-surface-100/60 uppercase tracking-wide">
          Limites de requêtes par hôte
        </div>
        <p className="text-xs text-surface-100/60">
          Plafonne le nombre de requêtes/minute émises vers un hôte pour éviter d'être
          repéré par les protections anti-bot.
        </p>

        <div className="border border-surface-700 rounded">
          <table className="w-full text-xs">
            <thead className="text-surface-100/50 bg-surface-900/50">
              <tr>
                <th className="text-left px-3 py-2 font-medium">Hôte</th>
                <th className="text-right px-3 py-2 font-medium">Req. dernière minute</th>
                <th className="text-right px-3 py-2 font-medium">Limite / min</th>
              </tr>
            </thead>
            <tbody>
              {hostRows.length === 0 ? (
                <tr>
                  <td colSpan={3} className="px-3 py-3 text-center text-surface-100/40">
                    Aucune limite configurée.
                  </td>
                </tr>
              ) : hostRows.map(([host, s]) => (
                <tr key={host} className="border-t border-surface-700/60">
                  <td className="px-3 py-2 font-mono">{host}</td>
                  <td className="px-3 py-2 text-right font-mono">{s.events_last_minute}</td>
                  <td className="px-3 py-2 text-right font-mono">
                    {s.max_per_minute > 0 ? s.max_per_minute : "∞"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="grid grid-cols-[1fr_auto_auto] gap-2 items-end">
          <div>
            <label className="block text-xs text-surface-100/60 mb-1">Hôte</label>
            <input
              className="input"
              placeholder="ex. api.example.com"
              value={rlHost}
              onChange={(e) => setRlHost(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs text-surface-100/60 mb-1">Max / min</label>
            <input
              type="number"
              min={0}
              className="input"
              value={rlMax}
              onChange={(e) => setRlMax(Number(e.target.value) || 0)}
            />
          </div>
          <button
            type="button"
            className="btn-primary"
            onClick={saveRatelimit}
            disabled={rlBusy}
          >
            Ajouter / Mettre à jour
          </button>
        </div>
      </section>
    </div>
  );
}
