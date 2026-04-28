import {
  LayoutDashboard, Users, Globe, Monitor, ListChecks, Wand2, Settings,
  type LucideIcon,
} from "lucide-react";
import { DashboardPage } from "./pages/DashboardPage";
import { MacrosPage } from "./pages/MacrosPage";
import { ProfilesPage } from "./pages/ProfilesPage";
import { ProxiesPage } from "./pages/ProxiesPage";
import { SessionsPage } from "./pages/SessionsPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TasksPage } from "./pages/TasksPage";
import { useAppStore, type AppState } from "./store";

type TabId = AppState["tab"];

interface TabDef {
  id: TabId;
  label: string;
  Icon: LucideIcon;
}

const TABS: TabDef[] = [
  { id: "dashboard", label: "Tableau de bord", Icon: LayoutDashboard },
  { id: "profiles",  label: "Profils",         Icon: Users },
  { id: "proxies",   label: "Proxies",         Icon: Globe },
  { id: "sessions",  label: "Sessions",        Icon: Monitor },
  { id: "tasks",     label: "Tâches",          Icon: ListChecks },
  { id: "macros",    label: "Macros",          Icon: Wand2 },
  { id: "settings",  label: "Paramètres",      Icon: Settings },
];

export function App() {
  const tab = useAppStore((s) => s.tab);
  const layout = useAppStore((s) => s.layout);
  const toast = useAppStore((s) => s.toast);
  const clearToast = useAppStore((s) => s.clearToast);

  return (
    <div className={`h-full ${layout === "sidebar" ? "flex" : "flex flex-col"}`}>
      {layout === "sidebar" ? <Sidebar /> : <TopBar />}

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

/** Compact horizontal nav across the top of the window. */
function TopBar() {
  const tab = useAppStore((s) => s.tab);
  const setTab = useAppStore((s) => s.setTab);
  return (
    <header className="flex items-center gap-1 px-3 py-2 border-b border-surface-700 bg-surface-800">
      <BrandMark />
      {TABS.map(({ id, label, Icon }) => (
        <button
          key={id}
          type="button"
          onClick={() => setTab(id)}
          className={`px-3 py-1 rounded text-sm transition-colors flex items-center gap-1.5 ${
            tab === id
              ? "bg-surface-700 text-white"
              : "text-surface-100/70 hover:bg-surface-700/50"
          }`}
        >
          <Icon size={14} strokeWidth={2} />
          {label}
        </button>
      ))}
      <div className="ml-auto flex items-center gap-2 text-xs text-surface-100/50">
        <kbd className="px-1.5 py-0.5 rounded border border-surface-700 bg-surface-900 font-mono">⌘</kbd>
        <kbd className="px-1.5 py-0.5 rounded border border-surface-700 bg-surface-900 font-mono">K</kbd>
      </div>
    </header>
  );
}

/** Vertical column on the left, classic dashboard layout. */
function Sidebar() {
  const tab = useAppStore((s) => s.tab);
  const setTab = useAppStore((s) => s.setTab);
  return (
    <aside className="w-56 shrink-0 flex flex-col border-r border-surface-700 bg-surface-800">
      <div className="px-4 py-4 border-b border-surface-700">
        <BrandMark />
      </div>
      <nav className="flex-1 overflow-y-auto p-2 space-y-0.5">
        {TABS.map(({ id, label, Icon }) => {
          const active = tab === id;
          return (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={`w-full text-left px-3 py-2 rounded-md text-sm flex items-center gap-2.5
                transition-colors ${
                active
                  ? "bg-accent-500/15 text-accent-500 border-l-2 border-accent-500"
                  : "text-surface-100/70 hover:bg-surface-700/40 hover:text-surface-100 border-l-2 border-transparent"
              }`}
            >
              <Icon size={16} strokeWidth={2} />
              {label}
            </button>
          );
        })}
      </nav>
      <div className="p-3 border-t border-surface-700 text-xs text-surface-100/50 flex items-center justify-between">
        <span>palette</span>
        <span className="flex items-center gap-1">
          <kbd className="px-1.5 py-0.5 rounded border border-surface-700 bg-surface-900 font-mono">⌘</kbd>
          <kbd className="px-1.5 py-0.5 rounded border border-surface-700 bg-surface-900 font-mono">K</kbd>
        </span>
      </div>
    </aside>
  );
}

/** The little glowing dot + brand wordmark used in both layouts. */
function BrandMark() {
  return (
    <div className="text-sm font-bold text-accent-500 flex items-center gap-1.5">
      <span className="inline-block w-2 h-2 rounded-full bg-accent-500 shadow-[0_0_8px] shadow-accent-500" />
      camoufox
    </div>
  );
}
