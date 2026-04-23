// Colored pill used to render profile/task tags. Color is deterministic from
// the tag string so the same tag always renders identically.

const TAG_COLORS = [
  "bg-rose-600",
  "bg-amber-500",
  "bg-emerald-600",
  "bg-sky-600",
  "bg-violet-600",
  "bg-pink-600",
  "bg-teal-600",
  "bg-orange-600",
];

export function tagColor(tag: string): string {
  let h = 0;
  for (const c of tag) h = (h * 31 + c.charCodeAt(0)) & 0xffffffff;
  return TAG_COLORS[Math.abs(h) % TAG_COLORS.length];
}

interface Props {
  tag: string;
}

export function TagPill({ tag }: Props) {
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs ${tagColor(tag)} text-white`}>
      {tag}
    </span>
  );
}

export function TagList({ tags }: { tags: string[] }) {
  if (!tags || tags.length === 0) {
    return <span className="text-surface-100/40">-</span>;
  }
  return (
    <div className="flex flex-wrap gap-1">
      {tags.map((t) => (
        <TagPill key={t} tag={t} />
      ))}
    </div>
  );
}
