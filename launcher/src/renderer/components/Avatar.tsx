/**
 * Visual identity for a profile (or any string-keyed entity).
 *
 * Derives a stable color hue from the id, paints a gradient circle, and
 * overlays the initials of the name. This gives every row in the
 * profiles table a recognisable thumbnail without requiring the user
 * to upload anything — the hue is reproducible across reloads because
 * it's a pure function of the id.
 */
interface Props {
  id: string;
  name: string;
  size?: number;
  /** When true, draws a soft glow ring (used on selected/hovered rows). */
  active?: boolean;
}

export function Avatar({ id, name, size = 28, active = false }: Props) {
  const hue = hashHue(id);
  const initials = makeInitials(name);
  const fontSize = Math.max(9, Math.round(size * 0.4));
  return (
    <span
      className={`avatar inline-flex items-center justify-center shrink-0 select-none
                  font-semibold text-white ${active ? "avatar-active" : ""}`}
      style={{
        width: size,
        height: size,
        borderRadius: size * 0.3,
        background: `linear-gradient(135deg,
          hsl(${hue} 70% 55%) 0%,
          hsl(${(hue + 40) % 360} 70% 45%) 100%)`,
        fontSize,
        letterSpacing: "0.02em",
        boxShadow: active
          ? `0 0 0 2px hsl(${hue} 80% 60% / 0.5),
             0 4px 16px hsl(${hue} 70% 50% / 0.4)`
          : `inset 0 1px 0 rgb(255 255 255 / 0.15),
             0 1px 2px rgb(0 0 0 / 0.4)`,
      }}
      title={name}
    >
      {initials}
    </span>
  );
}

function hashHue(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h % 360;
}

function makeInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "??";
  if (parts.length === 1) {
    const p = parts[0];
    return (p.charAt(0) + (p.charAt(1) || "")).toUpperCase();
  }
  return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase();
}
