import { type LucideIcon } from "lucide-react";

/**
 * Standard hero header used at the top of every page.
 *
 * Layout: a tall block with an iconographic mark on the left, a
 * two-line title/subtitle, an optional metric chip, and an actions
 * cluster on the right. Themes hook into `.page-header` for signature
 * decorations (dot grid, gradient blob, ASCII frame, etc.).
 */
interface Props {
  title: string;
  subtitle?: string;
  icon: LucideIcon;
  badge?: { label: string; tone?: "neutral" | "accent" | "success" | "warning" };
  actions?: React.ReactNode;
}

export function PageHeader({ title, subtitle, icon: Icon, badge, actions }: Props) {
  const toneClass = ((): string => {
    switch (badge?.tone) {
      case "accent":  return "bg-accent-500/15 text-accent-500 border-accent-500/30";
      case "success": return "bg-green-500/15 text-green-300 border-green-500/30";
      case "warning": return "bg-amber-500/15 text-amber-300 border-amber-500/30";
      default:        return "bg-surface-700 text-surface-100/70 border-surface-700";
    }
  })();

  return (
    <header className="page-header relative px-6 py-5 border-b border-surface-700 overflow-hidden">
      {/* Theme-specific decoration is layered behind via ::before/::after. */}
      <div className="relative flex items-center gap-4">
        <span className="page-header-icon inline-flex items-center justify-center w-11 h-11
                         rounded-lg bg-accent-500/10 text-accent-500 border border-accent-500/20
                         shadow-[0_0_24px] shadow-accent-500/10 shrink-0">
          <Icon size={22} strokeWidth={2} />
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="page-header-title text-2xl font-bold tracking-tight text-surface-100">
              {title}
            </h1>
            {badge && (
              <span className={`text-[11px] font-medium px-2 py-0.5 rounded-md border ${toneClass}`}>
                {badge.label}
              </span>
            )}
          </div>
          {subtitle && (
            <p className="page-header-subtitle text-sm text-surface-100/55 mt-0.5">
              {subtitle}
            </p>
          )}
        </div>
        {actions && (
          <div className="flex items-center gap-2 shrink-0">
            {actions}
          </div>
        )}
      </div>
    </header>
  );
}
