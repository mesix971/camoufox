import { useEffect, useState } from "react";
import type { Macro } from "../../shared/types";
import { api } from "../api";
import { MacroEditModal } from "../components/MacroEditModal";
import { RunMacroModal } from "../components/RunMacroModal";
import { useAppStore } from "../store";

export function MacrosPage() {
  const {
    macros, macrosLoading, macrosError, refreshMacros, showToast,
  } = useAppStore();

  const [editFor, setEditFor] = useState<Macro | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [runFor, setRunFor] = useState<string | null>(null);
  const [recordOpen, setRecordOpen] = useState(false);

  useEffect(() => {
    refreshMacros();
  }, [refreshMacros]);

  const openNew = () => {
    setEditFor(null);
    setEditorOpen(true);
  };

  const openEdit = async (m: Macro) => {
    try {
      const full = await api().showMacro({ name: m.name }) as Macro;
      setEditFor(full);
      setEditorOpen(true);
    } catch (e) {
      showToast("error", (e as Error).message);
    }
  };

  const remove = async (m: Macro) => {
    if (!confirm(`Supprimer la macro « ${m.name} » ?`)) return;
    try {
      await api().deleteMacro({ name: m.name });
      await refreshMacros();
      showToast("success", "Macro supprimée");
    } catch (e) {
      showToast("error", (e as Error).message);
    }
  };

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between px-4 py-3 border-b border-surface-700">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold">Macros</h2>
          <span className="text-xs text-surface-100/60">{macros.length} total</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="btn-ghost"
            onClick={() => refreshMacros()}
            disabled={macrosLoading}
          >
            {macrosLoading ? "..." : "Rafraîchir"}
          </button>
          <button type="button" className="btn-ghost" onClick={() => setRecordOpen(true)}>
            + Enregistrer
          </button>
          <button type="button" className="btn-primary" onClick={openNew}>
            + Nouvelle macro
          </button>
        </div>
      </div>

      {macrosError && (
        <div className="px-4 py-2 bg-red-900/60 text-red-200 text-sm border-b border-red-800">
          {macrosError}
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {macros.length === 0 && !macrosLoading && (
          <div className="p-8 text-center text-surface-100/50">
            Aucune macro enregistrée. Cliquez sur <b>+ Nouvelle macro</b> ou <b>+ Enregistrer</b>.
          </div>
        )}
        <table className="w-full text-sm">
          <thead className="text-xs uppercase text-surface-100/50 bg-surface-800/60 sticky top-0">
            <tr>
              <th className="text-left px-4 py-2 font-medium">Nom</th>
              <th className="text-right px-4 py-2 font-medium">Actions</th>
              <th className="text-left px-4 py-2 font-medium">Aperçu</th>
              <th className="text-right px-4 py-2 font-medium">Opérations</th>
            </tr>
          </thead>
          <tbody>
            {macros.map((m) => {
              const count = countActions(m);
              return (
                <tr key={m.name} className="table-row">
                  <td className="px-4 py-2 font-medium">{m.name}</td>
                  <td className="px-4 py-2 text-right font-mono text-xs">{count}</td>
                  <td className="px-4 py-2 text-xs text-surface-100/70">
                    {summarize(m)}
                  </td>
                  <td className="px-4 py-2 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        type="button"
                        className="btn-ghost !py-1 !text-xs"
                        onClick={() => openEdit(m)}
                      >
                        Éditer
                      </button>
                      <button
                        type="button"
                        className="btn-primary !py-1 !text-xs"
                        onClick={() => setRunFor(m.name)}
                      >
                        Exécuter
                      </button>
                      <button
                        type="button"
                        className="btn-danger !py-1 !text-xs"
                        onClick={() => remove(m)}
                      >
                        Supprimer
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <MacroEditModal
        open={editorOpen}
        onClose={() => setEditorOpen(false)}
        macro={editFor}
      />
      <RunMacroModal
        open={runFor !== null}
        onClose={() => setRunFor(null)}
        macroName={runFor}
        mode="run"
      />
      <RunMacroModal
        open={recordOpen}
        onClose={() => setRecordOpen(false)}
        mode="record"
      />
    </div>
  );
}

function countActions(m: Macro): number {
  if (typeof m.action_count === "number") return m.action_count;
  if (Array.isArray(m.actions)) return m.actions.length;
  return 0;
}

function summarize(m: Macro): string {
  const acts = Array.isArray(m.actions) ? m.actions : [];
  if (acts.length === 0) return "—";
  const types = acts.slice(0, 3).map((a) => {
    if (a && typeof a === "object" && "type" in a) {
      return String((a as { type: unknown }).type);
    }
    return "?";
  });
  const more = acts.length > 3 ? "…" : "";
  return types.join(", ") + more;
}
