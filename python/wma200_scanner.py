"""
200-Week Moving Average Scanner v2 — Stocks + Crypto
=====================================================
Scans a universe (S&P 500, crypto majors, or custom tickers) for assets
that crossed — or sit near — their 200-week moving average, then writes:

  1. Console table
  2. wma200_signals.csv  +  wma200_signals.json   (StockMind ingestion)
  3. wma200_report.html  — self-contained visual report (open in browser)

Requirements:
    pip install yfinance pandas lxml

Usage:
    python wma200_scanner.py                          # S&P 500, ±10% band
    python wma200_scanner.py --universe crypto        # crypto majors
    python wma200_scanner.py --universe custom --tickers AAPL MSFT BTC-USD
    python wma200_scanner.py --band 5                 # tighter band
    python wma200_scanner.py --backtest BTC-USD       # event-study backtest
    python wma200_scanner.py --selftest               # offline pipeline proof

Data: Yahoo Finance via yfinance (free, no key). 200 weeks ~= 3.85 years.
"""

import argparse
import json
import sys
import time
from datetime import date

import pandas as pd

WEEKS = 200
HISTORY = "7y"                # full MA + ~1.5y of context for charts
BATCH_SIZE = 50
CHART_WEEKS = 260             # weeks shown in each report chart

CRYPTO_UNIVERSE = [
    "BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", "XRP-USD", "ADA-USD",
    "DOGE-USD", "AVAX-USD", "LINK-USD", "DOT-USD", "LTC-USD", "BCH-USD",
    "XLM-USD", "TRX-USD", "POL-USD",
]
# Note: coins listed after ~2022 won't have 200 weekly bars yet and are
# skipped automatically. Crypto trades 7d/week — weekly bars still apply.


# ----------------------------------------------------------------------
# Universe helpers
# ----------------------------------------------------------------------
def get_sp500_tickers() -> list[str]:
    # Wikipedia 403s requests without a browser User-Agent, so fetch the page
    # ourselves with a UA header and hand the HTML to pandas.
    import io
    import urllib.request
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (compatible; wma200-scanner/2.0)"})
    html = urllib.request.urlopen(req, timeout=30).read().decode()
    table = pd.read_html(io.StringIO(html))[0]
    return table["Symbol"].str.replace(".", "-", regex=False).tolist()


def get_universe(name: str, custom: list[str] | None) -> tuple[list[str], float]:
    """Returns (tickers, default_min_price)."""
    if name == "sp500":
        return get_sp500_tickers(), 1.00      # your $1 floor for stocks
    if name == "crypto":
        return CRYPTO_UNIVERSE, 0.0           # DOGE et al. trade under $1
    if name == "custom":
        if not custom:
            sys.exit("--universe custom requires --tickers ...")
        return [t.upper() for t in custom], 0.0
    sys.exit(f"Unknown universe: {name}")


# ----------------------------------------------------------------------
# Core analysis (pure function -> unit-testable offline)
# ----------------------------------------------------------------------
def analyse(weekly_close: pd.Series, band_pct: float,
            min_price: float) -> dict | None:
    """Compute 200WMA status for one weekly close series."""
    s = weekly_close.dropna()
    if len(s) < WEEKS + 14:                   # MA + slope lookback
        return None

    ma = s.rolling(WEEKS).mean()
    price_now, price_prev = float(s.iloc[-1]), float(s.iloc[-2])
    ma_now, ma_prev = float(ma.iloc[-1]), float(ma.iloc[-2])

    if price_now < min_price or pd.isna(ma_now):
        return None

    dist = (price_now - ma_now) / ma_now
    crossed_up = price_prev <= ma_prev and price_now > ma_now
    crossed_down = price_prev >= ma_prev and price_now < ma_now
    near = abs(dist) <= band_pct / 100.0

    if not (crossed_up or crossed_down or near):
        return {"above": price_now > ma_now}  # breadth only, no signal

    signal = ("CROSSED UP" if crossed_up else
              "CROSSED DOWN" if crossed_down else
              "NEAR (above)" if dist >= 0 else "NEAR (below)")

    slope_13w = (ma.iloc[-1] / ma.iloc[-14] - 1) * 100
    tail_p = s.iloc[-CHART_WEEKS:]
    tail_m = ma.iloc[-CHART_WEEKS:]

    return {
        "above": price_now > ma_now,
        "signal": signal,
        "price": round(price_now, 4),
        "wma200": round(ma_now, 4),
        "dist_pct": round(dist * 100, 2),
        "ma_slope_13w_pct": round(float(slope_13w), 2),
        "chart": {
            "dates": [d.strftime("%Y-%m-%d") for d in tail_p.index],
            "price": [round(float(v), 4) for v in tail_p],
            "ma": [None if pd.isna(v) else round(float(v), 4) for v in tail_m],
        },
    }


def run_scan(tickers: list[str], band_pct: float, min_price: float,
             fetch_fn) -> tuple[list[dict], dict]:
    """fetch_fn(batch) -> {ticker: weekly close Series}. Injected so the
    pipeline runs identically on live yfinance data or offline test data."""
    signals, above, total = [], 0, 0
    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i:i + BATCH_SIZE]
        series_map = fetch_fn(batch)
        for t, closes in series_map.items():
            res = analyse(closes, band_pct, min_price)
            if res is None:
                continue
            total += 1
            above += int(res["above"])
            if "signal" in res:
                signals.append({"ticker": t, **{k: v for k, v in res.items()
                                                if k != "above"}})
    breadth = {
        "date": date.today().isoformat(),
        "assets_with_full_ma": total,
        "pct_above_200wma": round(100 * above / total, 1) if total else None,
        "crossed_up": sum(s["signal"] == "CROSSED UP" for s in signals),
        "crossed_down": sum(s["signal"] == "CROSSED DOWN" for s in signals),
    }
    order = {"CROSSED UP": 0, "CROSSED DOWN": 1,
             "NEAR (below)": 2, "NEAR (above)": 3}
    signals.sort(key=lambda r: (order[r["signal"]], abs(r["dist_pct"])))
    return signals, breadth


# ----------------------------------------------------------------------
# Live data fetcher (yfinance)
# ----------------------------------------------------------------------
def yfinance_fetcher(batch: list[str]) -> dict[str, pd.Series]:
    import yfinance as yf
    data = yf.download(batch, period=HISTORY, interval="1wk",
                       auto_adjust=True, progress=False,
                       group_by="ticker", threads=True)
    out = {}
    for t in batch:
        try:
            s = data[t]["Close"] if len(batch) > 1 else data["Close"]
            if isinstance(s, pd.DataFrame):
                s = s.squeeze()
            out[t] = s
        except (KeyError, TypeError):
            continue
    time.sleep(1)  # be polite to Yahoo between batches
    return out


# ----------------------------------------------------------------------
# HTML report (self-contained, inline SVG — no CDN, works offline)
# ----------------------------------------------------------------------
def svg_chart(chart: dict, width=560, height=150) -> str:
    prices = chart["price"]
    mas = [m for m in chart["ma"] if m is not None]
    if not prices or not mas:
        return ""
    lo = min(min(prices), min(mas)) * 0.98
    hi = max(max(prices), max(mas)) * 1.02
    span = (hi - lo) or 1.0
    n = len(prices)

    def pts(vals):
        out = []
        for i, v in enumerate(vals):
            if v is None:
                continue
            x = i / (n - 1) * width
            y = height - (v - lo) / span * height
            out.append(f"{x:.1f},{y:.1f}")
        return " ".join(out)

    return (f'<svg viewBox="0 0 {width} {height}" '
            f'preserveAspectRatio="none" class="chart">'
            f'<polyline points="{pts(chart["ma"])}" class="ma"/>'
            f'<polyline points="{pts(prices)}" class="px"/></svg>')


BADGE = {"CROSSED UP": "up", "CROSSED DOWN": "down",
         "NEAR (above)": "near", "NEAR (below)": "near"}


def write_report(signals: list[dict], breadth: dict, universe: str,
                 band_pct: float, path: str, note: str = "") -> None:
    cards = []
    for s in signals:
        cards.append(f"""
    <div class="card">
      <div class="head">
        <span class="tick">{s['ticker']}</span>
        <span class="badge {BADGE[s['signal']]}">{s['signal']}</span>
      </div>
      {svg_chart(s['chart'])}
      <div class="stats">
        <div><label>Price</label>{s['price']:,}</div>
        <div><label>200WMA</label>{s['wma200']:,}</div>
        <div><label>Distance</label><span class="{ 'pos' if s['dist_pct']>=0 else 'neg'}">{s['dist_pct']:+.2f}%</span></div>
        <div><label>MA slope 13w</label><span class="{ 'pos' if s['ma_slope_13w_pct']>=0 else 'neg'}">{s['ma_slope_13w_pct']:+.2f}%</span></div>
      </div>
    </div>""")

    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>200WMA Scan — {universe}</title>
<style>
  body {{ background:#0b0f14; color:#d7dde4; font:14px/1.5 'SF Mono',Menlo,Consolas,monospace; margin:0; padding:32px; }}
  h1 {{ font-size:18px; letter-spacing:2px; color:#7fd4a8; margin:0 0 4px; }}
  .sub {{ color:#5c6a78; margin-bottom:24px; }}
  .note {{ background:#2a1f0a; color:#e8b45a; border:1px solid #6b4e1a; padding:8px 14px; border-radius:6px; display:inline-block; margin-bottom:20px; }}
  .breadth {{ display:flex; gap:16px; margin-bottom:28px; flex-wrap:wrap; }}
  .tile {{ background:#121924; border:1px solid #1f2b3a; border-radius:8px; padding:14px 20px; }}
  .tile b {{ display:block; font-size:22px; color:#e8eef4; }}
  .tile label {{ color:#5c6a78; font-size:11px; text-transform:uppercase; letter-spacing:1px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(400px,1fr)); gap:18px; }}
  .card {{ background:#121924; border:1px solid #1f2b3a; border-radius:8px; padding:16px; }}
  .head {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; }}
  .tick {{ font-size:17px; font-weight:700; color:#e8eef4; }}
  .badge {{ font-size:11px; padding:3px 10px; border-radius:20px; letter-spacing:1px; }}
  .badge.up {{ background:#0d2b1c; color:#4fd08a; border:1px solid #1e5c3c; }}
  .badge.down {{ background:#2d1216; color:#f06a6a; border:1px solid #6b2430; }}
  .badge.near {{ background:#2a2410; color:#e8c45a; border:1px solid #6b5a1a; }}
  .chart {{ width:100%; height:150px; display:block; margin-bottom:10px; }}
  .chart .px {{ fill:none; stroke:#4fa8f0; stroke-width:1.6; }}
  .chart .ma {{ fill:none; stroke:#e8c45a; stroke-width:1.4; stroke-dasharray:5 4; }}
  .stats {{ display:grid; grid-template-columns:repeat(4,1fr); gap:8px; }}
  .stats label {{ display:block; color:#5c6a78; font-size:10px; text-transform:uppercase; letter-spacing:1px; }}
  .pos {{ color:#4fd08a; }} .neg {{ color:#f06a6a; }}
  .legend {{ color:#5c6a78; font-size:12px; margin-bottom:20px; }}
  .legend .px {{ color:#4fa8f0; }} .legend .ma {{ color:#e8c45a; }}
</style></head><body>
<h1>200-WEEK MA SCAN</h1>
<div class="sub">{universe.upper()} &nbsp;|&nbsp; band ±{band_pct}% &nbsp;|&nbsp; {breadth['date']}</div>
{f'<div class="note">{note}</div>' if note else ''}
<div class="breadth">
  <div class="tile"><label>% above 200WMA</label><b>{breadth['pct_above_200wma']}%</b></div>
  <div class="tile"><label>Crossed up this week</label><b>{breadth['crossed_up']}</b></div>
  <div class="tile"><label>Crossed down this week</label><b>{breadth['crossed_down']}</b></div>
  <div class="tile"><label>Signals in band</label><b>{len(signals)}</b></div>
  <div class="tile"><label>Assets with full MA</label><b>{breadth['assets_with_full_ma']}</b></div>
</div>
<div class="legend"><span class="px">━ price</span> &nbsp; <span class="ma">╌ 200-week MA</span> &nbsp; (last {CHART_WEEKS} weeks)</div>
<div class="grid">{''.join(cards) if cards else '<p>No signals in band.</p>'}</div>
</body></html>"""
    with open(path, "w") as f:
        f.write(html)


# ----------------------------------------------------------------------
# Backtest — event study vs baseline
# ----------------------------------------------------------------------
def backtest(ticker: str, band_pct: float = 5.0, horizons=(13, 26, 52)):
    import yfinance as yf
    s = yf.download(ticker, period="max", interval="1wk",
                    auto_adjust=True, progress=False)["Close"].dropna()
    if isinstance(s, pd.DataFrame):
        s = s.squeeze()
    if len(s) < WEEKS + max(horizons) + 10:
        print("Not enough history for a meaningful backtest.")
        return
    ma = s.rolling(WEEKS).mean()
    dist = (s - ma) / ma
    touch = dist.abs() <= band_pct / 100.0
    print(f"\n{ticker}: {int(touch.sum())} weeks within ±{band_pct}% of "
          f"200WMA, of {int(ma.notna().sum())} weeks with a formed MA\n")
    hdr = f"{'Horizon':>8} | {'Signal mean':>11} | {'Signal win%':>11} | " \
          f"{'Baseline mean':>13} | {'Edge':>7}"
    print(hdr + "\n" + "-" * len(hdr))
    for h in horizons:
        fwd = s.shift(-h) / s - 1
        sig, base = fwd[touch & fwd.notna()], fwd[ma.notna() & fwd.notna()]
        if len(sig):
            print(f"{h:>6}w  | {sig.mean():>10.1%} | {(sig>0).mean():>10.1%} |"
                  f" {base.mean():>12.1%} | {sig.mean()-base.mean():>+6.1%}")
    print("\nCaveats: overlapping windows inflate the sample; current-index "
          "constituents carry survivorship bias.")


# ----------------------------------------------------------------------
# Offline self-test: proves the whole pipeline without network access
# ----------------------------------------------------------------------
def selftest():
    import numpy as np
    rng = np.random.default_rng(42)
    idx = pd.date_range(end="2026-07-03", periods=320, freq="W-FRI")

    def gbm(start, drift, vol):
        r = rng.normal(drift, vol, len(idx))
        return pd.Series(start * np.exp(np.cumsum(r)), index=idx)

    # TEST-DOWN: uptrend whose final week breaks below the MA
    down = gbm(50, 0.004, 0.03)
    ma_d = down.rolling(WEEKS).mean().iloc[-1]
    down.iloc[-2], down.iloc[-1] = ma_d * 1.04, ma_d * 0.93
    # TEST-UP: long base whose final week pops above the MA
    up = gbm(100, 0.0005, 0.02)
    ma_u = up.rolling(WEEKS).mean().iloc[-1]
    up.iloc[-2], up.iloc[-1] = ma_u * 0.97, ma_u * 1.06
    # TEST-NEAR: drifts to sit just above its MA
    near = gbm(30, 0.001, 0.015)
    ma_ref = near.rolling(WEEKS).mean().iloc[-1]
    near.iloc[-1] = ma_ref * 1.03
    # TEST-FAR: way above its MA -> breadth only, no signal
    far = gbm(20, 0.006, 0.02)

    series = {"TEST-DOWN": down, "TEST-UP": up,
              "TEST-NEAR": near, "TEST-FAR": far}
    signals, breadth = run_scan(list(series), band_pct=10.0, min_price=0.0,
                                fetch_fn=lambda b: {t: series[t] for t in b})

    got = {s["ticker"]: s["signal"] for s in signals}
    assert got.get("TEST-DOWN") == "CROSSED DOWN", got
    assert got.get("TEST-UP") == "CROSSED UP", got
    assert got.get("TEST-NEAR") == "NEAR (above)", got
    assert "TEST-FAR" not in got, got
    assert breadth["assets_with_full_ma"] == 4

    write_report(signals, breadth, "selftest", 10.0,
                 "wma200_report.html",
                 note="SELF-TEST / SYNTHETIC DATA — run without --selftest "
                      "for live Yahoo Finance data")
    print("Self-test PASSED: cross-up, cross-down, near-band and breadth "
          "all detected correctly.")
    print("Demo report written to wma200_report.html")


# ----------------------------------------------------------------------
if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--universe", default="sp500",
                   choices=["sp500", "crypto", "custom"])
    p.add_argument("--tickers", nargs="*", default=None)
    p.add_argument("--band", type=float, default=10.0)
    p.add_argument("--min-price", type=float, default=None)
    p.add_argument("--backtest", type=str, default=None)
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args()

    if args.selftest:
        selftest()
        sys.exit(0)
    if args.backtest:
        backtest(args.backtest.upper(), band_pct=min(args.band, 5.0))
        sys.exit(0)

    tickers, default_min = get_universe(args.universe, args.tickers)
    min_price = default_min if args.min_price is None else args.min_price
    print(f"Scanning {len(tickers)} tickers ({args.universe}), "
          f"band ±{args.band}%, min price ${min_price}\n")

    signals, breadth = run_scan(tickers, args.band, min_price,
                                yfinance_fetcher)

    if signals:
        df = pd.DataFrame([{k: v for k, v in s.items() if k != "chart"}
                           for s in signals])
        print(df.to_string(index=False))
        df.to_csv("wma200_signals.csv", index=False)
    with open("wma200_signals.json", "w") as f:
        json.dump({"breadth": breadth, "signals": signals}, f, indent=2)
    write_report(signals, breadth, args.universe, args.band,
                 "wma200_report.html")
    print(f"\nBreadth: {breadth['pct_above_200wma']}% above 200WMA | "
          f"{breadth['crossed_up']} up-crosses, "
          f"{breadth['crossed_down']} down-crosses")
    print("Wrote wma200_signals.csv, wma200_signals.json, "
          "wma200_report.html")
