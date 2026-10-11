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
  phone: string;
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
  phone: '',
});

export type FieldName = 'size' | 'days' | 'time' | 'fridge' | 'neighborhood' | 'phone';
export type FieldErrors = Partial<Record<FieldName, string>>;

/** Phone as +1XXXXXXXXXX for a 10-digit US number, otherwise digits with any leading +. Null if invalid. */
export function normalizePhone(raw: string): string | null {
  const trimmed = raw.trim();
  const digits = trimmed.replace(/\D/g, '');
  if (digits.length < 10 || digits.length > 15) return null;
  if (trimmed.startsWith('+')) return `+${digits}`;
  if (digits.length === 10) return `+1${digits}`;
  if (digits.length === 11 && digits.startsWith('1')) return `+${digits}`;
  return `+${digits}`;
}

export function validate(form: FormState, t: Strings): FieldErrors {
  const errors: FieldErrors = {};
  if (form.size === null) errors.size = t.required;
  if (form.days === null) errors.days = t.required;
  if (form.time === null) errors.time = t.required;
  if (form.fridge === null) errors.fridge = t.required;
  if (!form.neighborhood.trim()) errors.neighborhood = t.required;
  if (form.phone.trim() && normalizePhone(form.phone) === null) errors.phone = t.phoneInvalid;
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

/** create_request: the same answers, plus consent, channel, and the optional phone. */
export function toCreateBody(form: FormState): CreateRequestBody {
  const body: CreateRequestBody = { ...toAnswers(form), channel: 'web', consent: true };
  const phone = form.phone.trim() ? normalizePhone(form.phone) : null;
  if (phone) body.phone = phone;
  return body;
}
