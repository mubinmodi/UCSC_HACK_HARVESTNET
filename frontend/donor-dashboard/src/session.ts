// Per-tab session state. Staff tokens live in memory and in sessionStorage only (cleared
// when the tab closes). They are never written to localStorage, the URL, logs, or Git.
const PREFIX = 'harvestnet.';
const memory = new Map<string, string>();

function read(key: string): string {
  if (memory.has(key)) return memory.get(key) ?? '';
  try {
    return window.sessionStorage.getItem(PREFIX + key) ?? '';
  } catch {
    return '';
  }
}

function write(key: string, value: string) {
  if (value) memory.set(key, value);
  else memory.delete(key);
  try {
    if (value) window.sessionStorage.setItem(PREFIX + key, value);
    else window.sessionStorage.removeItem(PREFIX + key);
  } catch {
    // Storage blocked: the in-memory copy still works for this page load.
  }
}

export const staffToken = {
  get: (organizationId: string) => read(`staff-token.${organizationId}`),
  set: (organizationId: string, token: string) => write(`staff-token.${organizationId}`, token.trim()),
  clear: (organizationId: string) => write(`staff-token.${organizationId}`, ''),
};

export const sessionValue = {
  get: (key: string) => read(key),
  set: (key: string, value: string) => write(key, value),
};

/** Lots this donor created in this tab, newest first. Only IDs are kept. */
export const recentLots = {
  list(donorId: string): string[] {
    try {
      const parsed = JSON.parse(read(`lots.${donorId}`) || '[]');
      return Array.isArray(parsed) ? parsed.filter((v) => typeof v === 'string') : [];
    } catch {
      return [];
    }
  },
  add(donorId: string, lotId: string) {
    const next = [lotId, ...recentLots.list(donorId).filter((id) => id !== lotId)].slice(0, 20);
    write(`lots.${donorId}`, JSON.stringify(next));
  },
};

/** Test helper: forget everything held in memory. */
export function resetSessionForTests() {
  memory.clear();
  try {
    window.sessionStorage.clear();
  } catch {
    // ignore
  }
}
