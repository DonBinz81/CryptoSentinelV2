// Stable per-installation device identifier.
// Used to keep each device's alert configuration and notifications separate on
// the backend (single user_id, separated by device_id). Persisted in
// localStorage so it survives app restarts; regenerated only on reinstall/clear.

const DEVICE_ID_KEY = 'cs_device_id';

function generateUuid(): string {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
  } catch {
    // fall through to manual generation
  }
  // RFC4122-ish v4 fallback for environments without crypto.randomUUID.
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export function getDeviceId(): string {
  try {
    const existing = localStorage.getItem(DEVICE_ID_KEY);
    if (existing) return existing;
    const id = generateUuid();
    localStorage.setItem(DEVICE_ID_KEY, id);
    return id;
  } catch {
    // localStorage unavailable: return an ephemeral id (still works per session).
    return generateUuid();
  }
}
