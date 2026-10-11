import type { ReactNode } from 'react';
import { AlertTriangle, FlaskConical, RotateCcw } from 'lucide-react';
import { ApiError } from './api';
import type { Strings } from './i18n';

/** Plain-words message for a failed API call. */
export function errorText(err: unknown, t: Strings): string {
  if (!(err instanceof ApiError)) return t.errorOther;
  if (err.kind === 'network') return t.errorNetwork;
  if (err.kind === 'timeout') return t.errorTimeout;
  if (err.kind === 'bad_response') return t.errorOther;
  if (err.status === 503) return t.errorBusy;
  if (err.status === 404) return t.errorNotFound;
  if (err.status === 409) return t.errorConflict;
  if (err.status === 400) return t.errorBadInput;
  return t.errorOther;
}

export function ErrorBox({ error, t, onRetry }: { error: unknown; t: Strings; onRetry?: () => void }) {
  const detail = error instanceof ApiError && error.kind === 'http' && error.status === 400 ? error.message : null;
  return (
    <div className="error" role="alert">
      <p>
        <AlertTriangle size={20} aria-hidden="true" />
        <span>{errorText(error, t)}</span>
      </p>
      {detail && <p className="error-detail">{detail}</p>}
      {onRetry && (
        <button type="button" className="secondary small" onClick={onRetry}>
          <RotateCcw size={18} aria-hidden="true" />
          {t.tryAgain}
        </button>
      )}
    </div>
  );
}

/** Shown whenever the API's reply is example or synthetic data (the skeleton always is). */
export function ExampleNotice({ t, children }: { t: Strings; children?: ReactNode }) {
  return (
    <div className="example-notice" role="note">
      <FlaskConical size={20} aria-hidden="true" />
      <div>
        <strong>{t.exampleTitle}.</strong> {children ?? t.exampleBody}
      </div>
    </div>
  );
}

export function Loading({ text }: { text: string }) {
  return (
    <p className="loading" role="status">
      <span className="spinner" aria-hidden="true" />
      {text}
    </p>
  );
}

export interface Option<V extends string> {
  value: V;
  label: string;
}

/** A radio group drawn as large tap targets. Native radios keep keyboard and screen readers working. */
export function ChoiceGroup<V extends string>(props: {
  name: string;
  legend: string;
  options: Option<V>[];
  value: V | null;
  onChange: (value: V) => void;
  hint?: string;
  error?: string | null;
  stacked?: boolean;
  lang?: (value: V) => string | undefined;
}) {
  const { name, legend, options, value, onChange, hint, error, stacked, lang } = props;
  const hintId = hint ? `${name}-hint` : undefined;
  const errorId = error ? `${name}-error` : undefined;
  return (
    <fieldset id={`${name}-group`} aria-describedby={[hintId, errorId].filter(Boolean).join(' ') || undefined} aria-invalid={error ? true : undefined}>
      <legend>{legend}</legend>
      {hint && (
        <p className="hint" id={hintId}>
          {hint}
        </p>
      )}
      {error && (
        <p className="field-error" id={errorId}>
          {error}
        </p>
      )}
      <div className={stacked ? 'choices stacked' : 'choices'}>
        {options.map(option => (
          <label key={option.value} className={value === option.value ? 'choice selected' : 'choice'} lang={lang?.(option.value)}>
            <input type="radio" name={name} value={option.value} checked={value === option.value} onChange={() => onChange(option.value)} />
            <span>{option.label}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}
