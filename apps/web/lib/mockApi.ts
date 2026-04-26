// Mock API-ответы для работы без backend. Включается через NEXT_PUBLIC_USE_MOCK_API=true.
// Задержка имитирует реальный запрос, но в пределах <300мс.

import { ApiError, type RequestOptions } from './apiError';
import type {
  AuditReport,
  AuditResultSummary,
  BillingAccount,
  BillingLedgerEntry,
  CrmConnection,
  DashboardOverview,
  Job,
  Notification,
  User,
  Workspace,
} from './types';

const DELAY_MS = 180;

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

// In-memory «БД».
const state: {
  user: User | null;
  workspace: Workspace;
  connections: CrmConnection[];
  jobs: Job[];
  reports: AuditReport[];
  notifications: Notification[];
  registeredEmails: Set<string>;
} = {
  user: null,
  workspace: {
    id: 'ws-demo-1',
    name: 'Demo Workspace',
    slug: 'demo',
    locale: 'ru',
    industry: 'b2b_saas',
    role: 'owner',
  },
  connections: [],
  jobs: [],
  reports: [],
  notifications: [
    {
      id: 'n1',
      kind: 'system',
      title: 'Добро пожаловать в CODE9 Analytics',
      body: 'Начните с подключения amoCRM в режиме mock, чтобы увидеть демо-аналитику.',
      read_at: null,
      created_at: new Date().toISOString(),
    },
  ],
  registeredEmails: new Set<string>(['demo@code9.app']),
};

function uid(prefix = ''): string {
  return `${prefix}${Math.random().toString(36).slice(2, 10)}`;
}

function makeAuditSummary(): AuditResultSummary {
  return {
    deals_count: 1284,
    contacts_count: 3410,
    tasks_count: 842,
    calls_count: 1920,
    pipelines_count: 3,
    users_count: 12,
    data_range_days: 540,
    estimated_storage_mb: 186,
    estimated_export_minutes: 14,
    estimated_price_rub: 2900,
  };
}

function makeDashboardOverview(): DashboardOverview {
  return {
    funnel: [
      { stage: 'Лид', count: 1200, conversion_from_previous: 1 },
      { stage: 'Квалификация', count: 820, conversion_from_previous: 0.68 },
      { stage: 'Демо', count: 510, conversion_from_previous: 0.62 },
      { stage: 'КП', count: 310, conversion_from_previous: 0.61 },
      { stage: 'Оплачен', count: 180, conversion_from_previous: 0.58 },
    ],
    conversions: { lead_to_deal: 0.26, deal_to_won: 0.58 },
    managers_activity: [
      { user_id: 'u1', name: 'Анна', deals_open: 24, deals_won: 12 },
      { user_id: 'u2', name: 'Борис', deals_open: 18, deals_won: 9 },
      { user_id: 'u3', name: 'Виктор', deals_open: 30, deals_won: 15 },
      { user_id: 'u4', name: 'Галина', deals_open: 12, deals_won: 7 },
    ],
    abandoned_deals: 84,
    total_calls: 1920,
    total_messages: 4210,
  };
}

function makeUser(email: string): User {
  return {
    id: uid('u-'),
    email,
    display_name: null,
    locale: 'ru',
    email_verified: true,
    two_factor_enabled: false,
    workspaces: [{ id: state.workspace.id, name: state.workspace.name, role: 'owner' }],
  };
}

// Matcher — примитивный роутер.
export async function mockApi<T>(path: string, opts: RequestOptions): Promise<T> {
  await sleep(DELAY_MS);
  const method = opts.method ?? 'GET';
  const body = (opts.body ?? {}) as Record<string, unknown>;
  const key = `${method} ${path.split('?')[0]}`;

  // --- Auth ---
  if (key === 'POST /auth/register') {
    const email = String(body.email ?? '').toLowerCase();
    if (state.registeredEmails.has(email)) {
      throw new ApiError(409, 'conflict', 'Email уже зарегистрирован');
    }
    state.registeredEmails.add(email);
    return { user_id: uid('u-'), email_verification_required: true } as T;
  }

  if (key === 'POST /auth/login') {
    const email = String(body.email ?? '').toLowerCase();
    const password = String(body.password ?? '');
    if (!email || !password) {
      throw new ApiError(400, 'validation_error', 'Заполните email и пароль', {
        email: !email ? 'required' : '',
        password: !password ? 'required' : '',
      });
    }
    // В mock любой пароль длиной ≥ 6 проходит.
    if (password.length < 6) {
      throw new ApiError(401, 'invalid_credentials', 'Неверные учётные данные');
    }
    state.user = makeUser(email);
    return {
      access_token: 'mock-access-token-' + uid(),
      access_token_expires_in: 900,
      user: state.user,
    } as T;
  }

  if (key === 'POST /auth/logout') {
    state.user = null;
    return undefined as T;
  }

  if (key === 'POST /auth/refresh') {
    if (!state.user) state.user = makeUser('demo@code9.app');
    return { access_token: 'mock-access-token-' + uid(), access_token_expires_in: 900 } as T;
  }

  if (key === 'POST /auth/verify-email/request') {
    return undefined as T;
  }

  if (key === 'POST /auth/verify-email/confirm') {
    const code = String(body.code ?? '');
    if (code.length !== 6) {
      throw new ApiError(400, 'validation_error', 'Код должен содержать 6 цифр', { code: 'length' });
    }
    if (code === '000000') {
      throw new ApiError(400, 'code_expired', 'Код истёк, запросите новый');
    }
    return { email_verified: true } as T;
  }

  if (key === 'POST /auth/password-reset/request') {
    return undefined as T;
  }

  if (key === 'POST /auth/password-reset/confirm') {
    const code = String(body.code ?? '');
    if (code !== '123456') {
      throw new ApiError(400, 'code_expired', 'Код недействителен');
    }
    return { ok: true } as T;
  }

  if (key === 'GET /auth/me') {
    if (!state.user) {
      throw new ApiError(401, 'unauthorized', 'Сессия не найдена');
    }
    return state.user as T;
  }

  // --- Workspaces ---
  if (key === 'GET /workspaces') {
    return [state.workspace] as T;
  }
  if (path.startsWith('/workspaces/') && method === 'GET' && path.split('/').length === 3) {
    return state.workspace as T;
  }

  // --- CRM Connections ---
  if (path.match(/^\/workspaces\/[^/]+\/crm\/connections$/) && method === 'GET') {
    return state.connections as T;
  }
  if (path.match(/^\/workspaces\/[^/]+\/crm\/connections$/) && method === 'POST') {
    const conn: CrmConnection = {
      id: uid('c-'),
      provider: (body.provider as CrmConnection['provider']) ?? 'amocrm',
      status: 'pending',
      external_account_id: '12345',
      external_domain: 'mycompany.amocrm.ru',
      last_sync_at: null,
      token_expires_at: null,
      created_at: new Date().toISOString(),
    };
    state.connections.push(conn);
    return {
      id: conn.id,
      status: conn.status,
      mock_complete_url: `/crm/connections/${conn.id}/mock-complete`,
    } as T;
  }
  if (key === 'POST /crm/connections/mock-amocrm') {
    const conn: CrmConnection = {
      id: uid('c-'),
      provider: 'amocrm',
      status: 'active',
      external_account_id: '12345',
      external_domain: 'mycompany.amocrm.ru',
      last_sync_at: new Date().toISOString(),
      token_expires_at: new Date(Date.now() + 7 * 86400 * 1000).toISOString(),
      created_at: new Date().toISOString(),
    };
    state.connections.push(conn);
    return conn as T;
  }
  const connMatch = path.match(/^\/crm\/connections\/([^/]+)(\/.*)?$/);
  if (connMatch) {
    const id = connMatch[1];
    const sub = connMatch[2] ?? '';
    const conn = state.connections.find((c) => c.id === id);
    if (!conn) throw new ApiError(404, 'not_found', 'Подключение не найдено');

    if (method === 'GET' && sub === '') return conn as T;
    if (method === 'POST' && sub === '/pause') {
      conn.status = 'paused';
      return conn as T;
    }
    if (method === 'POST' && sub === '/resume') {
      conn.status = 'active';
      return conn as T;
    }
    if (method === 'POST' && sub === '/sync') {
      const job: Job = {
        id: uid('j-'),
        kind: 'fetch_crm_data',
        status: 'succeeded',
        started_at: new Date().toISOString(),
        finished_at: new Date().toISOString(),
      };
      state.jobs.push(job);
      return { job_id: job.id } as T;
    }
    if (method === 'POST' && sub === '/delete/request') {
      return {
        deletion_request_id: uid('d-'),
        expires_at: new Date(Date.now() + 10 * 60 * 1000).toISOString(),
      } as T;
    }
    if (method === 'POST' && sub === '/delete/confirm') {
      const code = String(body.code ?? '');
      if (code !== '123456') throw new ApiError(400, 'code_expired', 'Неверный код');
      conn.status = 'deleting';
      const job: Job = {
        id: uid('j-'),
        kind: 'delete_connection_data',
        status: 'running',
        started_at: new Date().toISOString(),
      };
      state.jobs.push(job);
      return { job_id: job.id } as T;
    }
  }

  // --- Audit ---
  if (path.match(/^\/workspaces\/[^/]+\/audit\/reports$/) && method === 'POST') {
    const report: AuditReport = {
      id: uid('r-'),
      crm_connection_id: String(body.crm_connection_id ?? ''),
      created_at: new Date().toISOString(),
      summary: makeAuditSummary(),
    };
    state.reports.push(report);
    const job: Job = {
      id: uid('j-'),
      kind: 'run_audit_report',
      status: 'succeeded',
      started_at: new Date().toISOString(),
      finished_at: new Date().toISOString(),
      result: { report_id: report.id },
    };
    state.jobs.push(job);
    return { job_id: job.id } as T;
  }
  if (path.match(/^\/workspaces\/[^/]+\/audit\/reports$/) && method === 'GET') {
    return state.reports as T;
  }
  const reportMatch = path.match(/^\/workspaces\/[^/]+\/audit\/reports\/([^/]+)$/);
  if (reportMatch && method === 'GET') {
    const report = state.reports.find((r) => r.id === reportMatch[1]);
    return (report ?? { id: reportMatch[1], summary: makeAuditSummary(), created_at: new Date().toISOString() }) as T;
  }

  // --- Export ---
  if (path.match(/^\/workspaces\/[^/]+\/export\/jobs$/) && method === 'POST') {
    const job: Job = {
      id: uid('j-'),
      kind: 'build_export_zip',
      status: 'succeeded',
      started_at: new Date().toISOString(),
      finished_at: new Date().toISOString(),
      result: { download_url: '/mock/export.zip' },
    };
    state.jobs.push(job);
    return { job_id: job.id } as T;
  }

  // --- Dashboards ---
  if (path.match(/^\/workspaces\/[^/]+\/dashboards\/overview$/)) {
    return makeDashboardOverview() as T;
  }
  if (path.match(/^\/workspaces\/[^/]+\/dashboards\/funnel$/)) {
    return makeDashboardOverview().funnel as T;
  }
  if (path.match(/^\/workspaces\/[^/]+\/dashboards\/managers$/)) {
    return makeDashboardOverview().managers_activity as T;
  }

  // --- Jobs ---
  const jobMatch = path.match(/^\/workspaces\/[^/]+\/jobs\/([^/]+)$/);
  if (jobMatch && method === 'GET') {
    const job = state.jobs.find((j) => j.id === jobMatch[1]);
    if (!job) throw new ApiError(404, 'not_found', 'Job не найден');
    return job as T;
  }

  // --- Notifications ---
  if (path.match(/^\/workspaces\/[^/]+\/notifications$/)) {
    return state.notifications as T;
  }
  const notifMatch = path.match(/^\/workspaces\/[^/]+\/notifications\/([^/]+)\/read$/);
  if (notifMatch && method === 'POST') {
    const n = state.notifications.find((n) => n.id === notifMatch[1]);
    if (n) n.read_at = new Date().toISOString();
    return undefined as T;
  }

  // --- Billing ---
  if (path.match(/^\/workspaces\/[^/]+\/billing\/account$/)) {
    return {
      balance_cents: 450000,
      currency: 'RUB',
      plan: 'pay_as_you_go',
      provider: 'yookassa',
    } as BillingAccount as T;
  }
  if (path.match(/^\/workspaces\/[^/]+\/billing\/ledger$/)) {
    const entries: BillingLedgerEntry[] = [
      {
        id: 'l1',
        kind: 'deposit',
        amount_cents: 500000,
        currency: 'RUB',
        description: 'Пополнение, ЮKassa',
        created_at: new Date(Date.now() - 3 * 86400 * 1000).toISOString(),
      },
      {
        id: 'l2',
        kind: 'charge',
        amount_cents: -50000,
        currency: 'RUB',
        description: 'Тестовая выгрузка 100 сделок',
        created_at: new Date(Date.now() - 86400 * 1000).toISOString(),
      },
    ];
    return { items: entries } as T;
  }

  // --- AI ---
  if (path.match(/^\/workspaces\/[^/]+\/ai\/consent$/) && method === 'GET') {
    return { status: 'not_accepted' } as T;
  }
  if (path.match(/^\/workspaces\/[^/]+\/ai\/consent$/) && method === 'POST') {
    return { status: body.action === 'accept' ? 'accepted' : 'revoked' } as T;
  }
  if (path.match(/^\/workspaces\/[^/]+\/ai\/knowledge$/) && method === 'GET') {
    return [] as T;
  }

  // --- Admin ---
  if (key === 'POST /admin/auth/login') {
    const email = String(body.email ?? '').toLowerCase();
    const password = String(body.password ?? '');
    if (password.length < 6) {
      throw new ApiError(401, 'invalid_credentials', 'Неверные учётные данные');
    }
    return {
      access_token: 'mock-admin-token-' + uid(),
      access_token_expires_in: 900,
      admin: { id: 'adm-1', email, role: 'superadmin' },
    } as T;
  }
  if (key === 'POST /admin/auth/logout') return undefined as T;
  if (key === 'GET /admin/workspaces') {
    return {
      items: [
        {
          id: 'ws-1',
          name: 'Acme Corp',
          slug: 'acme',
          status: 'active',
          owner_email: 'owner@acme.test',
          owner_name: 'Owner',
          plan: 'enterprise',
          billing_plan: 'enterprise',
          token_plan: 'enterprise',
          balance_tokens: 100000,
          available_tokens: 95000,
          reserved_tokens: 5000,
          subscription_expires_at: new Date(Date.now() + 365 * 86400 * 1000).toISOString(),
          connections: 1,
          active_connections: 1,
          error_connections: 0,
          last_error: null,
        },
        {
          id: 'ws-2',
          name: 'Globex',
          slug: 'globex',
          status: 'paused',
          owner_email: 'owner@globex.test',
          owner_name: 'Owner',
          plan: 'free',
          billing_plan: 'free',
          token_plan: 'free',
          balance_tokens: 0,
          available_tokens: 0,
          reserved_tokens: 0,
          subscription_expires_at: null,
          connections: 0,
          active_connections: 0,
          error_connections: 0,
          last_error: null,
        },
      ],
    } as T;
  }
  if (path.match(/^\/admin\/workspaces\/[^/]+\/manual-billing$/) && method === 'POST') {
    return {
      ok: true,
      workspace_id: path.split('/')[3],
      token_account: {
        plan_key: body.plan_key,
        balance_tokens: Number(body.add_tokens || 0),
        reserved_tokens: 0,
        available_tokens: Number(body.add_tokens || 0),
        subscription_expires_at: body.expires_at ?? null,
      },
      billing_plan: body.plan_key,
    } as T;
  }
  if (key === 'GET /admin/users') {
    return {
      items: [
        { id: 'u-1', email: 'owner@acme.com', display_name: 'Owner', created_at: new Date().toISOString() },
      ],
    } as T;
  }
  if (key === 'GET /admin/connections') {
    return { items: state.connections } as T;
  }
  if (key === 'GET /admin/jobs') {
    return { items: state.jobs } as T;
  }
  if (key === 'GET /admin/audit-logs') {
    return {
      items: [
        {
          id: 'al-1',
          admin_user_id: 'adm-1',
          action: 'admin.login',
          target: '-',
          created_at: new Date().toISOString(),
        },
      ],
    } as T;
  }
  if (key === 'GET /admin/ai/research-patterns') {
    return { items: [] } as T;
  }
  if (key === 'GET /admin/billing') {
    return { total_balance_cents: 1200000, currency: 'RUB' } as T;
  }

  // Fallback.
  throw new ApiError(404, 'not_found', `Mock: неизвестный endpoint ${key}`);
}
