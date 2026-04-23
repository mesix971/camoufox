interface Props {
  status: string;
  children?: React.ReactNode;
}

const STATUS_LABELS: Record<string, string> = {
  running: "En cours",
  stopped: "Arrêtée",
  starting: "Démarrage",
  crashed: "Plantée",
  active: "actif",
  flagged: "signalé",
  dead: "mort",
  untested: "non testé",
  // Task statuses
  queued: "En file",
  success: "Réussie",
  failed: "Échouée",
  retrying: "Nouvelle tentative",
  cancelled: "Annulée",
};

export function StatusBadge({ status, children }: Props) {
  return (
    <span className={`badge badge-${status}`}>
      {children ?? STATUS_LABELS[status] ?? status}
    </span>
  );
}
