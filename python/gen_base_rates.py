"""
Per-name 200WMA base rates (event study)  ->  web/public/base_rates.json
========================================================================
For every ticker that currently shows a signal in EITHER
web/public/wma200_signals.json (S&P 500) or
web/public/wma200_signals_crypto.json (crypto), runs the same event study as
wma200_scanner.backtest(): over the ticker's FULL weekly history find weeks
within ±5% of the 200WMA ("touches"), then compare the mean forward 26-week
return after those touches against the baseline mean 26-week return over all
weeks with a formed MA. Edge = touch mean − baseline mean.

The forward-return / touch maths below mirrors backtest() exactly (that
function only prints, so its numbers can't be captured — the formulas are
reproduced, not the analyse() maths, which is left untouched).

Run:  python/.venv/bin/python python/gen_base_rates.py
"""

import json
import os
import sys
import time

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wma200_scanner import WEEKS  # noqa: E402  reuse the engine's constant

HORIZON = 26
BAND_PCT = 5.0
FETCH_BATCH = 15
HERE = os.path.dirname(os.path.abspath(__file__))
PUB = os.path.join(HERE, "..", "web", "public")
SP_IN = os.path.join(PUB, "wma200_signals.json")
CRYPTO_IN = os.path.join(PUB, "wma200_signals_crypto.json")
OUT = os.path.join(PUB, "base_rates.json")

CAVEAT = ("Overlapping 26-week forward windows inflate the effective sample "
          "size; current-index / current-signal constituents carry "
          "survivorship bias. Treat these as descriptive base rates, not "
          "guarantees.")


def signal_tickers(path: str) -> list[str]:
    if not os.path.exists(path):
        print(f"  (missing {os.path.basename(path)} — skipping its tickers)")
        return []
    with open(path) as f:
        d = json.load(f)
    return [s["ticker"] for s in d.get("signals", [])]


def fetch_batch(batch: list[str]) -> dict[str, pd.Series]:
    """Full-history weekly closes for a batch; retry once, skip on failure."""
    import yfinance as yf
    for attempt in (1, 2):
        try:
            data = yf.download(batch, period="max", interval="1wk",
                               auto_adjust=True, progress=False,
                               group_by="ticker", threads=True)
            out: dict[str, pd.Series] = {}
            for t in batch:
                try:
                    s = data[t]["Close"] if len(batch) > 1 else data["Close"]
                    if isinstance(s, pd.DataFrame):
                        s = s.squeeze()
                    out[t] = s
                except (KeyError, TypeError):
                    continue
            time.sleep(1)
            return out
        except Exception as e:                          # noqa: BLE001
            print(f"    batch attempt {attempt} failed: {e}")
            if attempt == 2:
                return {}
    return {}


def study(s: pd.Series) -> dict | None:
    """Event study mirroring backtest() for a single weekly close series."""
    s = s.dropna()
    if len(s) < WEEKS + HORIZON + 10:
        return None
    ma = s.rolling(WEEKS).mean()
    dist = (s - ma) / ma
    touch = dist.abs() <= BAND_PCT / 100.0
    fwd = s.shift(-HORIZON) / s - 1
    sig = fwd[touch & fwd.notna()]
    base = fwd[ma.notna() & fwd.notna()]
    if len(sig) == 0 or len(base) == 0:
        return None
    fwd_mean = sig.mean() * 100
    baseline = base.mean() * 100
    return {
        "touches": int(len(sig)),
        "fwd_mean_pct": round(float(fwd_mean), 1),
        "baseline_mean_pct": round(float(baseline), 1),
        "edge_pct": round(float(fwd_mean - baseline), 1),
        "win_pct": round(float((sig > 0).mean() * 100), 1),
    }


def main() -> None:
    sp = signal_tickers(SP_IN)
    cr = signal_tickers(CRYPTO_IN)
    # union across BOTH current-signal files, de-duped, stable order
    tickers = list(dict.fromkeys(sp + cr))
    print(f"S&P signals: {len(sp)}, crypto signals: {len(cr)}, "
          f"union: {len(tickers)} tickers")
    if not tickers:
        sys.exit("No current signals found in either file — aborting.")

    results: dict[str, dict] = {}
    skipped: list[str] = []
    for i in range(0, len(tickers), FETCH_BATCH):
        batch = tickers[i:i + FETCH_BATCH]
        print(f"  fetching {i + 1}-{i + len(batch)} of {len(tickers)}...")
        series = fetch_batch(batch)
        for t in batch:
            s = series.get(t)
            if s is None or (isinstance(s, pd.Series) and s.dropna().empty):
                skipped.append(f"{t} (no data)")
                continue
            r = study(s)
            if r is None:
                skipped.append(f"{t} (too little history for 26w window)")
                continue
            results[t] = r

    payload = {
        "horizon_weeks": HORIZON,
        "band_pct": BAND_PCT,
        "generated": pd.Timestamp.today().strftime("%Y-%m-%d"),
        "_caveat": CAVEAT,
        "tickers": results,
    }
    with open(OUT, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"\nWrote {len(results)} tickers to {os.path.abspath(OUT)}")
    if skipped:
        print(f"Skipped {len(skipped)}: {', '.join(skipped)}")
    # small readable summary
    for t, r in list(results.items())[:5]:
        print(f"  {t}: touches={r['touches']} fwd={r['fwd_mean_pct']}% "
              f"base={r['baseline_mean_pct']}% edge={r['edge_pct']}% "
              f"win={r['win_pct']}%")


if __name__ == "__main__":
    main()
