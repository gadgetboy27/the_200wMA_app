"""
Volume + Spring enrichment for the current 200WMA signals -> web/public/enrichment.json

Two computable, Wyckoff-flavoured confirmations layered on the 200WMA signal —
NOT subjective schematic labelling:

  * Volume (effort vs result): is the move happening on above-median weekly
    volume (real demand) or thin volume (suspect)? vol_ratio = latest weekly
    volume / 50-week median volume.

  * Spring off the 200WMA: a weekly bar whose LOW dips below the 200WMA but whose
    CLOSE reclaims it — a false breakdown of long-term support. Because the
    200WMA *is* the support line here, a recent spring is a cyclical-dip entry
    with a tight, objective invalidation (the spring low).

Keeps analyse()/run_scan() (the frozen, port-verified maths) untouched — this is
a separate pass, like gen_base_rates.py. Batches the fetch so the whole signal
set costs ~2 network calls, not one-per-ticker.

Run:  python/.venv/bin/python python/gen_enrichment.py
"""
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wma200_scanner import BATCH_SIZE, HISTORY, WEEKS  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PUB = os.path.join(HERE, "..", "web", "public")
OUT = os.path.join(PUB, "enrichment.json")

LOOKBACK = 13                 # weeks to search for a recent spring (~1 quarter)
VOL_CONFIRM = 1.20            # latest vol >= 1.2x its 50-week median => demand


def signal_tickers(path: str) -> list[str]:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [s["ticker"] for s in json.load(f).get("signals", [])]


def fetch_ohlcv(tickers: list[str]) -> dict[str, pd.DataFrame]:
    import yfinance as yf
    out: dict[str, pd.DataFrame] = {}
    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i:i + BATCH_SIZE]
        data = yf.download(batch, period=HISTORY, interval="1wk",
                           auto_adjust=True, progress=False,
                           group_by="ticker", threads=True)
        for t in batch:
            try:
                df = data[t] if len(batch) > 1 else data
                if isinstance(df, pd.DataFrame) and {"Close", "Low", "Volume"} <= set(df.columns):
                    out[t] = df.dropna(subset=["Close"])
            except (KeyError, TypeError):
                continue
    return out


def enrich(df: pd.DataFrame) -> dict | None:
    close = df["Close"]
    if len(close) < WEEKS + 1:
        return None
    ma = close.rolling(WEEKS).mean()
    if pd.isna(ma.iloc[-1]):
        return None

    # --- Volume: effort vs result ---
    vol = df["Volume"].fillna(0)
    med50 = float(vol.iloc[-50:].median()) if len(vol) >= 10 else 0.0
    latest_vol = float(vol.iloc[-1])
    vol_ratio = round(latest_vol / med50, 2) if med50 > 0 else None
    vol_confirms = bool(vol_ratio is not None and vol_ratio >= VOL_CONFIRM)

    # --- Spring: weekly low pierces the MA but close reclaims it ---
    low, ma_recent = df["Low"], ma
    spring = {"happened": False, "weeks_ago": None, "depth_pct": None}
    n = len(close)
    for back in range(0, min(LOOKBACK, n)):
        idx = n - 1 - back
        m = ma_recent.iloc[idx]
        if pd.isna(m):
            continue
        lo, cl = float(low.iloc[idx]), float(close.iloc[idx])
        if lo < m and cl >= m:                     # pierced support, closed back above
            spring = {
                "happened": True,
                "weeks_ago": back,
                "depth_pct": round((lo - m) / m * 100, 2),
            }
            break                                   # most recent spring wins

    return {"vol_ratio": vol_ratio, "vol_confirms": vol_confirms, "spring": spring}


def main() -> None:
    tickers = sorted(set(
        signal_tickers(os.path.join(PUB, "wma200_signals.json"))
        + signal_tickers(os.path.join(PUB, "wma200_signals_crypto.json"))
    ))
    if not tickers:
        sys.exit("No current signals found — run the scan first.")
    print(f"Enriching {len(tickers)} signal tickers with volume + spring...")

    frames = fetch_ohlcv(tickers)
    results = {}
    springs = 0
    for t in tickers:
        df = frames.get(t)
        if df is None:
            continue
        e = enrich(df)
        if e is None:
            continue
        results[t] = e
        springs += int(e["spring"]["happened"])

    payload = {
        "generated": None,     # stamped by caller/commit; kept deterministic here
        "lookback_weeks": LOOKBACK,
        "vol_confirm_threshold": VOL_CONFIRM,
        "_note": "Volume = latest weekly volume / 50-week median. Spring = weekly "
                 "low below the 200WMA with a close back above it, within lookback.",
        "tickers": results,
    }
    with open(OUT, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"Wrote {len(results)} tickers to {os.path.abspath(OUT)} "
          f"({springs} with a recent spring off the 200WMA)")


if __name__ == "__main__":
    main()
