export type DashboardWidgetType =
  | string
  | 'kpi_applications'
  | 'kpi_open'
  | 'kpi_sales_amount'
  | 'kpi_sales_count'
  | 'kpi_lost'
  | 'kpi_avg_deal'
  | 'kpi_conversion'
  | 'kpi_pipeline_count'
  | 'kpi_manager_count'
  | 'line_dynamics'
  | 'revenue_dynamics'
  | 'status_structure'
  | 'stage_funnel'
  | 'pipeline_health'
  | 'pipeline_stale'
  | 'manager_table'
  | 'manager_revenue_rank'
  | 'manager_conversion_rank'
  | 'manager_risk'
  | 'top_deals'
  | 'open_age_buckets'
  | 'pipeline_table'
  | 'phase2b_calls'
  | 'phase2b_messages'
  | 'phase2b_email'
  | 'phase2b_sources'
  | 'phase2b_lost_reasons';

export type DashboardPage = {
  page_key: string;
  title: string;
};

export type DashboardWidget = {
  id?: string;
  widget_key: string;
  widget_type: DashboardWidgetType;
  title: string;
  x: number;
  y: number;
  w: number;
  h: number;
  config: Record<string, unknown>;
};

export type DashboardWidgetAvailability =
  | 'available'
  | 'requires_mapping'
  | 'requires_integration'
  | 'requires_ai';

export type DashboardTemplate = {
  template_key: string;
  title: string;
  category: string;
  widgets: DashboardWidgetType[];
  requirements?: string[];
};

export type DashboardBuilderPayload = {
  dashboard: {
    id: string;
    name: string;
    filters: Record<string, unknown>;
    created_at: string | null;
    updated_at: string | null;
  };
  pages?: DashboardPage[];
  widgets: DashboardWidget[];
  share: {
    enabled: boolean;
    share_url: string | null;
    created_at: string | null;
    last_accessed_at: string | null;
  };
  widget_catalog: Array<{
    widget_type: DashboardWidgetType;
    title: string;
    group?: string;
    availability?: DashboardWidgetAvailability;
    requirements?: string[];
    description?: string | null;
    w: number;
    h: number;
    placeholder?: boolean;
  }>;
  dashboard_templates?: DashboardTemplate[];
  sales?: SalesDashboardSnapshot;
  embed?: boolean;
};

export type SalesDashboardSnapshot = {
  mock: boolean;
  filters?: {
    period?: string | null;
    date_from?: string | null;
    date_to?: string | null;
    pipeline_id?: string | null;
    pipeline_ids?: string[];
    active_pipeline_ids?: string[];
  };
  kpis: {
    total_deals: number;
    open_deals: number;
    won_deals: number;
    lost_deals: number;
    won_rate: number;
    lost_rate: number;
    revenue_rub: number;
    avg_deal_rub?: number;
    date_from?: string | null;
    date_to?: string | null;
    pipeline_count?: number;
    manager_count?: number;
  };
  monthly_revenue: Array<{
    month: string | null;
    deals: number;
    won_deals: number;
    lost_deals?: number;
    revenue_rub: number;
  }>;
  pipeline_breakdown: Array<{
    pipeline: string;
    deals: number;
    open_deals: number;
    won_deals: number;
    lost_deals: number;
    revenue_rub: number;
  }>;
  status_breakdown?: Array<{
    status: string;
    deals: number;
    revenue_rub: number;
  }>;
  stage_funnel: Array<{
    pipeline?: string | null;
    stage: string;
    deals: number;
    revenue_rub?: number;
  }>;
  sales_cycle?: {
    avg_won_cycle_days: number;
    avg_lost_cycle_days: number;
    avg_open_age_days: number;
    stale_open_deals: number;
    stale_open_amount_rub: number;
  };
  open_age_buckets?: Array<{
    bucket: string;
    label: string;
    deals: number;
    amount_rub: number;
  }>;
  pipeline_health?: Array<{
    pipeline: string;
    deals: number;
    open_deals: number;
    won_deals: number;
    lost_deals: number;
    stale_open_deals: number;
    open_amount_rub: number;
    avg_open_age_days: number;
    oldest_open_age_days: number;
    won_rate: number;
  }>;
  manager_risk?: Array<{
    user_id: string;
    name: string;
    open_deals: number;
    stale_open_deals: number;
    open_amount_rub: number;
    avg_open_age_days: number;
    oldest_open_age_days: number;
  }>;
  manager_leaderboard?: Array<{
    user_id: string;
    name: string;
    deals: number;
    open_deals: number;
    won_deals: number;
    lost_deals: number;
    revenue_rub: number;
    avg_deal_rub?: number;
  }>;
  manager_metrics?: Array<{
    user_id: string;
    name: string;
    applications: number;
    calls: number;
    sales_count: number;
    not_sales_count: number;
    sales_amount: number;
    conversion: number;
    calls_in: number;
    calls_out: number;
    calls_duration_sec: number;
    messages_count: number;
    emails_sent: number;
    currency: string;
  }>;
  top_deals: Array<{
    id: string;
    name: string;
    status: string;
    price_rub: number;
    pipeline: string | null;
    stage: string | null;
    manager: string | null;
    created_at: string | null;
    closed_at: string | null;
  }>;
};
