import { describe, expect, it } from 'vitest';
import { parsePickupLink } from '../pickupLink';

describe('pickup email links', () => {
  it('reads the pickup, request code, and language from the URL fragment', () => {
    expect(parsePickupLink('#pickup=pk-1%202&code=K7P4&lang=es')).toBeNull();
    expect(parsePickupLink('#pickup=pk-1013-0001&code=K7P4&lang=es')).toEqual({
      pickupId: 'pk-1013-0001', requestCode: 'K7P4', language: 'es',
    });
  });

  it('ignores page anchors and incomplete or malformed links', () => {
    for (const hash of ['#main-content', '#pickup=pk-1&code=K7P4', '#pickup=pk-1&code=K7P4&lang=fr', '#pickup=%2F&code=K7P4&lang=en']) {
      expect(parsePickupLink(hash)).toBeNull();
    }
  });
});
