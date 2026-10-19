export type DashboardFilters = {
  factory: string;
  productLine: string;
  period: "7d" | "30d" | "90d";
};

export type Dashboard = {
  cards: { label: string; value: string; change: string }[];
  trend: { month: string; rate: number }[];
  rankings?: {
    factories?: { factory?: string; rate?: number }[];
    product_lines?: { product_line?: string; rate?: number }[];
    suppliers?: { supplier_name?: string; order_count?: number; rate?: number }[];
  };
  retail?: {
    source: string;
    transaction_rows: number;
    order_count: number;
    sku_count: number;
    country_count: number;
    net_transaction_value: number;
    first_transaction_at?: string;
    last_transaction_at?: string;
    latest_30_days?: { transaction_rows?: number; net_transaction_value?: number; start_at?: string; end_at?: string };
    top_markets?: { country?: string; transaction_rows?: number; net_transaction_value?: number }[];
  } | null;
  anomalies?: { type: string; factory?: string; rate?: number; analysis_question?: string; analysis_template?: string }[];
  cache_status?: string;
  refreshed_at?: string;
  refresh_interval_seconds?: number;
  filters?: { factory?: string | null; product_line?: string | null; period?: string | null };
};
