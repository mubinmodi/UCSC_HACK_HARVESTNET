// The household's form entries, and how they become the contract's request fields.
// Missing answers are never guessed or defaulted (front_desk.py): the page asks again instead.
import type { CreateRequestBody, HouseholdAnswers, Language, SnapAnswer } from './api';
import { pickupWindow, type DaysChoice, type Strings, type TimeChoice } from './i18n';

export const MIN_SIZE = 1;
export const MAX_SIZE = 20;

export interface FormState {
  size: number | null;
  days: DaysChoice | null;
  time: TimeChoice | null;
  fridge: 'yes' | 'no' | null;
  neighborhood: string;
  cantEat: string;
  snap: SnapAnswer | null;
  language: Language;
  email: string;
}

export const emptyForm = (language: Language): FormState => ({
  size: null,
  days: null,
  time: null,
  fridge: null,
  neighborhood: '',
  cantEat: '',
  snap: null,
  language,
  email: '',
});

export type FieldName = 'size' | 'days' | 'time' | 'fridge' | 'neighborhood' | 'email';
export type FieldErrors = Partial<Record<FieldName, string>>;

/** Match the core's optional email rules before consent, without echoing a bad address. */
export function normalizeEmail(raw: string): string | null {
  const value = raw.trim();
  if (!value || value.length > 254 || value.split('@').length !== 2) return null;
  const [local, domain] = value.split('@');
  const labels = domain.split('.');
  if (!/^[A-Za-z0-9.!#$%&*+/=?^_`{|}~-]{1,64}$/.test(local) || local.startsWith('.') || local.endsWith('.') || local.includes('..')) return null;
  if (labels.length < 2 || labels.some(label => !/^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$/.test(label))) return null;
  if (!/^[A-Za-z]{2,63}$/.test(labels.at(-1) ?? '')) return null;
  return `${local}@${domain.toLowerCase()}`;
}

export function validate(form: FormState, t: Strings): FieldErrors {
  const errors: FieldErrors = {};
  if (form.size === null) errors.size = t.required;
  if (form.days === null) errors.days = t.required;
  if (form.time === null) errors.time = t.required;
  if (form.fridge === null) errors.fridge = t.required;
  if (!form.neighborhood.trim()) errors.neighborhood = t.required;
  if (form.email.trim() && normalizeEmail(form.email) === null) errors.email = t.emailInvalid;
  return errors;
}

export function cantEatList(text: string): string[] {
  return text
    .split(/[,\n;]/)
    .map(item => item.trim())
    .filter(Boolean);
}

/** The answers in the shape preview_request takes. Only call after validate() passes. */
export function toAnswers(form: FormState): HouseholdAnswers {
  if (form.size === null || form.days === null || form.time === null || form.fridge === null) {
    throw new Error('toAnswers called before the form was complete');
  }
  return {
    language: form.language,
    household_size: form.size,
    pickup_windows: [pickupWindow(form.days, form.time)],
    limited_fridge: form.fridge === 'yes',
    neighborhood: form.neighborhood.trim(),
    cant_eat: cantEatList(form.cantEat),
    snap: form.snap ?? 'not_said',
  };
}

/** create_request: the same answers, plus consent, channel, and the optional write-only email. */
export function toCreateBody(form: FormState): CreateRequestBody {
  const body: CreateRequestBody = { ...toAnswers(form), channel: 'web', consent: true };
  if (form.email.trim()) {
    const email = normalizeEmail(form.email);
    if (!email) throw new Error('toCreateBody called with an invalid email');
    body.email = email;
  }
  return body;
}
