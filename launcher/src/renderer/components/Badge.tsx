interface Props {
  status: string;
  children?: React.ReactNode;
}

export function StatusBadge({ status, children }: Props) {
  return (
    <span className={`badge badge-${status}`}>
      {children ?? status}
    </span>
  );
}
