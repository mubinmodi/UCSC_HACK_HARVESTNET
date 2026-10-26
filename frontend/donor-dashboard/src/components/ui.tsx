import { useEffect, useId, useRef, type ReactNode } from 'react';
import { Leaf, X } from 'lucide-react';
import type { Labelled } from '../types';
import { humanize } from '../format';

// Bundled illustrations from the original branch. Profiles without one get a leaf icon.
const PICTURES: Record<string, string> = {
  apples: 'apples',
  tomatoes: 'tomatoes',
  romaine: 'lettuce',
  lettuce: 'lettuce',
  carrots: 'carrots',
};

export function Photo({ produceId, small = false }: { produceId: string; small?: boolean }) {
  const picture = PICTURES[produceId];
  if (!picture)
    return (
      <span className={`produce produce-placeholder${small ? ' produce-small' : ''}`} aria-hidden="true">
        <Leaf />
      </span>
    );
  return (
    <img
      className={`produce${small ? ' produce-small' : ''}`}
      src={`${import.meta.env.BASE_URL}produce/${picture}.svg`}
      alt=""
      aria-hidden="true"
    />
  );
}

export function Badge({ text, tone, label }: { text: string; tone?: string; label?: string }) {
  return <span className={`badge ${tone ?? text.toLowerCase().replace(/[^a-z]+/g, '-')}`}>{label ?? humanize(text)}</span>;
}

/** Says where the data came from, from the response's own `mode` and `synthetic` fields. */
export function DataLabel({ data }: { data: Labelled | null | undefined }) {
  if (!data) return null;
  const mode = data.mode ?? 'unknown';
  const words =
    mode === 'example'
      ? 'Example response from the API skeleton. Every value is synthetic.'
      : mode === 'live'
        ? data.synthetic
          ? 'Live API, synthetic scenario data.'
          : 'Live API data.'
        : `${humanize(mode)} data${data.synthetic ? ', synthetic' : ''}.`;
  return (
    <p className={`data-label mode-${mode}`}>
      <span aria-hidden="true" /> {words}
    </p>
  );
}

export function ErrorNote({ message }: { message: string | null | undefined }) {
  if (!message) return null;
  return (
    <p className="error-note" role="alert">
      {message}
    </p>
  );
}

export function Section({ title, icon, children, aside }: { title: string; icon?: ReactNode; children: ReactNode; aside?: ReactNode }) {
  const id = useId();
  return (
    <section className="card-section" aria-labelledby={id}>
      <div className="section-heading">
        <h2 id={id}>
          {icon}
          {title}
        </h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

export function PageHeading({ icon, title, subtitle }: { icon: ReactNode; title: string; subtitle?: string }) {
  return (
    <div className="page-heading">
      <div className="heading-icon" aria-hidden="true">
        {icon}
      </div>
      <div>
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
    </div>
  );
}

/** A dialog with a focus trap and Escape to close (from the original branch). */
export function Modal({ title, onClose, busy, children }: { title: string; onClose: () => void; busy?: boolean; children: ReactNode }) {
  const ref = useRef<HTMLElement>(null);
  const titleId = useId();
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const first = ref.current?.querySelector<HTMLElement>('input, select, textarea, button:not([data-close])');
    first?.focus();
    function handleKey(event: KeyboardEvent) {
      if (event.key === 'Escape' && !busy) onClose();
      if (event.key !== 'Tab' || !ref.current) return;
      const elements = ref.current.querySelectorAll<HTMLElement>(
        'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled)',
      );
      if (!elements.length) return;
      const firstEl = elements[0];
      const lastEl = elements[elements.length - 1];
      if (event.shiftKey && document.activeElement === firstEl) {
        event.preventDefault();
        lastEl.focus();
      } else if (!event.shiftKey && document.activeElement === lastEl) {
        event.preventDefault();
        firstEl.focus();
      }
    }
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('keydown', handleKey);
      previous?.focus();
    };
  }, [busy, onClose]);
  return (
    <div className="modal-backdrop">
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby={titleId} ref={ref}>
        <div className="modal-heading">
          <h2 id={titleId}>{title}</h2>
          <button type="button" data-close aria-label="Close dialog" disabled={busy} onClick={onClose}>
            <X />
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}
