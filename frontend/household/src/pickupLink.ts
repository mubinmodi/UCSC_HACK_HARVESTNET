import type { Language } from './api';

export interface PickupLink {
  pickupId: string;
  requestCode: string;
  language: Language;
}

/** Pickup email links carry their identifiers only in the URL fragment, not a server request. */
export function parsePickupLink(hash: string): PickupLink | null {
  if (!hash.startsWith('#')) return null;
  const params = new URLSearchParams(hash.slice(1));
  const pickupId = params.get('pickup');
  const requestCode = params.get('code');
  const language = params.get('lang');
  if (!pickupId || !/^[A-Za-z0-9._-]{1,120}$/.test(pickupId)) return null;
  if (!requestCode || !/^[A-Za-z0-9]{4,12}$/.test(requestCode)) return null;
  if (language !== 'en' && language !== 'es') return null;
  return { pickupId, requestCode, language };
}
