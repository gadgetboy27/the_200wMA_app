"""
Historical S&P 500 breadth vs 200-week MA  ->  web/public/breadth_history.json
==============================================================================
For each of the trailing ~156 weeks (3 years) computes the % of S&P 500
constituents whose weekly close sat ABOVE their 200-week MA *as of that week*,
counting only names that had a fully-formed 200WMA that week (mirrors the
"assets_with_full_ma" denominator rule in wma200_scanner.analyse: formed MA
plus the $1 stock price floor).

Fetches once at ~7y / 1wk so every reported week has 200 prior weekly bars.
This is the run-once / run-occasionally job. The weekly cron only APPENDS the
newest point (see scripts/weekly_scan.sh); it does not regenerate history.

Run:  python/.venv/bin/python python/gen_breadth_history.py
"""

import json
import os
import sys
from datetime import date

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wma200_scanner import (  # noqa: E402  reuse the engine, don't reimplement
    BATCH_SIZE,
    WEEKS,
    get_sp500_tickers,
    yfinance_fetcher,
)

MIN_PRICE = 1.00        # same $1 stock floor the sp500 universe uses
LOOKBACK_WEEKS = 156    # ~3 years of reported breadth points
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "..", "web", "public", "breadth_history.json")


def fetch_all(tickers: list[str]) -> dict[str, pd.Series]:
    """Batch-fetch weekly closes, retry a failed batch once, skip on failure."""
    series: dict[str, pd.Series] = {}
    n_batches = (len(tickers) + BATCH_SIZE - 1) // BATCH_SIZE
    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i:i + BATCH_SIZE]
        b = i // BATCH_SIZE + 1
        for attempt in (1, 2):
            try:
                m = yfinance_fetcher(batch)
                series.update(m)
                print(f"  batch {b}/{n_batches}: fetched {len(m)}/{len(batch)}")
                break
            except Exception as e:                      # noqa: BLE001
                print(f"  batch {b}/{n_batches} attempt {attempt} failed: {e}")
                if attempt == 2:
                    print(f"  batch {b}/{n_batches}: skipping after retry")
    return series


def main() -> None:
    print("Fetching S&P 500 constituents...")
    tickers = get_sp500_tickers()
    print(f"  {len(tickers)} tickers")

    print("Fetching ~7y weekly closes (batched, polite to Yahoo)...")
    series = fetch_all(tickers)
    # keep only usable series
    closes = pd.DataFrame({
        t: s for t, s in series.items()
        if isinstance(s, pd.Series) and s.dropna().shape[0] > 0
    })
    print(f"  usable series: {closes.shape[1]}/{len(tickers)}")
    if closes.empty:
        sys.exit("No data fetched — aborting.")

    closes = closes.sort_index()

    # Per-week breadth. rolling(200) needs 200 non-null obs -> MA only forms
    # once a name has 200 weekly bars, exactly mirroring analyse's denominator.
    formed_count = pd.Series(0.0, index=closes.index)
    above_count = pd.Series(0.0, index=closes.index)
    for t in closes.columns:
        s = closes[t]
        ma = s.rolling(WEEKS).mean()
        formed = ma.notna() & s.notna() & (s >= MIN_PRICE)
        above = formed & (s > ma)
        formed_count = formed_count.add(formed.astype(float), fill_value=0.0)
        above_count = above_count.add(above.astype(float), fill_value=0.0)

    res = pd.DataFrame({"formed": formed_count, "above": above_count})
    res = res[res["formed"] > 0]

    # Drop the current unfinished week if the week's Friday close hasn't passed.
    if len(res):
        last = res.index[-1]
        last_friday = last + pd.Timedelta(days=4)   # weekly bars label Monday
        if pd.Timestamp(date.today()) <= last_friday:
            print(f"  dropping unfinished current week {last.date()}")
            res = res.iloc[:-1]

    res = res.iloc[-LOOKBACK_WEEKS:]
    if res.empty:
        sys.exit("Not enough history to compute breadth.")

    series_out = [
        {"date": idx.strftime("%Y-%m-%d"),
         "pct_above_200wma": round(100.0 * row.above / row.formed, 1)}
        for idx, row in res.iterrows()
    ]
    generated = res.index[-1].strftime("%Y-%m-%d")

    payload = {"universe": "sp500", "generated": generated, "series": series_out}
    os.makedirs(os.path.dirname(os.path.abspath(OUT)), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"\nWrote {len(series_out)} weekly points to {os.path.abspath(OUT)}")
    print(f"  range: {series_out[0]['date']} -> {series_out[-1]['date']}")
    print(f"  latest breadth: {series_out[-1]['pct_above_200wma']}% above 200WMA")


if __name__ == "__main__":
    main()
