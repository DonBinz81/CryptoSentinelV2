import { Capacitor, CapacitorHttp } from '@capacitor/core';

/**
 * Unico punto di configurazione e trasporto verso il backend.
 *
 * Prima esistevano tre copie del wrapper nativo/web (agentApi, supportApi,
 * marketData) piu' sei chiamate CapacitorHttp sparse: la copia di alertSync era
 * l'unica senza controllo dello status, e i sync falliti passavano per riusciti.
 * Qui lo status viene controllato SEMPRE: CapacitorHttp, a differenza di fetch,
 * risolve anche su 4xx/5xx.
 *
 * Uso diretto di CapacitorHttp fuori da questo modulo: solo per la diagnostica
 * in SettingsTab, che misura latenza/raggiungibilita' e mappa gli errori grezzi.
 */

export const BACKEND_URL = (import.meta.env.VITE_BACKEND_API_BASE_URL as string | undefined)?.replace(/\/+$/, '') ?? '';
export const READ_TOKEN = (import.meta.env.VITE_API_READ_TOKEN as string | undefined) ?? '';
export const DEVICE_TOKEN = (import.meta.env.VITE_API_DEVICE_TOKEN as string | undefined) ?? '';
export const ALERTS_TOKEN = (import.meta.env.VITE_API_ALERTS_TOKEN as string | undefined) ?? '';

/** Errore HTTP con status leggibile dal chiamante (retry, logging, messaggi). */
export class BackendHttpError extends Error {
  readonly status: number;
  constructor(status: number, label: string, detail?: string) {
    super(detail ? `${label}: ${status} — ${detail}` : `${label}: ${status}`);
    this.name = 'BackendHttpError';
    this.status = status;
  }
}

/**
 * Rende leggibile il corpo di errore di FastAPI.
 * Su 422 il body è {"detail":[{"loc":["body","perp_min_rr"],"msg":"..."}]}:
 * senza questa estrazione l'utente vedeva solo "422" e non sapeva QUALE
 * campo avesse un valore fuori dai limiti.
 */
function describeError(body: unknown): string | undefined {
  if (!body || typeof body !== 'object') return undefined;
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === 'string') return detail;
  if (!Array.isArray(detail)) return undefined;
  const parts = detail.slice(0, 3).map((d) => {
    const item = d as { loc?: unknown[]; msg?: string };
    const campo = Array.isArray(item.loc)
      ? item.loc.filter((x) => x !== 'body').join('.')
      : '';
    const msg = item.msg ?? 'valore non valido';
    return campo ? `${campo}: ${msg}` : msg;
  });
  return parts.length ? parts.join(' · ') : undefined;
}

export interface BackendRequestOptions {
  method?: 'GET' | 'PUT' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  token?: string;
  /** Prefisso dei messaggi d'errore, es. 'Agent API' → 'Agent API: 503'. */
  label?: string;
  timeoutMs?: number;
  connectTimeoutMs?: number;
  extraHeaders?: Record<string, string>;
}

export function requireBackend(label = 'API'): string {
  if (!BACKEND_URL) throw new Error(`${label}: backend URL is not configured`);
  return BACKEND_URL;
}

export function authHeaders(token = READ_TOKEN): Record<string, string> {
  if (!token) throw new Error('API token is not configured');
  return { Authorization: `Bearer ${token}`, Accept: 'application/json' };
}

export async function backendRequest<T>(path: string, options: BackendRequestOptions = {}): Promise<T> {
  const method = options.method ?? 'GET';
  const label = options.label ?? 'API';
  const timeoutMs = options.timeoutMs ?? 30_000;
  const url = `${requireBackend(label)}${path}`;
  const headers = {
    ...authHeaders(options.token),
    ...(options.body ? { 'Content-Type': 'application/json' } : {}),
    ...(options.extraHeaders ?? {}),
  };

  if (Capacitor.isNativePlatform()) {
    const response = await CapacitorHttp.request({
      method,
      url,
      headers,
      data: options.body,
      connectTimeout: options.connectTimeoutMs ?? Math.min(12_000, timeoutMs),
      readTimeout: timeoutMs,
    });
    if (response.status < 200 || response.status >= 300) {
      throw new BackendHttpError(response.status, label, describeError(response.data));
    }
    return response.data as T;
  }

  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      method,
      headers,
      body: options.body ? JSON.stringify(options.body) : undefined,
      signal: controller.signal,
    });
    if (!response.ok) {
      const body = await response.json().catch(() => undefined);
      throw new BackendHttpError(response.status, label, describeError(body));
    }
    if (response.status === 204) return undefined as T;
    return await response.json() as T;
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new Error(`${label}: timeout`);
    }
    throw err;
  } finally {
    window.clearTimeout(timer);
  }
}
