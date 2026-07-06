"""
Value Timing enrichment for the current 200WMA signals -> web/public/value_timing.json
======================================================================================
Three per-name reads layered on the 200WMA signal, all from free yfinance data:

  * Piotroski F-score (0-9): nine pass/fail financial-health checks from the
    two most recent COMMON fiscal years across the income statement, balance
    sheet and cash-flow statement. Stocks only (crypto has no statements).

  * Valuation z-scores: is today's P/E / P/S / P/B cheap or pricey vs the
    name's OWN ~4-year history? Per-share fundamentals are stepped under the
    weekly close series (split-adjusted, +90d filing lag to avoid look-ahead).
    Guards: P/E segments with EPS<=0 dropped; P/B killed if book value ever
    <=0 (buyback-heavy names like MCD run negative equity).

  * Tranche ladder: a staged buy plan scaled to how deep THIS name has
    historically traded below its 200WMA (last 10y of weekly closes).
    Rung 1 = the MA itself; rungs 2-3 = the median and deep-tail (p10) of
    below-MA depths. Price-based, so it applies to crypto too.

Keeps analyse()/run_scan() (the frozen, port-verified maths) untouched — this
is a separate pass, like gen_base_rates.py. Fundamentals are per-ticker calls
(yfinance can't batch statements), so this is the slowest generator (~1-2s per
stock); ladder prices come from one batched weekly download.

Run:  python/.venv/bin/python python/gen_value_timing.py
"""

import json
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wma200_scanner import BATCH_SIZE, WEEKS  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PUB = os.path.join(HERE, "..", "web", "public")
SP_IN = os.path.join(PUB, "wma200_signals.json")
CRYPTO_IN = os.path.join(PUB, "wma200_signals_crypto.json")
OUT = os.path.join(PUB, "value_timing.json")

# --- Valuation z-scores ---
Z_MIN_WEEKS = 40          # need this many weekly ratio points for a usable z
FILING_LAG_DAYS = 90      # annuals become "known" ~a quarter after fiscal end
# --- F-score ---
SHARE_TOL = 0.005         # <=0.5% share-count rise still passes (rounding/SBC noise)
# --- Tranche ladder ---
DEPTH_YEARS = 10          # depth stats over the last decade, not 2008-era max
MIN_DEPTH_WEEKS = 10      # fewer below-MA weeks than this -> fixed fallback rungs
DEPTH_FALLBACK = (-10.0, -20.0)
STOCK_RUNG3_CAP = -35.0   # stocks only; -60% below the 200WMA is a real BTC event
RUNG_MIN_GAP = 4.0        # % spacing floors so calm names don't stack rungs
RUNG_WEIGHTS = (25, 35, 40)
# --- Fetching ---
FUND_SLEEP = 1.0          # per-ticker pause (CI runner IPs get throttled harder)
RETRY_BACKOFF = 8         # seconds between the two statement-fetch attempts

NOTE = ("F-score = Piotroski 9-check financial health from the two most recent "
        "common fiscal years. Valuation z = today's P/E / P/S / P/B vs this "
        "name's own ~4y weekly ratio history (split-adjusted, +90d filing lag; "
        "residual dividend-adjustment drift accepted). Ladder rungs = the 200WMA "
        "and the p50/p10 of this name's last-10y weekly close depths below it. "
        "Descriptive, not advice.")


def signal_tickers(path: str) -> list[str]:
    if not os.path.exists(path):
        print(f"  (missing {os.path.basename(path)} — skipping its tickers)")
        return []
    with open(path) as f:
        d = json.load(f)
    return [s["ticker"] for s in d.get("signals", [])]


# --------------------------------------------------------------------------
# Weekly closes (batched) — feeds both the ladder and the valuation series.
# --------------------------------------------------------------------------

def fetch_weekly_closes(tickers: list[str]) -> dict[str, pd.Series]:
    import yfinance as yf
    out: dict[str, pd.Series] = {}
    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i:i + BATCH_SIZE]
        for attempt in (1, 2):
            try:
                data = yf.download(batch, period=f"{DEPTH_YEARS}y", interval="1wk",
                                   auto_adjust=True, progress=False,
                                   group_by="ticker", threads=True)
                for t in batch:
                    try:
                        s = data[t]["Close"] if len(batch) > 1 else data["Close"]
                        if isinstance(s, pd.DataFrame):
                            s = s.squeeze()
                        out[t] = s.dropna()
                    except (KeyError, TypeError):
                        continue
                time.sleep(1)
                break
            except Exception as e:                      # noqa: BLE001
                print(f"    price batch attempt {attempt} failed: {e}")
                if attempt == 1:
                    time.sleep(RETRY_BACKOFF)
    return out


# --------------------------------------------------------------------------
# Tranche ladder — volatility-scaled buy rungs below the 200WMA.
# --------------------------------------------------------------------------

def build_ladder(close: pd.Series, is_crypto: bool) -> dict | None:
    if len(close) < WEEKS + 1:
        return None
    ma = close.rolling(WEEKS).mean()
    ma_now = float(ma.iloc[-1])
    if pd.isna(ma_now) or ma_now <= 0:
        return None

    below = (close - ma) / ma
    depths = below[ma.notna() & (below < 0)].to_numpy() * 100.0

    if len(depths) >= MIN_DEPTH_WEEKS:
        # Depths are NEGATIVE — the deep tail is the LOW percentile.
        d2 = float(np.percentile(depths, 50))
        d3 = float(np.percentile(depths, 10))
        basis = "p50/p10"
    else:
        d2, d3 = DEPTH_FALLBACK
        basis = "fallback"

    # Spacing floors, then the stock-only deep cap; keep the ladder monotonic.
    d2 = min(d2, -RUNG_MIN_GAP)
    d3 = min(d3, d2 - RUNG_MIN_GAP)
    if not is_crypto:
        d3 = max(d3, STOCK_RUNG3_CAP)
        d2 = max(d2, d3 + RUNG_MIN_GAP)

    rungs = []
    for pct, weight in zip((0.0, d2, d3), RUNG_WEIGHTS):
        rungs.append({
            "price": round(ma_now * (1 + pct / 100.0), 2),
            "pct_vs_ma": round(pct, 1),
            "weight": weight,
        })
    return {"rungs": rungs, "basis": basis}


# --------------------------------------------------------------------------
# Fundamentals — statements aligned on common fiscal dates.
# --------------------------------------------------------------------------

def _row(df: pd.DataFrame, label: str, date) -> float | None:
    try:
        v = df.at[label, date]
    except KeyError:
        return None
    return None if pd.isna(v) else float(v)


def common_fiscal_dates(inc: pd.DataFrame, bal: pd.DataFrame,
                        cfs: pd.DataFrame) -> list:
    """Column counts differ per statement — align by date, never position."""
    dates = set(inc.columns) & set(bal.columns) & set(cfs.columns)
    return sorted(dates, reverse=True)


def f_score(inc: pd.DataFrame, bal: pd.DataFrame, cfs: pd.DataFrame,
            dates: list) -> dict | None:
    if len(dates) < 2:
        return None
    t, p = dates[0], dates[1]

    ni = _row(inc, "Net Income", t)
    ni_p = _row(inc, "Net Income", p)
    rev = _row(inc, "Total Revenue", t)
    rev_p = _row(inc, "Total Revenue", p)
    gp = _row(inc, "Gross Profit", t)
    gp_p = _row(inc, "Gross Profit", p)
    ta = _row(bal, "Total Assets", t)
    ta_p = _row(bal, "Total Assets", p)
    ca = _row(bal, "Current Assets", t)
    ca_p = _row(bal, "Current Assets", p)
    cl = _row(bal, "Current Liabilities", t)
    cl_p = _row(bal, "Current Liabilities", p)
    ocf = _row(cfs, "Operating Cash Flow", t)
    # Debt-free names report no LTD row — that's 0 debt, a pass, not a skip.
    ltd = _row(bal, "Long Term Debt", t) or 0.0
    ltd_p = _row(bal, "Long Term Debt", p) or 0.0
    sh = _row(bal, "Ordinary Shares Number", t)
    sh_p = _row(bal, "Ordinary Shares Number", p)
    if sh is None or sh_p is None:                       # fallback per plan
        sh = _row(inc, "Basic Average Shares", t)
        sh_p = _row(inc, "Basic Average Shares", p)

    checks: dict[str, bool | None] = {
        "roa": (ni / ta > 0) if ni is not None and ta else None,
        "cfo": (ocf > 0) if ocf is not None else None,
        "d_roa": (ni / ta > ni_p / ta_p)
                 if None not in (ni, ni_p) and ta and ta_p else None,
        "accruals": (ocf > ni) if None not in (ocf, ni) else None,
        "d_lev": (ltd / ta <= ltd_p / ta_p) if ta and ta_p else None,
        "d_liq": (ca / cl > ca_p / cl_p)
                 if None not in (ca, ca_p) and cl and cl_p else None,
        "shares": (sh <= sh_p * (1 + SHARE_TOL))
                  if None not in (sh, sh_p) else None,
        "d_margin": (gp / rev > gp_p / rev_p)
                    if None not in (gp, gp_p) and rev and rev_p else None,
        "d_turn": (rev / ta > rev_p / ta_p)
                  if None not in (rev, rev_p) and ta and ta_p else None,
    }
    evaluable = [v for v in checks.values() if v is not None]
    if not evaluable:
        return None
    return {
        "f_score": int(sum(evaluable)),
        "f_max": len(evaluable),
        "checks": checks,
    }


def per_share_history(inc: pd.DataFrame, bal: pd.DataFrame, dates: list,
                      splits: pd.Series) -> list[dict]:
    """Per fiscal year: EPS / RevPS / BVPS, adjusted onto the (split-adjusted)
    price basis by the cumulative split factor from that date to now."""
    out = []
    for d in dates:
        sh = _row(bal, "Ordinary Shares Number", d)
        if not sh:
            continue
        factor = 1.0
        if splits is not None and len(splits):
            after = splits[splits.index > pd.Timestamp(d, tz=splits.index.tz)]
            if len(after):
                factor = float(after.prod())
        ni, rev, eq = (_row(inc, "Net Income", d),
                       _row(inc, "Total Revenue", d),
                       _row(bal, "Stockholders Equity", d))
        out.append({
            "known_from": pd.Timestamp(d) + pd.Timedelta(days=FILING_LAG_DAYS),
            "eps": ni / sh / factor if ni is not None else None,
            "rps": rev / sh / factor if rev is not None else None,
            "bps": eq / sh / factor if eq is not None else None,
        })
    return sorted(out, key=lambda r: r["known_from"])


def valuation_z(close: pd.Series, years: list[dict]) -> dict | None:
    if not years or close.empty:
        return None
    idx = close.index.tz_localize(None) if close.index.tz else close.index
    px = pd.Series(close.to_numpy(), index=idx)

    def ratio_series(key: str, positive_only: bool) -> pd.Series:
        parts = []
        for i, y in enumerate(years):
            v = y[key]
            if v is None or v == 0 or (positive_only and v <= 0):
                continue
            start = y["known_from"].tz_localize(None) if y["known_from"].tz else y["known_from"]
            end = None
            if i + 1 < len(years):
                nxt = years[i + 1]["known_from"]
                end = nxt.tz_localize(None) if nxt.tz else nxt
            seg = px[px.index >= start]
            if end is not None:
                seg = seg[seg.index < end]
            parts.append(seg / v)
        return pd.concat(parts) if parts else pd.Series(dtype=float)

    def z_of(key: str, positive_only: bool) -> float | None:
        # P/B is killed entirely if book value ever goes <=0 (negative-equity
        # names like MCD make the ratio meaningless, not just that segment).
        if positive_only and key == "bps" and any(
                y["bps"] is not None and y["bps"] <= 0 for y in years):
            return None
        s = ratio_series(key, positive_only)
        if len(s) < Z_MIN_WEEKS:
            return None
        std = float(s.std())
        if not std:
            return None
        return round((float(s.iloc[-1]) - float(s.mean())) / std, 2)

    pe = z_of("eps", True)
    ps = z_of("rps", True)
    pb = z_of("bps", True)
    zs = [z for z in (pe, ps, pb) if z is not None]
    if not zs:
        return None
    weeks = max(len(ratio_series(k, True))
                for k in ("eps", "rps", "bps"))
    return {
        "pe_z": pe, "ps_z": ps, "pb_z": pb,
        "composite_z": round(float(np.median(zs)), 2),
        "weeks": int(weeks),
    }


def fetch_fundamentals(ticker: str):
    """(income, balance, cashflow, splits) or None for crypto/no-statement names."""
    import yfinance as yf
    for attempt in (1, 2):
        try:
            tk = yf.Ticker(ticker)
            inc = tk.income_stmt
            if inc is None or inc.empty:               # crypto / ETF guard
                return None
            bal, cfs = tk.balance_sheet, tk.cash_flow
            if bal is None or bal.empty or cfs is None or cfs.empty:
                return None
            try:
                splits = tk.splits
            except Exception:                           # noqa: BLE001
                splits = None
            return inc, bal, cfs, splits
        except Exception as e:                          # noqa: BLE001
            print(f"    {ticker} statements attempt {attempt} failed: {e}")
            if attempt == 1:
                time.sleep(RETRY_BACKOFF)
    return None


# --------------------------------------------------------------------------

def main() -> None:
    sp = signal_tickers(SP_IN)
    cr = signal_tickers(CRYPTO_IN)
    crypto = set(cr)
    tickers = list(dict.fromkeys(sp + cr))
    print(f"S&P signals: {len(sp)}, crypto signals: {len(cr)}, "
          f"union: {len(tickers)} tickers")
    if not tickers:
        sys.exit("No current signals found in either file — aborting.")

    print("Fetching weekly closes (batched)...")
    closes = fetch_weekly_closes(tickers)

    results: dict[str, dict] = {}
    skipped: list[str] = []
    for n, t in enumerate(tickers, 1):
        close = closes.get(t)
        ladder = build_ladder(close, t in crypto) if close is not None else None
        entry: dict = {"f_score": None, "f_max": None, "checks": None,
                       "valuation": None, "ladder": ladder}

        if t not in crypto:
            print(f"  [{n}/{len(tickers)}] {t} fundamentals...")
            fund = fetch_fundamentals(t)
            if fund is not None:
                inc, bal, cfs, splits = fund
                dates = common_fiscal_dates(inc, bal, cfs)
                fs = f_score(inc, bal, cfs, dates)
                if fs is not None:
                    entry.update(fs)
                if close is not None:
                    years = per_share_history(inc, bal, dates, splits)
                    entry["valuation"] = valuation_z(close, years)
            time.sleep(FUND_SLEEP)

        if entry["ladder"] is None and entry["f_score"] is None:
            skipped.append(f"{t} (no data)")
            continue
        results[t] = entry

    payload = {
        "generated": pd.Timestamp.today().strftime("%Y-%m-%d"),
        "z_min_weeks": Z_MIN_WEEKS,
        "depth_years": DEPTH_YEARS,
        "tranche_weights": list(RUNG_WEIGHTS),
        "_note": NOTE,
        "tickers": results,
    }
    with open(OUT, "w") as f:
        json.dump(payload, f, indent=2)

    scored = sum(1 for r in results.values() if r["f_score"] is not None)
    valued = sum(1 for r in results.values() if r["valuation"] is not None)
    print(f"\nWrote {len(results)} tickers to {os.path.abspath(OUT)} "
          f"({scored} with F-scores, {valued} with valuation z)")
    if skipped:
        print(f"Skipped {len(skipped)}: {', '.join(skipped)}")
    for t, r in list(results.items())[:5]:
        v = r["valuation"]
        l3 = r["ladder"]["rungs"][2]["pct_vs_ma"] if r["ladder"] else None
        print(f"  {t}: F={r['f_score']}/{r['f_max']} "
              f"z={v['composite_z'] if v else None} rung3={l3}%")


if __name__ == "__main__":
    main()
