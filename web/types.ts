// Type definitions mirroring the JSON emitted by the Python scanner
// (python/wma200_scanner.py -> wma200_signals.json).
// Keep this in sync with the scanner's output shape.

export type SignalType =
  | "CROSSED UP"
  | "CROSSED DOWN"
  | "NEAR (above)"
  | "NEAR (below)";

export interface Chart {
  dates: string[];
  price: number[];
  // The MA series can contain nulls for the early weeks before the
  // 200-week window is fully populated.
  ma: (number | null)[];
}

export interface Signal {
  ticker: string;
  signal: SignalType;
  price: number;
  wma200: number;
  dist_pct: number;
  ma_slope_13w_pct: number;
  chart: Chart;
}

export interface Breadth {
  date: string;
  assets_with_full_ma: number;
  pct_above_200wma: number | null;
  crossed_up: number;
  crossed_down: number;
}

export interface ScanResult {
  breadth: Breadth;
  signals: Signal[];
}

export type Universe = "sp500" | "crypto";

// web/public/base_rates.json — per-ticker event-study context.
export interface BaseRate {
  touches: number;
  fwd_mean_pct: number;
  baseline_mean_pct: number;
  edge_pct: number;
  win_pct: number;
}
export interface BaseRates {
  horizon_weeks: number;
  band_pct: number;
  generated?: string;
  _caveat?: string;
  tickers: Record<string, BaseRate | null>;
}

// web/public/breadth_history.json — real historical weekly breadth.
export interface BreadthHistory {
  universe: string;
  generated?: string;
  series: { date: string; pct_above_200wma: number }[];
}

// web/public/enrichment.json — Wyckoff-flavoured volume + spring confirmation.
export interface Spring {
  happened: boolean;
  weeks_ago: number | null;
  depth_pct: number | null;
}
export interface Enrichment {
  vol_ratio: number | null; // latest weekly volume / 50-week median
  vol_confirms: boolean;
  spring: Spring;
}
export interface Enrichments {
  lookback_weeks: number;
  vol_confirm_threshold: number;
  tickers: Record<string, Enrichment | undefined>;
}

// web/public/value_timing.json — Piotroski F-score + valuation z + tranche ladder.
export interface FScoreChecks {
  roa: boolean | null;
  cfo: boolean | null;
  d_roa: boolean | null;
  accruals: boolean | null;
  d_lev: boolean | null;
  d_liq: boolean | null;
  shares: boolean | null;
  d_margin: boolean | null;
  d_turn: boolean | null;
}
export interface Valuation {
  pe_z: number | null;
  ps_z: number | null;
  pb_z: number | null;
  composite_z: number;
  weeks: number;
}
export interface LadderRung {
  price: number;
  pct_vs_ma: number;
  weight: number;
}
export interface Ladder {
  rungs: LadderRung[];
  basis: "p50/p10" | "fallback";
}
export interface ValueTimingEntry {
  f_score: number | null; // Piotroski passes (stocks only; null for crypto)
  f_max: number | null; // checks that were evaluable (financials lack some)
  checks: FScoreChecks | null;
  valuation: Valuation | null; // null when every z-guard tripped
  ladder: Ladder | null;
}
export interface ValueTiming {
  generated?: string;
  z_min_weeks: number;
  depth_years: number;
  tranche_weights: number[];
  tickers: Record<string, ValueTimingEntry | undefined>;
}
