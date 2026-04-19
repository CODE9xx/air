// Общие TypeScript-типы между apps/web и (в перспективе) API-генерацией.
// Источник истины — docs/api/CONTRACT.md.

export type Locale = 'ru' | 'en';

export interface User {
  id: string;
  email: string;
  display_name: string | null;
  locale: Locale;
  email_verified: boolean;
  two_factor_enabled?: boolean;
  workspaces?: WorkspaceMembership[];
}

export interface WorkspaceMembership {
  id: string;
  name: string;
  role: 'owner' | 'admin' | 'analyst' | 'viewer';
  slug?: string;
}

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  locale: Locale;
  industry?: string;
  role?: 'owner' | 'admin' | 'analyst' | 'viewer';
}

export type CrmProvider = 'amocrm' | 'kommo' | 'bitrix24' | 'mock';

export type CrmConnectionStatus =
  | 'pending'
  | 'active'
  | 'paused'
  | 'failed'
  | 'deleting'
  | 'deleted';

export interface AmoAccountMeta {
  id?: number | string | null;
  name?: string | null;
  subdomain?: string | null;
  country?: string | null;
  currency?: string | null;
}

export interface CrmConnectionMetadata {
  mock?: boolean;
  source?: string;
  amo_account?: AmoAccountMeta;
  last_pull_at?: string | null;
  last_pull_counts?: {
    pipelines?: number;
    stages?: number;
    users?: number;
    contacts?: number;
    deals?: number;
  };
  [key: string]: unknown;
}

export interface CrmConnection {
  id: string;
  workspace_id?: string;
  name?: string;
  provider: CrmProvider;
  status: CrmConnectionStatus;
  external_account_id?: string;
  external_domain?: string;
  tenant_schema?: string | null;
  last_sync_at?: string | null;
  token_expires_at?: string | null;
  last_error?: string | null;
  metadata?: CrmConnectionMetadata;
  created_at?: string;
}

/**
 * Payload возвращаемый `GET /integrations/amocrm/oauth/start`.
 * В MOCK-режиме — `mock: true, redirect_url`; в реальном — `authorize_url + state`.
 */
export interface AmoOAuthStartResponse {
  mock: boolean;
  connection_id: string;
  authorize_url?: string;
  state?: string;
  redirect_url?: string;
}

export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';

export interface Job {
  id: string;
  kind: string;
  status: JobStatus;
  payload?: Record<string, unknown>;
  result?: Record<string, unknown> | null;
  error?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface AuditResultSummary {
  deals_count: number;
  contacts_count: number;
  tasks_count: number;
  calls_count: number;
  pipelines_count: number;
  users_count: number;
  data_range_days: number;
  estimated_storage_mb: number;
  estimated_export_minutes: number;
  estimated_price_rub: number;
}

export interface AuditReport {
  id: string;
  crm_connection_id: string;
  created_at: string;
  summary: AuditResultSummary;
}

export interface DashboardOverview {
  funnel: Array<{ stage: string; count: number; conversion_from_previous: number }>;
  conversions: { lead_to_deal: number; deal_to_won: number };
  managers_activity: Array<{ user_id: string; name: string; deals_open: number; deals_won: number }>;
  abandoned_deals: number;
  total_calls: number;
  total_messages: number;
}

export interface Notification {
  id: string;
  kind: string;
  title: string;
  body?: string;
  read_at: string | null;
  created_at: string;
}

export interface BillingAccount {
  balance_cents: number;
  currency: 'RUB' | 'USD' | 'EUR';
  plan: string;
  provider: string;
}

export interface BillingLedgerEntry {
  id: string;
  kind: 'deposit' | 'charge' | 'refund' | 'adjustment';
  amount_cents: number;
  currency: string;
  description: string;
  created_at: string;
}

export interface ApiErrorShape {
  error: {
    code: string;
    message: string;
    field_errors?: Record<string, string>;
  };
}

export interface AdminUser {
  id: string;
  email: string;
  role: 'superadmin' | 'support';
}
