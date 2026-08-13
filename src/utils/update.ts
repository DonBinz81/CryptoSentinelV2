import { Capacitor, registerPlugin } from '@capacitor/core';
import type { PluginListenerHandle } from '@capacitor/core';

interface AppSettingsPlugin {
  downloadApk(options: { url: string }): Promise<void>;
  openDownloads(): Promise<void>;
  syncAlerts(options: { json: string }): Promise<void>;
  getAlerts(): Promise<{ json: string }>;
  syncRangeAlerts(options: { json: string }): Promise<void>;
  getRangeAlerts(): Promise<{ json: string }>;
  openWithChooser(options: { url: string; title?: string }): Promise<void>;
  addListener(event: 'downloadComplete', handler: (data: { status: string }) => void): Promise<PluginListenerHandle>;
}
const AppSettings = registerPlugin<AppSettingsPlugin>('AppSettings');

const RELEASES_API = 'https://api.github.com/repos/iridexx/CryptoSentinelHackathon/releases/latest';
const DEV_RELEASES_API = 'https://api.github.com/repos/iridexx/CryptoSentinelHackathon/releases/tags/dev';

// L'APK produzione è pubblicato su GitHub Pages, nessun login richiesto
export const APK_PAGES_URL = 'https://iridexx.github.io/CryptoSentinelHackathon/CryptoSentinelAI-latest.apk';

export interface UpdateResult {
  available: boolean;
  releaseName: string | null;
  releaseDate: string;
  buildNumber: string | null;
  releaseNotes: string | null;
  downloadUrl: string | null;
}

export interface DevBuildInfo {
  buildNumber: string | null;
  branch: string | null;
  buildDate: string;
  downloadUrl: string | null;
}

export async function checkForUpdates(currentBuildNumber: string): Promise<UpdateResult> {
  const res = await fetch(RELEASES_API, {
    headers: { Accept: 'application/vnd.github+json' },
    cache: 'no-store',
  });
  if (!res.ok) throw new Error(`GitHub API: ${res.status}`);
  const release = await res.json();

  const releaseDate = new Date(release.published_at as string);
  const apkAsset = (release.assets as { name: string; browser_download_url: string }[])
    ?.find((a) => a.name.endsWith('.apk'));
  // Tag format: "v1.0.<run_number>" — the last segment is the build number
  const tagParts = ((release.tag_name as string) ?? '').replace(/^v/, '').split('.');
  const releaseBuildNumber = parseInt(tagParts[tagParts.length - 1], 10);
  const currentBuildNum = parseInt(currentBuildNumber, 10);
  const available = !isNaN(currentBuildNum) && !isNaN(releaseBuildNumber)
    ? releaseBuildNumber > currentBuildNum
    : false;

  const rawNotes = (release.body as string | null)?.trim() ?? null;

  return {
    available,
    releaseName: (release.name as string) ?? null,
    releaseDate: releaseDate.toLocaleDateString('it-IT', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    }),
    buildNumber: isNaN(releaseBuildNumber) ? null : String(releaseBuildNumber),
    releaseNotes: rawNotes && rawNotes.length > 0 ? rawNotes : null,
    downloadUrl: apkAsset?.browser_download_url ?? null,
  };
}

export async function getDevBuildInfo(): Promise<DevBuildInfo> {
  const res = await fetch(DEV_RELEASES_API, {
    headers: { Accept: 'application/vnd.github+json' },
    cache: 'no-store',
  });
  if (!res.ok) throw new Error(`GitHub API: ${res.status}`);
  const release = await res.json();

  // Title format: "CryptoSentinelAI Dev v1.0.<run_number>" — last segment is build number
  const titleMatch = (release.name as string)?.match(/v[\d.]+\.(\d+)/);
  const notesMatch = (release.body as string)?.match(/Build #(\d+)/);
  const buildNumber = titleMatch?.[1] ?? notesMatch?.[1] ?? null;
  const branchMatch = (release.body as string)?.match(/Branch: ([^\s|]+)/);
  const apkAsset = (release.assets as { name: string; browser_download_url: string }[])
    ?.find((a) => a.name.endsWith('.apk'));

  return {
    buildNumber,
    branch: branchMatch?.[1] ?? null,
    buildDate: new Date(release.published_at as string).toLocaleDateString('it-IT', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    }),
    downloadUrl: apkAsset?.browser_download_url ?? null,
  };
}

export async function mergeToMain(branch: string, token: string): Promise<void> {
  const res = await fetch('https://api.github.com/repos/iridexx/CryptoSentinelHackathon/merges', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      Accept: 'application/vnd.github+json',
    },
    body: JSON.stringify({
      base: 'main',
      head: branch,
      commit_message: `Merge ${branch} → main (da app)`,
    }),
  });
  if (res.status === 201 || res.status === 204) return;
  const data = await res.json().catch(() => ({}));
  throw new Error((data as { message?: string }).message ?? `Errore ${res.status}`);
}

export async function downloadAndInstall(url: string): Promise<void> {
  if (Capacitor.isNativePlatform()) {
    await AppSettings.downloadApk({ url });
  } else {
    window.open(url, '_blank');
  }
}

export async function getAlertsFromNative(): Promise<string | null> {
  if (!Capacitor.isNativePlatform()) return null;
  try {
    const result = await AppSettings.getAlerts();
    return result.json ?? null;
  } catch {
    return null;
  }
}

export async function syncAlertsToNative(alerts: unknown[]): Promise<void> {
  if (!Capacitor.isNativePlatform()) return;
  try { await AppSettings.syncAlerts({ json: JSON.stringify(alerts) }); } catch { /* ignore */ }
}

export async function getRangeAlertsFromNative(): Promise<string | null> {
  if (!Capacitor.isNativePlatform()) return null;
  try {
    const result = await AppSettings.getRangeAlerts();
    return result.json ?? null;
  } catch {
    return null;
  }
}

export async function syncRangeAlertsToNative(alerts: unknown[]): Promise<void> {
  if (!Capacitor.isNativePlatform()) return;
  try { await AppSettings.syncRangeAlerts({ json: JSON.stringify(alerts) }); } catch { /* ignore */ }
}

export async function openDownloadsFolder(): Promise<void> {
  if (Capacitor.isNativePlatform()) {
    await AppSettings.openDownloads();
  }
}

export async function onDownloadComplete(handler: (ok: boolean) => void): Promise<() => void> {
  if (!Capacitor.isNativePlatform()) return () => {};
  const handle = await AppSettings.addListener('downloadComplete', (data: { status: string }) => {
    handler(data.status === 'completed');
  });
  return () => handle.remove();
}
