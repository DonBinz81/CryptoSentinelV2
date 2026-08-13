import { Capacitor, CapacitorHttp } from '@capacitor/core';
import { getDeviceId } from '../utils/deviceId';

export type TicketCategory = 'bug' | 'alert' | 'market' | 'agent' | 'wallet' | 'other';
export type TicketPriority = 'low' | 'medium' | 'high' | 'critical';
export type TicketStatus = 'open' | 'in_progress' | 'waiting_user' | 'resolved' | 'closed' | 'archived';

export interface SupportMessage {
  message_id: string;
  ticket_id: string;
  sender_type: 'user' | 'admin';
  sender_id: string | null;
  body: string;
  diagnostics: Record<string, unknown> | null;
  created_at: string;
}

export interface SupportTicketSummary {
  ticket_id: string;
  user_id: string;
  device_id: string | null;
  display_name: string;
  category: TicketCategory;
  priority: TicketPriority;
  status: TicketStatus;
  subject: string;
  created_at: string;
  updated_at: string;
  last_message_at: string;
  resolved_at: string | null;
  closed_at: string | null;
  closed_by: string | null;
  message_count: number;
  has_unread: boolean;
}

export interface SupportTicketDetail extends SupportTicketSummary {
  messages: SupportMessage[];
  last_seen_at: string | null;
}

export interface SupportNotificationResponse {
  unread_count: number;
  latest_ticket: SupportTicketSummary | null;
}

const BACKEND_URL = (import.meta.env.VITE_BACKEND_API_BASE_URL as string | undefined)?.replace(/\/+$/, '');
const READ_TOKEN = import.meta.env.VITE_API_READ_TOKEN as string | undefined;

function requireBackend(): string {
  if (!BACKEND_URL) throw new Error('Backend URL is not configured');
  return BACKEND_URL;
}

function authHeaders(token = READ_TOKEN): Record<string, string> {
  if (!token) throw new Error('API token is not configured');
  return { Authorization: `Bearer ${token}`, Accept: 'application/json' };
}

async function request<T>(
  path: string,
  options: { method?: 'GET' | 'POST' | 'PATCH'; body?: unknown; token?: string } = {},
): Promise<T> {
  const method = options.method ?? 'GET';
  const url = `${requireBackend()}${path}`;
  const headers = {
    ...authHeaders(options.token),
    ...(options.body ? { 'Content-Type': 'application/json' } : {}),
  };
  if (Capacitor.isNativePlatform()) {
    const response = await CapacitorHttp.request({
      method,
      url,
      headers,
      data: options.body,
      connectTimeout: 10_000,
      readTimeout: 20_000,
    });
    if (response.status < 200 || response.status >= 300) {
      throw new Error(`Support API: ${response.status}`);
    }
    return response.data as T;
  }
  const response = await fetch(url, {
    method,
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  if (!response.ok) throw new Error(`Support API: ${response.status}`);
  return await response.json() as T;
}

export function supportDeviceId(): string {
  return getDeviceId();
}

export function syncDeviceProfile(displayName: string): Promise<unknown> {
  return request('/api/v1/support/device-profile', {
    method: 'POST',
    body: {
      device_id: getDeviceId(),
      display_name: displayName,
      platform: Capacitor.getPlatform(),
      app_version: __APP_VERSION__,
      build_number: String(__APP_BUILD_NUMBER__),
      locale: navigator.language,
    },
  });
}

export function listSupportTickets(): Promise<{ items: SupportTicketSummary[]; total: number }> {
  return request(`/api/v1/support/tickets?device_id=${encodeURIComponent(getDeviceId())}`);
}

export function getSupportNotifications(): Promise<SupportNotificationResponse> {
  return request('/api/v1/support/notifications');
}

export function getSupportTicket(ticketId: string): Promise<SupportTicketDetail> {
  return request(`/api/v1/support/tickets/${encodeURIComponent(ticketId)}?device_id=${encodeURIComponent(getDeviceId())}`);
}

export function markSupportTicketRead(ticketId: string): Promise<SupportTicketDetail> {
  return request(`/api/v1/support/tickets/${encodeURIComponent(ticketId)}/read?device_id=${encodeURIComponent(getDeviceId())}`, {
    method: 'POST',
  });
}

export function markAllSupportTicketsRead(): Promise<{ updated: number }> {
  return request('/api/v1/support/tickets/read-all', {
    method: 'POST',
  });
}

export function createSupportTicket(payload: {
  displayName: string;
  category: TicketCategory;
  priority: TicketPriority;
  subject: string;
  message: string;
  includeDiagnostics: boolean;
}): Promise<SupportTicketDetail> {
  return request('/api/v1/support/tickets', {
    method: 'POST',
    body: {
      device_id: getDeviceId(),
      display_name: payload.displayName,
      category: payload.category,
      priority: payload.priority,
      subject: payload.subject,
      message: payload.message,
      diagnostics: payload.includeDiagnostics ? safeDiagnostics() : null,
    },
  });
}

export function replySupportTicket(ticketId: string, message: string): Promise<SupportTicketDetail> {
  return request(`/api/v1/support/tickets/${encodeURIComponent(ticketId)}/messages`, {
    method: 'POST',
    body: { device_id: getDeviceId(), message },
  });
}

export function closeSupportTicket(ticketId: string): Promise<SupportTicketDetail> {
  return request(`/api/v1/support/tickets/${encodeURIComponent(ticketId)}/close`, {
    method: 'POST',
    body: { device_id: getDeviceId(), message: 'Closed by user' },
  });
}

export function adminListSupportTickets(adminToken: string): Promise<{ items: SupportTicketSummary[]; total: number }> {
  return request('/api/v1/support/admin/tickets', { token: adminToken });
}

export function adminGetSupportNotifications(adminToken: string): Promise<SupportNotificationResponse> {
  return request('/api/v1/support/admin/notifications', { token: adminToken });
}

export function adminGetSupportTicket(ticketId: string, adminToken: string): Promise<SupportTicketDetail> {
  return request(`/api/v1/support/admin/tickets/${encodeURIComponent(ticketId)}`, { token: adminToken });
}

export function adminMarkSupportTicketRead(ticketId: string, adminToken: string): Promise<SupportTicketDetail> {
  return request(`/api/v1/support/admin/tickets/${encodeURIComponent(ticketId)}/read`, {
    method: 'POST',
    token: adminToken,
  });
}

export function adminMarkAllSupportTicketsRead(adminToken: string): Promise<{ updated: number }> {
  return request('/api/v1/support/admin/tickets/read-all', {
    method: 'POST',
    token: adminToken,
  });
}

export function adminReplySupportTicket(ticketId: string, message: string, adminToken: string): Promise<SupportTicketDetail> {
  return request(`/api/v1/support/admin/tickets/${encodeURIComponent(ticketId)}/messages`, {
    method: 'POST',
    token: adminToken,
    body: { message },
  });
}

export function adminUpdateSupportStatus(ticketId: string, status: TicketStatus, adminToken: string): Promise<SupportTicketDetail> {
  return request(`/api/v1/support/admin/tickets/${encodeURIComponent(ticketId)}/status`, {
    method: 'PATCH',
    token: adminToken,
    body: { status },
  });
}

function safeDiagnostics(): Record<string, unknown> {
  return {
    app_version: __APP_VERSION__,
    build_number: String(__APP_BUILD_NUMBER__),
    platform: Capacitor.getPlatform(),
    locale: navigator.language,
    device_id: getDeviceId(),
    backend_url: BACKEND_URL ?? null,
    timestamp: new Date().toISOString(),
  };
}
