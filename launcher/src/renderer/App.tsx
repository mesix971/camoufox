import { DashboardPage } from "./pages/DashboardPage";
import { MacrosPage } from "./pages/MacrosPage";
import { ProfilesPage } from "./pages/ProfilesPage";
import { ProxiesPage } from "./pages/ProxiesPage";
import { SessionsPage } from "./pages/SessionsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TasksPage } from "./pages/TasksPage";
import { useAppStore } from "./store";

const TABS = [
  { id: "dashboard" as const, label: "Tableau de bord" },
  { id: "profiles" as const, label: "Profils" },
  { id: "proxies" as const, label: "Proxies" },
  { id: "sessions" as const, label: "Sessions" },
  { id: "tasks" as const, label: "Tâches" },
  { id: "macros" as const, label: "Macros" },
  { id: "settings" as const, label: "Paramètres" },
];

export function App() {
  const tab = useAppStore((s) => s.tab);
  const setTab = useAppStore((s) => s.setTab);
  const toast = useAppStore((s) => s.toast);
  const clearToast = useAppStore((s) => s.clearToast);

  return (
    <div className="h-full flex flex-col">
      <header className="flex items-center gap-1 px-3 py-2 border-b border-surface-700 bg-surface-800">
        <div className="px-2 py-1 text-sm font-bold text-accent-500 mr-3">camoufox</div>
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`px-3 py-1 rounded text-sm transition-colors ${
              tab === t.id
                ? "bg-surface-700 text-white"
                : "text-surface-100/70 hover:bg-surface-700/50"
            }`}
          >
            {t.label}
          </button>
        ))}
      </header>

      <main className="flex-1 overflow-hidden">
        {tab === "dashboard" && <DashboardPage />}
        {tab === "profiles" && <ProfilesPage />}
        {tab === "proxies" && <ProxiesPage />}
        {tab === "sessions" && <SessionsPage />}
        {tab === "tasks" && <TasksPage />}
        {tab === "macros" && <MacrosPage />}
        {tab === "settings" && <SettingsPage />}
      </main>

      {toast && (
        <div
          className={`fixed bottom-4 right-4 px-4 py-2 rounded shadow-lg border cursor-pointer ${
            toast.kind === "error"
              ? "bg-red-900/90 border-red-700 text-red-100"
              : toast.kind === "success"
              ? "bg-green-900/90 border-green-700 text-green-100"
              : "bg-surface-800 border-surface-700 text-surface-100"
          }`}
          onClick={clearToast}
        >
          {toast.text}
        </div>
      )}
    </div>
  );
}
