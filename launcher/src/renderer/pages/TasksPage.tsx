import { useEffect, useMemo, useState } from "react";
import { ListChecks, RefreshCw, Plus } from "lucide-react";
import type { Task, TaskStatus } from "../../shared/types";
import { api } from "../api";
import { StatusBadge } from "../components/Badge";
import { NewTaskModal } from "../components/NewTaskModal";
import { PageHeader } from "../components/PageHeader";
import { TagList } from "../components/TagPill";
import { useAppStore } from "../store";

const STATUS_ORDER: TaskStatus[] = [
  "queued", "running", "retrying", "success", "failed", "cancelled",
];

const STATUS_FR: Record<TaskStatus, string> = {
  queued: "en file",
  running: "en cours",
  retrying: "nouvelle tentative",
  success: "réussies",
  failed: "échouées",
  cancelled: "annulées",
};

export function TasksPage() {
  const {
    tasks, tasksStats, tasksLoading, tasksError, refreshTasks,
    refreshProfiles, showToast,
  } = useAppStore();
  const [showNew, setShowNew] = useState(false);

  useEffect(() => {
    refreshTasks();
    refreshProfiles();
    const id = setInterval(refreshTasks, 3000);
    return () => clearInterval(id);
  }, [refreshTasks, refreshProfiles]);

  const remove = async (id: string) => {
    if (!confirm(`Supprimer la tâche ${id} ?`)) return;
    try {
      await api().deleteTask({ id });
      await refreshTasks();
      showToast("success", "Tâche supprimée");
    } catch (e) {
      showToast("error", (e as Error).message);
    }
  };

  const sortedTasks = useMemo(
    () => [...tasks].sort((a, b) => (b.created_at || "").localeCompare(a.created_at || "")),
    [tasks],
  );

  return (
    <div className="h-full flex flex-col">
<PageHeader
        title="Tâches"
        subtitle="Files d'attente planifiées et workers — backoff, retries, exécution."
        icon={ListChecks}
        badge={{ label: `${tasks.length} total`, tone: "neutral" }}
        actions={
          <>
            <button type="button" className="btn-ghost" onClick={() => refreshTasks()} disabled={tasksLoading}>
              <RefreshCw size={14} className={tasksLoading ? "animate-spin" : ""} />
              {tasksLoading ? "..." : "Rafraîchir"}
            </button>
            <button type="button" className="btn-primary" onClick={() => setShowNew(true)}>
              <Plus size={14} strokeWidth={2.5} />
              Nouvelle tâche
            </button>
          </>
        }
      />

      <div className="px-4 py-3 border-b border-surface-700 flex flex-wrap items-center gap-2">
        {STATUS_ORDER.map((s) => (
          <div
            key={s}
            className="px-3 py-1 rounded bg-surface-800 border border-surface-700 text-xs flex items-center gap-2"
          >
            <StatusBadge status={s} />
            <span className="font-mono">{tasksStats[s] ?? 0}</span>
            <span className="text-surface-100/50">{STATUS_FR[s]}</span>
          </div>
        ))}
      </div>

      {tasksError && (
        <div className="px-4 py-2 bg-red-900/60 text-red-200 text-sm border-b border-red-800">
          {tasksError}
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {sortedTasks.length === 0 && !tasksLoading && (
          <div className="p-8 text-center text-surface-100/50">
            Aucune tâche en file. Cliquez sur <b>+ Nouvelle tâche</b> pour en ajouter une.
          </div>
        )}
        <table className="w-full text-sm">
          <thead className="text-xs uppercase text-surface-100/50 bg-surface-800/60 sticky top-0">
            <tr>
              <th className="text-left px-4 py-2 font-medium">ID</th>
              <th className="text-left px-4 py-2 font-medium">Statut</th>
              <th className="text-left px-4 py-2 font-medium">Action</th>
              <th className="text-left px-4 py-2 font-medium">Programmée</th>
              <th className="text-right px-4 py-2 font-medium">Tentatives</th>
              <th className="text-left px-4 py-2 font-medium">Tags</th>
              <th className="text-left px-4 py-2 font-medium">Erreur</th>
              <th className="text-right px-4 py-2 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {sortedTasks.map((t) => (
              <TaskRow key={t.id} task={t} onDelete={remove} />
            ))}
          </tbody>
        </table>
      </div>

      <NewTaskModal open={showNew} onClose={() => setShowNew(false)} />
    </div>
  );
}

function TaskRow({ task, onDelete }: { task: Task; onDelete: (id: string) => void }) {
  const actionAbbr = abbreviateAction(task.action);
  return (
    <tr className="table-row">
      <td className="px-4 py-2 font-mono text-xs">{task.id}</td>
      <td className="px-4 py-2"><StatusBadge status={task.status} /></td>
      <td
        className="px-4 py-2 text-xs font-mono truncate max-w-xs"
        title={JSON.stringify(task.action, null, 2)}
      >
        {actionAbbr}
      </td>
      <td className="px-4 py-2 text-xs text-surface-100/60">
        {task.scheduled_at ? new Date(task.scheduled_at).toLocaleString() : "-"}
      </td>
      <td className="px-4 py-2 text-right font-mono text-xs">{task.attempts}</td>
      <td className="px-4 py-2"><TagList tags={task.tags} /></td>
      <td
        className="px-4 py-2 text-xs text-red-300/80 truncate max-w-xs"
        title={task.error ?? ""}
      >
        {task.error || "-"}
      </td>
      <td className="px-4 py-2 text-right">
        <button
          type="button"
          className="btn-danger !py-1 !text-xs"
          onClick={() => onDelete(task.id)}
        >
          Supprimer
        </button>
      </td>
    </tr>
  );
}

function abbreviateAction(action: Record<string, unknown>): string {
  const type = action.type ? String(action.type) : "?";
  const url = action.url ? String(action.url) : "";
  const pid = action.profile_id ? String(action.profile_id).slice(0, 8) : "";
  const parts = [type];
  if (pid) parts.push(pid);
  if (url) parts.push(url.length > 40 ? `${url.slice(0, 40)}...` : url);
  return parts.join(" ");
}
