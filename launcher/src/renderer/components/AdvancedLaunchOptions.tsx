// Collapsible "Options avancées" block shared by LaunchSessionModal and
// BatchLaunchModal.

import { useEffect } from "react";
import type { LaunchOptions } from "../../shared/types";
import { useAppStore } from "../store";

interface Props {
  value: LaunchOptions;
  onChange: (next: LaunchOptions) => void;
}

export function AdvancedLaunchOptions({ value, onChange }: Props) {
  const macros = useAppStore((s) => s.macros);
  const refreshMacros = useAppStore((s) => s.refreshMacros);

  useEffect(() => {
    refreshMacros();
  }, [refreshMacros]);

  const set = <K extends keyof LaunchOptions>(k: K, v: LaunchOptions[K]) =>
    onChange({ ...value, [k]: v });

  return (
    <details className="border border-surface-700 rounded bg-surface-900/40 mt-2">
      <summary className="cursor-pointer select-none px-3 py-2 text-sm font-medium">
        Options avancées
      </summary>
      <div className="px-3 pb-3 pt-1 space-y-2">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={!!value.warmup}
            onChange={(e) => set("warmup", e.target.checked)}
          />
          Préchauffage (visite d'abord des sites neutres)
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={!!value.persistent}
            onChange={(e) => set("persistent", e.target.checked)}
          />
          Session persistante (conserve cookies et stockage)
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={!!value.queue_monitor}
            onChange={(e) => set("queue_monitor", e.target.checked)}
          />
          Queue monitor (détecte les salles d'attente)
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={!!value.humanlike}
            onChange={(e) => set("humanlike", e.target.checked)}
          />
          Humanlike (souris + frappe réaliste)
        </label>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-surface-100/60 mb-1">
              Auto-refresh (secondes)
            </label>
            <input
              type="number"
              min={0}
              className="input"
              value={value.auto_refresh ?? 0}
              onChange={(e) => set("auto_refresh", Number(e.target.value) || 0)}
            />
            <div className="text-[10px] text-surface-100/40 mt-0.5">
              0 désactive
            </div>
          </div>
          <div>
            <label className="block text-xs text-surface-100/60 mb-1">
              Limite req/min
            </label>
            <input
              type="number"
              min={0}
              className="input"
              value={value.rate_limit ?? 0}
              onChange={(e) => set("rate_limit", Number(e.target.value) || 0)}
            />
            <div className="text-[10px] text-surface-100/40 mt-0.5">
              0 = illimité
            </div>
          </div>
        </div>
        <div>
          <label className="block text-xs text-surface-100/60 mb-1">
            Macro à exécuter (optionnel)
          </label>
          <select
            className="input"
            value={value.run_macro ?? ""}
            onChange={(e) => set("run_macro", e.target.value || undefined)}
          >
            <option value="">(aucune)</option>
            {macros.map((m) => (
              <option key={m.name} value={m.name}>{m.name}</option>
            ))}
          </select>
        </div>
      </div>
    </details>
  );
}
