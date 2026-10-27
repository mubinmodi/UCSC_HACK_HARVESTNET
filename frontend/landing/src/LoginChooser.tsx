import { useEffect, useRef } from 'react';
import { ArrowRight, Building2, Home, BarChart3, X } from 'lucide-react';
import type { Strings } from './i18n';

const icons = [Home, Building2, BarChart3];

/** A small modal: HarvestNet has no accounts, so "Log in" just points each kind of visitor to the right place. */
export function LoginChooser({ t, onClose }: { t: Strings; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    const first = ref.current?.querySelector<HTMLElement>('a, button');
    first?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== 'Tab' || !ref.current) return;
      const focusable = Array.from(ref.current.querySelectorAll<HTMLElement>('a[href], button:not([disabled])'));
      if (focusable.length === 0) return;
      const firstEl = focusable[0];
      const lastEl = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === firstEl) {
        event.preventDefault();
        lastEl.focus();
      } else if (!event.shiftKey && document.activeElement === lastEl) {
        event.preventDefault();
        firstEl.focus();
      }
    };
    document.addEventListener('keydown', onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = overflow;
      opener?.focus?.();
    };
  }, [onClose]);

  return (
    <div className="chooser-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
      <div className="chooser hn-card" role="dialog" aria-modal="true" aria-labelledby="chooser-title" ref={ref}>
        <div className="chooser-head">
          <h2 id="chooser-title">{t.loginTitle}</h2>
          <button type="button" className="chooser-close" aria-label={t.loginClose} onClick={onClose}>
            <X aria-hidden="true" />
          </button>
        </div>
        <p className="chooser-lead">{t.loginLead}</p>
        <ul className="chooser-list">
          {t.loginOptions.map((option, index) => {
            const Icon = icons[index] ?? Home;
            return (
              <li key={option.href}>
                <a className="chooser-option" href={option.href}>
                  <span className="chooser-icon" aria-hidden="true"><Icon /></span>
                  <span className="chooser-text">
                    <strong>{option.title}</strong>
                    <span>{option.body}</span>
                  </span>
                  <ArrowRight aria-hidden="true" className="chooser-arrow" />
                </a>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
