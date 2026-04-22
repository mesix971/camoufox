import { useEffect } from "react";

interface Props {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
  width?: string;
}

export function Modal({ open, title, onClose, children, footer, width = "max-w-xl" }: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
      onClick={onClose}
    >
      <div
        className={`bg-surface-800 border border-surface-700 rounded-lg shadow-xl w-full ${width} max-h-[85vh] flex flex-col`}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="px-4 py-3 border-b border-surface-700 flex items-center justify-between">
          <h2 className="font-semibold">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-surface-100/60 hover:text-surface-100 text-lg leading-none"
          >
            ×
          </button>
        </header>
        <div className="px-4 py-3 overflow-y-auto flex-1">{children}</div>
        {footer && (
          <footer className="px-4 py-3 border-t border-surface-700 flex items-center justify-end gap-2">
            {footer}
          </footer>
        )}
      </div>
    </div>
  );
}
