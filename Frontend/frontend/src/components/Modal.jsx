import { useEffect, useRef } from 'react';
import { X } from 'lucide-react';

/** Accessible modal: overlay click + Escape to close, focus moved into dialog. */
export default function Modal({ open, onClose, title, children, footer }) {
  const panelRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') onClose?.();
    };
    document.addEventListener('keydown', onKey);
    panelRef.current?.focus();
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className="relative z-10 w-full max-w-lg rounded-lg border border-white/10 bg-night-900 shadow-2xl outline-none"
      >
        <div className="flex items-center justify-between border-b border-white/10 px-5 py-3">
          <h2 className="text-sm font-semibold text-slate-100">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
            className="rounded p-1 text-slate-400 transition hover:bg-white/5 hover:text-slate-200"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        <div className="px-5 py-4 text-sm text-slate-300">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-white/10 px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}
