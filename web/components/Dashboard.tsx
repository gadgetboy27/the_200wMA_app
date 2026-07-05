import Sparkline from "@/components/Sparkline";
import BreadthTrend from "@/components/BreadthTrend";
import type {
  BaseRate,
  BaseRates,
  BreadthHistory,
  ScanResult,
  Signal,
  SignalType,
  Universe,
} from "@/types";

const BADGE_CLASS: Record<SignalType, string> = {
  "CROSSED UP": "up",
  "CROSSED DOWN": "down",
  "NEAR (above)": "near",
  "NEAR (below)": "near",
};

function breadthBand(pct: number | null): string {
  if (pct === null) return "";
  if (pct >= 70) return "band-green";
  if (pct >= 50) return "band-amber";
  if (pct >= 30) return "band-amber-dark";
  return "band-red";
}

function fmt(n: number): string {
  return n.toLocaleString("en-US", { maximumFractionDigits: 2 });
}
function pct(n: number): string {
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
}

// Evidence-based read: combine the setup (13w MA slope) with the per-name
// historical base rate (does buying this level actually pay off for THIS name?)
// into a plain-language "why this is / isn't a good buy". No company name — the
// verdict is built from price behaviour and history only, on purpose.
type Verdict = "constructive" | "mixed" | "weak";
function evidence(sig: Signal, br: BaseRate | null): { verdict: Verdict; text: string } {
  const rising = sig.ma_slope_13w_pct > 0;
  const thin = br ? br.touches < 15 : false;
  const thinNote = thin ? " History here is thin — treat as weak evidence." : "";

  if (!rising) {
    // A falling 200WMA is support that tends to break.
    const hist = br
      ? ` History agrees: touches of its MA returned ${pct(br.edge_pct)} vs baseline.`
      : "";
    return {
      verdict: "weak",
      text: `MA falling (13w) — a declining 200WMA is support that usually breaks, not a floor.${hist}${thinNote}`,
    };
  }
  // Rising MA: the setup is fine — let the base rate decide the verdict.
  if (!br) {
    return {
      verdict: "mixed",
      text: `Uptrend intact (MA rising), but there's no usable 200WMA history for this name — no evidence either way. Size small.${thinNote}`,
    };
  }
  if (br.edge_pct > 2) {
    return {
      verdict: "constructive",
      text: `Uptrend intact AND buying its 200WMA has historically beaten this name's own baseline by ${pct(br.edge_pct)} (${br.win_pct.toFixed(0)}% win, ${br.touches} touches). Evidence supports a dip-buy — but survivorship + overlap flatter this.${thinNote}`,
    };
  }
  if (br.edge_pct >= -1) {
    return {
      verdict: "mixed",
      text: `Uptrend intact, but its 200WMA touches have only matched baseline (${pct(br.edge_pct)}, ${br.win_pct.toFixed(0)}% win). The line looks like support but hasn't paid as an entry here.${thinNote}`,
    };
  }
  return {
    verdict: "mixed",
    text: `Uptrend intact, yet historically its 200WMA touches UNDER-performed this name's own baseline (${pct(br.edge_pct)}). The setup looks good; the evidence says this line isn't a reliable buy trigger for it.${thinNote}`,
  };
}

// ---- Classification & ranking (slope + signal -> actionable tier) ----
type Tier = "entry" | "watch" | "caution" | "avoid";
interface Classification {
  tier: Tier;
  rank: number;
  label: string;
}
export function classify(sig: Signal): Classification {
  const slope = sig.ma_slope_13w_pct;
  const rising = slope > 0;
  const strongRising = slope > 1;
  switch (sig.signal) {
    case "CROSSED UP":
      return rising
        ? { tier: "entry", rank: 0, label: "Golden long-cycle entry" }
        : { tier: "caution", rank: 30, label: "Knife-catch cross (MA falling)" };
    case "NEAR (below)":
      if (strongRising) return { tier: "entry", rank: 5, label: "Cycle dip (MA rising strongly)" };
      return rising
        ? { tier: "watch", rank: 12, label: "Testing support (MA rising)" }
        : { tier: "avoid", rank: 40, label: "Near falling MA — support may fail" };
    case "NEAR (above)":
      return rising
        ? { tier: "watch", rank: 15, label: "Holding above rising MA" }
        : { tier: "caution", rank: 32, label: "Above a falling MA — fragile" };
    case "CROSSED DOWN":
      return rising
        ? { tier: "caution", rank: 33, label: "Shakeout (MA still rising)" }
        : { tier: "avoid", rank: 50, label: "Structural break — avoid" };
  }
}

const TIER_META: Record<Tier, { title: string; blurb: string; cls: string }> = {
  entry: {
    title: "Actionable — long-cycle entries",
    blurb: "Crossed up or dipping toward a RISING 200WMA. The cyclical-dip setups this scan exists to find.",
    cls: "sec-entry",
  },
  watch: {
    title: "Watch",
    blurb: "Sitting near a rising or flat 200WMA — not triggered yet, worth tracking week to week.",
    cls: "sec-watch",
  },
  caution: {
    title: "Caution",
    blurb: "Signal present but the MA slope undercuts it — confirm before acting.",
    cls: "sec-caution",
  },
  avoid: {
    title: "Avoid — riding the 200WMA down",
    blurb: "Touching or breaking a FALLING 200WMA. Structural decline, not support.",
    cls: "sec-avoid",
  },
};
const TIER_ORDER: Tier[] = ["entry", "watch", "caution", "avoid"];

function BaseRateRow({ br, horizon }: { br: BaseRate; horizon: number }) {
  const edgeClass = br.edge_pct >= 0 ? "pos" : "neg";
  return (
    <div className="baserate" title="Event study over this ticker's full history. Overlapping windows inflate the sample; survivorship bias applies.">
      <span className="br-label">Base rate</span>
      <span>
        {br.touches} touches · fwd {horizon}w{" "}
        <span className={br.fwd_mean_pct >= 0 ? "pos" : "neg"}>{pct(br.fwd_mean_pct)}</span>{" "}
        vs base <span className={br.baseline_mean_pct >= 0 ? "pos" : "neg"}>{pct(br.baseline_mean_pct)}</span> ·{" "}
        edge <span className={edgeClass}>{pct(br.edge_pct)}</span> · win {br.win_pct.toFixed(0)}%
      </span>
    </div>
  );
}

const VERDICT_LABEL: Record<Verdict, string> = {
  constructive: "Evidence: constructive",
  mixed: "Evidence: mixed",
  weak: "Evidence: weak",
};

function SignalCard({
  sig,
  baseRate,
  horizon,
}: {
  sig: Signal;
  baseRate: BaseRate | null;
  horizon: number;
}) {
  const ev = evidence(sig, baseRate);
  const cls = classify(sig);
  const slopeClass = sig.ma_slope_13w_pct >= 0 ? "pos" : "neg";
  const distClass = sig.dist_pct >= 0 ? "pos" : "neg";
  return (
    <div className="card">
      <div className="head">
        <span className="tick">{sig.ticker}</span>
        <span className={`badge ${BADGE_CLASS[sig.signal]}`}>{sig.signal}</span>
      </div>
      <div className={`tag tag-${cls.tier}`}>{cls.label}</div>
      <Sparkline chart={sig.chart} />
      <div className="stats">
        <div>
          <label>Price</label>
          {fmt(sig.price)}
        </div>
        <div>
          <label>200WMA</label>
          {fmt(sig.wma200)}
        </div>
        <div>
          <label>Distance</label>
          <span className={distClass}>{pct(sig.dist_pct)}</span>
        </div>
        <div>
          <label>MA slope 13w</label>
          <span className={`slope ${slopeClass}`}>{pct(sig.ma_slope_13w_pct)}</span>
        </div>
      </div>
      {baseRate && <BaseRateRow br={baseRate} horizon={horizon} />}
      <div className={`verdict v-${ev.verdict}`}>
        <span className="v-label">{VERDICT_LABEL[ev.verdict]}</span>
        {ev.text}
      </div>
    </div>
  );
}

// Aggregate answer to "are 200WMA touches a good time to buy?", computed live
// from THIS week's signals + their base rates. Splits by MA slope so the reader
// sees the qualifier's effect, not a single blended number.
function EvidencePanel({
  signals,
  baseRates,
}: {
  signals: Signal[];
  baseRates: BaseRates | null;
}) {
  if (!baseRates) return null;
  const rows = signals
    .map((s) => ({ slope: s.ma_slope_13w_pct, br: baseRates.tickers?.[s.ticker] }))
    .filter((r): r is { slope: number; br: BaseRate } => !!r.br);
  if (rows.length < 5) return null;
  const mean = (a: number[]) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0);
  const rising = rows.filter((r) => r.slope > 0);
  const falling = rows.filter((r) => r.slope <= 0);
  const posShare = Math.round((100 * rows.filter((r) => r.br.edge_pct > 0).length) / rows.length);
  const riseEdge = mean(rising.map((r) => r.br.edge_pct));
  const fallEdge = mean(falling.map((r) => r.br.edge_pct));

  return (
    <div className="evpanel">
      <div className="evpanel-h">Is a 200WMA touch a good time to buy?</div>
      <p>
        Across this week&apos;s {rows.length} signals with history, only{" "}
        <b>{posShare}%</b> have beaten their own baseline after touching the 200WMA — a touch{" "}
        <b>alone is close to a coin flip</b>. What tilts the odds is the MA slope:
      </p>
      <div className="evpanel-split">
        <div className="ev-good">
          Rising MA (n={rising.length}): mean edge <b>{pct(riseEdge)}</b>
        </div>
        <div className="ev-bad">
          Falling MA (n={falling.length}): mean edge <b>{pct(fallEdge)}</b>
        </div>
      </div>
      <p className="evpanel-foot">
        Use this as a shortlist, not a trigger. Base rates are optimistic — current-index
        survivorship and overlapping windows both inflate them. Nothing here is advice.
      </p>
    </div>
  );
}

export default function Dashboard({
  universe,
  data,
  baseRates,
  breadthHistory,
}: {
  universe: Universe;
  data: ScanResult;
  baseRates: BaseRates | null;
  breadthHistory: BreadthHistory | null;
}) {
  const { breadth, signals } = data;
  const horizon = baseRates?.horizon_weeks ?? 26;

  const ranked = [...signals].sort((a, b) => {
    const ca = classify(a);
    const cb = classify(b);
    if (ca.rank !== cb.rank) return ca.rank - cb.rank;
    return Math.abs(a.dist_pct) - Math.abs(b.dist_pct);
  });
  const byTier: Record<Tier, Signal[]> = { entry: [], watch: [], caution: [], avoid: [] };
  for (const sig of ranked) byTier[classify(sig).tier].push(sig);
  const entryCount = byTier.entry.length;
  const brFor = (t: string): BaseRate | null => baseRates?.tickers?.[t] ?? null;

  return (
    <>
      <div className="sub">
        {universe === "crypto" ? "CRYPTO MAJORS" : "S&P 500"} &nbsp;|&nbsp; {breadth.date} &nbsp;|&nbsp;{" "}
        {signals.length} signals
      </div>

      <div className="breadth">
        <div className={`tile ${breadthBand(breadth.pct_above_200wma)}`}>
          <label>% above 200WMA</label>
          <b>{breadth.pct_above_200wma === null ? "—" : `${breadth.pct_above_200wma}%`}</b>
        </div>
        <div className="tile">
          <label>Crossed up this week</label>
          <b>{breadth.crossed_up}</b>
        </div>
        <div className="tile">
          <label>Crossed down this week</label>
          <b>{breadth.crossed_down}</b>
        </div>
        <div className={`tile ${entryCount > 0 ? "band-green" : ""}`}>
          <label>Actionable entries</label>
          <b>{entryCount}</b>
        </div>
        <div className="tile">
          <label>Assets with full MA</label>
          <b>{breadth.assets_with_full_ma}</b>
        </div>
      </div>

      {breadthHistory && <BreadthTrend history={breadthHistory} />}

      <EvidencePanel signals={signals} baseRates={baseRates} />

      <div className="legend">
        <span className="px">━ price</span> &nbsp; <span className="ma">╌ 200-week MA</span> &nbsp;|&nbsp;{" "}
        sorted most-actionable first
      </div>

      {signals.length === 0 ? (
        <p>No signals in band.</p>
      ) : (
        TIER_ORDER.map((tier) => {
          const rows = byTier[tier];
          if (rows.length === 0) return null;
          const meta = TIER_META[tier];
          return (
            <section key={tier} className={`tier ${meta.cls}`}>
              <div className="tier-head">
                <h2>
                  {meta.title} <span className="tier-count">{rows.length}</span>
                </h2>
                <p className="tier-blurb">{meta.blurb}</p>
              </div>
              <div className="grid">
                {rows.map((sig) => (
                  <SignalCard key={sig.ticker} sig={sig} baseRate={brFor(sig.ticker)} horizon={horizon} />
                ))}
              </div>
            </section>
          );
        })
      )}
    </>
  );
}
