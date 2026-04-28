import {
  LayoutDashboard, Users, Globe, Monitor, ListChecks, Wand2, Settings,
} from "lucide-react";
import { DashboardPage } from "./pages/DashboardPage";
import { MacrosPage } from "./pages/MacrosPage";
import { ProfilesPage } from "./pages/ProfilesPage";
import { ProxiesPage } from "./pages/ProxiesPage";
import { SessionsPage } from "./pages/SessionsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TasksPage } from "./pages/TasksPage";
import { useAppStore } from "./store";

const TABS = [
  { id: "dashboard"  as const, label: "Tableau de bord", Icon: LayoutDashboard },
  { id: "profiles"   as const, label: "Profils",         Icon: Users },
  { id: "proxies"    as const, label: "Proxies",         Icon: Globe },
  { id: "sessions"   as const, label: "Sessions",        Icon: Monitor },
  { id: "tasks"      as const, label: "Tâches",          Icon: ListChecks },
  { id: "macros"     as const, label: "Macros",          Icon: Wand2 },
  { id: "settings"   as const, label: "Paramètres",      Icon: Settings },
];

export function App() {
  const tab = useAppStore((s) => s.tab);
  const setTab = useAppStore((s) => s.setTab);
  const toast = useAppStore((s) => s.toast);
  const clearToast = useAppStore((s) => s.clearToast);

  return (
    <div className="h-full flex flex-col">
      <header className="flex items-center gap-1 px-3 py-2 border-b border-surface-700 bg-surface-800">
        <div className="px-2 py-1 text-sm font-bold text-accent-500 mr-3 flex items-center gap-1.5">
          <span className="inline-block w-2 h-2 rounded-full bg-accent-500 shadow-[0_0_8px] shadow-accent-500" />
          camoufox
        </div>
        {TABS.map((t) => {
          const Icon = t.Icon;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`px-3 py-1 rounded text-sm transition-colors flex items-center gap-1.5 ${
                tab === t.id
                  ? "bg-surface-700 text-white"
                  : "text-surface-100/70 hover:bg-surface-700/50"
              }`}
            >
              <Icon size={14} strokeWidth={2} />
              {t.label}
            </button>
          );
        })}
        <div className="ml-auto flex items-center gap-2 text-xs text-surface-100/50">
          <kbd className="px-1.5 py-0.5 rounded border border-surface-700 bg-surface-900 font-mono">⌘</kbd>
          <kbd className="px-1.5 py-0.5 rounded border border-surface-700 bg-surface-900 font-mono">K</kbd>
        </div>
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
