import { useEffect, useState } from "react";
import type { CreepJSScore, ProfileSummary } from "../../shared/types";
import { api } from "../api";
import { BindProxyModal } from "../components/BindProxyModal";
import { ImportProfileModal } from "../components/ImportProfileModal";
import { LaunchSessionModal } from "../components/LaunchSessionModal";
import { NewProfileModal } from "../components/NewProfileModal";
import { ProfileEditModal } from "../components/ProfileEditModal";
import { TagList } from "../components/TagPill";
import { useAppStore } from "../store";

export function ProfilesPage() {
  const {
    profiles, profilesLoading, profilesError, refreshProfiles,
    proxies, refreshProxies, showToast,
    creepjsScores, setCreepjsScore,
  } = useAppStore();
  const [showNew, setShowNew] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [launchFor, setLaunchFor] = useState<string | null>(null);
  const [bindFor, setBindFor] = useState<ProfileSummary | null>(null);
  const [editFor, setEditFor] = useState<ProfileSummary | null>(null);
  const [scoringIds, setScoringIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    refreshProfiles();
    refreshProxies();
  }, [refreshProfiles, refreshProxies]);

  const proxyLabel = (id: string | null): string => {
    if (!id) return "-";
    const p = proxies.find((x) => x.id === id);
    if (!p) return id;
    return `${p.label} [${p.status}]`;
  };

  const remove = async (id: string) => {
    if (!confirm(`Supprimer le profil ${id} ?`)) return;
    try {
      await api().deleteProfile(id);
      await refreshProfiles();
      showToast("success", "Profil supprimé");
    } catch (e) {
      showToast("error", (e as Error).message);
    }
  };

  const clone = async (p: ProfileSummary) => {
    if (!confirm(`Cloner le profil « ${p.name} » ?`)) return;
    try {
      await api().cloneProfile({ id: p.id });
      await refreshProfiles();
      showToast("success", "Profil cloné");
    } catch (e) {
      showToast("error", (e as Error).message);
    }
  };

  const scoreCreepjs = async (p: ProfileSummary) => {
    setScoringIds((prev) => {
      const next = new Set(prev);
      next.add(p.id);
      return next;
    });
    showToast("info", `CreepJS en cours pour « ${p.name} »...`);
    try {
      const res = await api().scoreProfileCreepjs({
        profile_id: p.id,
        headless: true,
        save_to_profile: true,
      }) as { score: CreepJSScore };
      setCreepjsScore(p.id, res.score);
      const verdict = res.score.passed ? "réussi" : "échoué";
      showToast(
        res.score.passed ? "success" : "error",
        `CreepJS ${verdict} : FP ${Math.round(res.score.fingerprint_score)} / Trust ${Math.round(res.score.trust_score)}`,
      );
    } catch (e) {
      showToast("error", (e as Error).message);
    } finally {
      setScoringIds((prev) => {
        const next = new Set(prev);
        next.delete(p.id);
        return next;
      });
    }
  };

  const exportOne = async (p: ProfileSummary) => {
    try {
      const res = await api().exportProfile({ id: p.id }) as {
        profile: Record<string, unknown>; export_version: number;
      };
      const blob = new Blob([JSON.stringify(res, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const safe = (p.name || p.id).replace(/[^a-zA-Z0-9_.-]+/g, "_");
      a.download = `${safe}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      showToast("success", "Profil exporté");
    } catch (e) {
      showToast("error", (e as Error).message);
    }
  };

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center justify-between px-4 py-3 border-b border-surface-700">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold">Profils</h2>
          <span className="text-xs text-surface-100/60">{profiles.length} total</span>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" className="btn-ghost" onClick={() => refreshProfiles()} disabled={profilesLoading}>
            {profilesLoading ? "..." : "Rafraîchir"}
          </button>
          <button type="button" className="btn-ghost" onClick={() => setShowImport(true)}>
            Importer
          </button>
          <button type="button" className="btn-primary" onClick={() => setShowNew(true)}>
            + Nouveau profil
          </button>
        </div>
      </div>

      {profilesError && (
        <div className="px-4 py-2 bg-red-900/60 text-red-200 text-sm border-b border-red-800">
          {profilesError}
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {profiles.length === 0 && !profilesLoading && (
          <div className="p-8 text-center text-surface-100/50">
            Aucun profil pour le moment. Cliquez sur <b>+ Nouveau profil</b> pour en générer un.
          </div>
        )}
        <table className="w-full text-sm">
          <thead className="text-xs uppercase text-surface-100/50 bg-surface-800/60 sticky top-0">
            <tr>
              <th className="text-left px-4 py-2 font-medium">Nom</th>
              <th className="text-left px-4 py-2 font-medium">Archétype</th>
              <th className="text-left px-4 py-2 font-medium">OS</th>
              <th className="text-left px-4 py-2 font-medium">Locale</th>
              <th className="text-left px-4 py-2 font-medium">Proxy</th>
              <th className="text-left px-4 py-2 font-medium">Tags</th>
              <th className="text-left px-4 py-2 font-medium">Dernière utilisation</th>
              <th className="text-right px-4 py-2 font-medium">Utilisations</th>
              <th className="text-right px-4 py-2 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {profiles.map((p) => (
              <tr key={p.id} className="table-row">
                <td className="px-4 py-2 font-medium">
                  <div className="flex items-center gap-2">
                    <span>{p.name}</span>
                    <CreepJSBadge score={creepjsScores[p.id]} />
                  </div>
                </td>
                <td className="px-4 py-2 font-mono text-xs text-surface-100/70">{p.archetype_id}</td>
                <td className="px-4 py-2">{p.os}</td>
                <td className="px-4 py-2">{p.locale}</td>
                <td className="px-4 py-2 text-xs text-surface-100/60">{proxyLabel(p.proxy_id)}</td>
                <td className="px-4 py-2"><TagList tags={p.tags} /></td>
                <td className="px-4 py-2 text-xs text-surface-100/60">
                  {p.last_used_at ? new Date(p.last_used_at).toLocaleString() : "-"}
                </td>
                <td className="px-4 py-2 text-right">{p.use_count}</td>
                <td className="px-4 py-2 text-right">
                  <div className="flex items-center justify-end gap-1 flex-wrap">
                    <button
                      type="button"
                      className="btn-ghost !py-1 !text-xs"
                      onClick={() => setEditFor(p)}
                    >
                      Éditer
                    </button>
                    <button
                      type="button"
                      className="btn-ghost !py-1 !text-xs"
                      onClick={() => clone(p)}
                    >
                      Cloner
                    </button>
                    <button
                      type="button"
                      className="btn-ghost !py-1 !text-xs"
                      onClick={() => exportOne(p)}
                    >
                      Exporter
                    </button>
                    <button
                      type="button"
                      className="btn-ghost !py-1 !text-xs"
                      onClick={() => scoreCreepjs(p)}
                      disabled={scoringIds.has(p.id)}
                    >
                      {scoringIds.has(p.id) ? "Test..." : "Tester CreepJS"}
                    </button>
                    <button
                      type="button"
                      className="btn-ghost !py-1 !text-xs"
                      onClick={() => setBindFor(p)}
                    >
                      Proxy
                    </button>
                    <button
                      type="button"
                      className="btn-primary !py-1 !text-xs"
                      onClick={() => setLaunchFor(p.id)}
                    >
                      Lancer
                    </button>
                    <button
                      type="button"
                      className="btn-danger !py-1 !text-xs"
                      onClick={() => remove(p.id)}
                    >
                      Supprimer
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <NewProfileModal open={showNew} onClose={() => setShowNew(false)} />
      <ImportProfileModal open={showImport} onClose={() => setShowImport(false)} />
      <LaunchSessionModal
        open={launchFor !== null}
        onClose={() => setLaunchFor(null)}
        initialProfileId={launchFor}
      />
      <BindProxyModal
        open={bindFor !== null}
        onClose={() => setBindFor(null)}
        profile={bindFor}
      />
      <ProfileEditModal
        open={editFor !== null}
        onClose={() => setEditFor(null)}
        profile={editFor}
      />
    </div>
  );
}

function CreepJSBadge({ score }: { score: CreepJSScore | undefined }) {
  if (!score) return null;
  const fp = Math.round(score.fingerprint_score);
  const trust = Math.round(score.trust_score);
  const cls = score.passed
    ? "bg-green-900/60 text-green-300"
    : "bg-red-900/60 text-red-300";
  const icon = score.passed ? "✓" : "✗";
  return (
    <span
      className={`badge ${cls}`}
      title={`FP ${fp} / Trust ${trust} — mensonges ${score.lies_count}, signaux bots ${score.bot_signals}`}
    >
      {icon} {fp}/{trust}
    </span>
  );
}
