// Display helpers. They only format values the API sent; they never compute quantities.
import type { Amendment, Mover, TimeWindow } from './types';

// Scenario times are Pacific (contracts README decision 3); show them in that zone.
const ZONE = 'America/Los_Angeles';

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return 'not set';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat('en-US', { timeZone: ZONE, hour: 'numeric', minute: '2-digit' }).format(date);
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return 'not set';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat('en-US', {
    timeZone: ZONE,
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(date);
}

export function formatWindow(window: TimeWindow | null | undefined): string {
  if (!window) return 'not set';
  return `${formatDateTime(window.start)} to ${formatTime(window.end)}`;
}

export function lb(pounds: number | null | undefined): string {
  if (pounds === null || pounds === undefined || Number.isNaN(pounds)) return 'unknown';
  return `${Number(pounds).toLocaleString('en-US', { maximumFractionDigits: 1 })} lb`;
}

export function moverText(mover: Mover | undefined): string {
  if (mover === 'donor') return 'Donor drops off';
  if (mover === 'food_bank') return 'Food bank collects';
  return mover ? `Moved by ${mover}` : 'Mover not agreed yet';
}

export function humanize(value: string | null | undefined): string {
  if (!value) return '';
  const text = value.replace(/_/g, ' ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export type Names = Record<string, string>;

export const nameOf = (names: Names | undefined, id: string | undefined) => (id ? names?.[id] ?? id : 'unknown');

export function describeChange(change: Amendment | null, names?: Names): string {
  if (!change) return 'First version, no change.';
  const produce = change.produce_id ? humanize(change.produce_id) : 'produce';
  switch (change.kind) {
    case 'set_pounds':
      return `Set ${produce} for ${nameOf(names, change.food_bank_id)} to ${lb(change.pounds)}.`;
    case 'shift_pounds':
      return `Move ${lb(change.pounds)} of ${produce} from ${nameOf(names, change.from_food_bank_id)} to ${nameOf(names, change.to_food_bank_id)}.`;
    case 'set_transport':
      return `${nameOf(names, change.food_bank_id)}: ${moverText(change.mover).toLowerCase()}, leaving ${formatTime(change.departs_at)}, arriving ${formatTime(change.arrives_at)}.`;
    default:
      return humanize(change.kind);
  }
}

/** A datetime-local value ("2026-10-13T15:00") as ISO 8601 with the browser's UTC offset. */
export function localInputToIso(value: string): string {
  const date = new Date(value);
  if (!value || Number.isNaN(date.getTime())) return '';
  const offset = -date.getTimezoneOffset();
  const sign = offset >= 0 ? '+' : '-';
  const pad = (n: number) => String(Math.floor(Math.abs(n))).padStart(2, '0');
  return `${value.length === 16 ? value + ':00' : value}${sign}${pad(offset / 60)}:${pad(offset % 60)}`;
}

/** An ISO time as a datetime-local value in the browser's zone. */
export function isoToLocalInput(iso: string | null | undefined): string {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 16);
}
