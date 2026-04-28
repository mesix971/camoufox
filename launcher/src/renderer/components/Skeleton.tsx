/**
 * Skeleton loaders.
 *
 * Plain animated placeholders that match the geometry of what's about
 * to render. Keeps the page from feeling empty during the first fetch
 * and avoids the classic "blink in" of late content.
 */

interface SkeletonProps {
  className?: string;
  width?: string | number;
  height?: string | number;
  rounded?: string;
}

export function Skeleton({
  className = "",
  width,
  height,
  rounded = "rounded-md",
}: SkeletonProps) {
  return (
    <span
      className={`skeleton inline-block bg-surface-700/60 ${rounded} ${className}`}
      style={{ width, height }}
      aria-busy="true"
    />
  );
}

/** Skeleton row that mimics a typical table row with avatar + 4 columns. */
export function SkeletonTableRow({ columns = 4, withAvatar = false }: {
  columns?: number;
  withAvatar?: boolean;
}) {
  return (
    <tr className="border-b border-surface-700/60">
      {withAvatar && (
        <td className="px-3 py-3">
          <div className="flex items-center gap-2.5">
            <Skeleton width={28} height={28} rounded="rounded-lg" />
            <Skeleton width={`${40 + Math.random() * 60}%`} height={12} />
          </div>
        </td>
      )}
      {Array.from({ length: columns }).map((_, i) => (
        <td key={i} className="px-3 py-3">
          <Skeleton width={`${30 + Math.random() * 60}%`} height={12} />
        </td>
      ))}
    </tr>
  );
}

/** N skeleton rows. */
export function SkeletonTable({ rows = 5, columns = 4, withAvatar = false }: {
  rows?: number;
  columns?: number;
  withAvatar?: boolean;
}) {
  return (
    <>
      {Array.from({ length: rows }).map((_, i) => (
        <SkeletonTableRow key={i} columns={columns} withAvatar={withAvatar} />
      ))}
    </>
  );
}
