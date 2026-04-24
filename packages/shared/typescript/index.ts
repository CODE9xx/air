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
    companies?: number;
    contacts?: number;
    deals?: number;
  };
  last_trial_export_at?: string | null;
  last_trial_export_counts?: {
    pipelines?: number;
    stages?: number;
    users?: number;
    companies?: number;
    contacts?: number;
    deals?: number;
  };
  active_export?: {
    mode?: 'real' | string;
    date_basis?: 'created_at' | string;
    date_from?: string | null;
    date_to?: string | null;
    pipeline_ids?: string[];
    counts?: {
      pipelines?: number;
      stages?: number;
      users?: number;
      companies?: number;
      contacts?: number;
      deals?: number;
    };
    completed_at?: string | null;
  };
  token_estimate_snapshot?: {
    source?: string;
    captured_at?: string | null;
    counts?: {
      deals?: number;
      contacts?: number;
      companies?: number;
      lead_notes?: number;
      events?: number;
    };
    avg_tokens?: {
      deals?: number;
      contacts?: number;
      companies?: number;
      lead_notes?: number;
      events?: number;
    };
    confidence?: Record<string, string>;
    notes?: string[];
  };
  // #44.6 external_button:
  amocrm_auth_mode?: 'static_client' | 'external_button';
  amocrm_external_integration?: {
    integration_id?: string | null;
    account_id?: number | null;
    account_subdomain?: string | null;
    received_at?: string | null;
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
  // #44.6 — top-level поля для удобства UI.
  amocrm_auth_mode?: 'static_client' | 'external_button' | null;
  amocrm_external_integration_id?: string | null;
  amocrm_credentials_received_at?: string | null;
}

/**
 * Payload возвращаемый `GET /integrations/amocrm/oauth/start`.
 *
 *   mock=true              → redirect_url: BE уже создал active подключение.
 *   auth_mode=static_client → authorize_url: редиректим на amoCRM consent.
 *   auth_mode=external_button → authorize_url=null, фронт показывает
 *     embedded amoCRM install-button с state + redirect_uri.
 */
export type AmoAuthMode = 'static_client' | 'external_button';

export interface AmoOAuthStartResponse {
  mock: boolean;
  auth_mode?: AmoAuthMode;
  connection_id: string;
  authorize_url?: string | null;
  state?: string;
  redirect_uri?: string;
  redirect_url?: string;
}

/**
 * Публичная метаинформация кнопки (data-* для <script class="amocrm_oauth">).
 * Секретов не содержит.
 */
export interface AmoButtonMeta {
  name?: string | null;
  description?: string | null;
  logo?: string | null;
  scopes?: string | null;
  title?: string | null;
}

/**
 * Payload возвращаемый `GET /integrations/amocrm/oauth/button-config`.
 * Используется фронтом для рендера кнопки/инструкции в зависимости от режима.
 *
 * `secrets_uri` — primary (соответствует amoCRM data-secrets_uri, v2 #44.6).
 * `webhook_url` — legacy alias; backend дублирует туда то же значение
 *                 для фронтов, которые ещё не мигрировали. Новый код должен
 *                 читать `secrets_uri`.
 */
export interface AmoButtonConfig {
  mock: boolean;
  auth_mode: AmoAuthMode;
  redirect_uri?: string | null;
  secrets_uri?: string;
  /** @deprecated alias of `secrets_uri`; will be removed after #48.x. */
  webhook_url?: string;
  wait_seconds?: number;
  client_id?: string | null;
  button?: AmoButtonMeta;
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

export interface TokenEstimateItem {
  key: 'deals' | 'contacts' | 'companies' | 'lead_notes' | 'events' | string;
  label: string;
  count: number;
  avg_tokens: number;
  estimated_tokens: number;
  confidence: string;
}

export interface TokenEstimateResponse {
  connection_id: string;
  period: 'all_time' | 'active_export' | string;
  source: string;
  basis: 'full_database_snapshot' | 'active_export_lower_bound' | 'active_export_scaled' | string;
  date_from?: string | null;
  date_to?: string | null;
  captured_at?: string | null;
  encoding: string;
  items: TokenEstimateItem[];
  total_tokens_without_calls: number;
  calls: {
    minutes: number;
    tokens_per_minute_low: number;
    tokens_per_minute_high: number;
    estimated_tokens_low: number;
    estimated_tokens_high: number;
    confidence: string;
  };
  total_tokens_low: number;
  total_tokens_high: number;
  notes: string[];
}

export interface DashboardOverview {
  funnel: Array<{ stage: string; count: number; conversion_from_previous: number | null }>;
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
