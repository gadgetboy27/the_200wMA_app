# 200-Week Moving Average Scanner

A scanner that finds US stocks and crypto majors sitting at, or crossing, their
**200-week moving average** — a long-cycle valuation and trend signal — and
publishes the results as a console table, CSV/JSON, and a self-contained HTML
report.

> **Read this first.** This is a **long-cycle** tool, not a day-trading tool. The
> signal it computes changes a handful of times per *decade* for a given asset.
> If your goal is placing bets on the US market *day to day*, this repo is the
> wrong instrument on its own — see [Viability assessment](#viability-assessment)
> for exactly why and what to build instead.

---

## Repository layout (multi-language by design)

Python and TypeScript each do what they're best at — this is deliberate, not
technical debt.

```
python/    Scanner ENGINE — the correct language for this layer.
           wma200_scanner.py    data fetch (yfinance), batch scan, backtest, HTML report
           gen_test_vectors.py  emits the cross-language golden contract
           requirements.txt
shared/    test_vectors.json    the CONTRACT: input series + expected analyse() output
ts/        Verified TypeScript PORT of the pure maths (analyse + breadth), so the
           Next.js app can compute signals natively without a Python round-trip.
web/       Next.js + TypeScript FRONTEND — reads the scanner's JSON and renders it.
```

**How the two maths implementations stay identical:** the Python `analyse()` is
the source of truth. `python/gen_test_vectors.py` runs it over deterministic
synthetic series covering every branch (crossed up/down, near above/below,
breadth-only, too-short, below-min-price) and writes the inputs + expected
outputs to `shared/test_vectors.json`. The TypeScript port's test suite loads
that same file and must reproduce every value (numeric fields within `1e-6`; the
one real cross-language gotcha is that Python's `round()` is round-half-to-even
while JS `Math.round` is round-half-up). Change the maths in Python, regenerate
the vectors, and the TS test tells you immediately if the port drifted.

```bash
# regenerate the contract after any change to the Python maths:
python/.venv/bin/python python/gen_test_vectors.py
# verify the TS port still matches:
cd ts && npm test
```

---

## What it does

For every ticker in a universe (S&P 500, crypto majors, or a custom list) the
scanner:

1. Downloads ~7 years of **weekly** closing prices from Yahoo Finance (free, no
   API key) via `yfinance`.
2. Computes the **200-week moving average** (200 weeks ≈ 3.85 years).
3. Classifies each asset:
   - **CROSSED UP** — last week closed back above the MA after being below it.
   - **CROSSED DOWN** — last week closed below the MA after being above it.
   - **NEAR (above / below)** — price is within a `±band%` (default ±10%) of the MA.
   - *(everything else is counted for breadth only, no signal.)*
4. Reports the **13-week MA slope** next to every signal. This is the critical
   qualifier: a touch of a *rising* 200WMA is a cyclical-dip entry; a touch of a
   *falling* 200WMA is a structural-decline trap. Never read a signal without it.
5. Computes market **breadth** — the % of the universe trading above its 200WMA —
   a free "risk-on / risk-off" gauge.

### Outputs

| File | Purpose |
|---|---|
| Console table | Quick human scan, sorted by signal priority then distance |
| `wma200_signals.csv` | Spreadsheet / import |
| `wma200_signals.json` | Machine ingestion (breadth + signals + chart data) |
| `wma200_report.html` | Self-contained dark-theme visual report — inline SVG sparklines, no CDN, opens offline |

### The maths (per asset, needs ≥ 214 weekly bars)

```
ma          = rolling_mean(weekly_close, 200)
dist        = (price[-1] - ma[-1]) / ma[-1]
crossedUp   = price[-2] <= ma[-2]  AND  price[-1] >  ma[-1]
crossedDown = price[-2] >= ma[-2]  AND  price[-1] <  ma[-1]
near        = |dist| <= band          (default 0.10)
slope13w    = ma[-1] / ma[-14] - 1    (≈ one quarter of MA trend)
```

Signal priority: `CROSSED UP > CROSSED DOWN > NEAR (below) > NEAR (above)`, then
sorted by `|dist|`. Assets with fewer than 214 weekly bars (young listings) are
skipped — *and excluded from breadth denominators*, so they don't masquerade as
"below the MA."

---

## Usage

```bash
pip install yfinance pandas lxml

python wma200_scanner.py                             # S&P 500, ±10% band
python wma200_scanner.py --universe crypto           # crypto majors
python wma200_scanner.py --universe custom --tickers AAPL MSFT BTC-USD
python wma200_scanner.py --band 5                     # tighter band
python wma200_scanner.py --backtest BTC-USD          # event-study backtest
python wma200_scanner.py --selftest                  # offline pipeline proof
```

Data source: Yahoo Finance weekly bars (free). Batched 50 tickers at a time with
a 1s pause between batches to stay polite to Yahoo.

---

## Engineering quality

This is a well-constructed script, not a toy:

- **Pure, testable core.** `analyse()` is a pure function over a price series; the
  fetcher is dependency-injected into `run_scan()`, so the exact same pipeline
  runs on live Yahoo data or on synthetic offline data.
- **Offline self-test.** `--selftest` builds synthetic geometric-Brownian-motion
  series engineered to produce a cross-up, a cross-down, a near-band touch, and a
  no-signal case, then *asserts* the scanner detects each. The whole pipeline is
  provable without a network.
- **Intellectually honest backtest.** `--backtest` reports signal edge *vs a
  baseline* and explicitly warns about the two things that make most retail
  backtests lie: overlapping forward windows inflate the sample, and scanning
  today's index constituents bakes in survivorship bias.
- **Correct data hygiene.** It knows Yahoo revises adjusted closes (so results
  must upsert, never duplicate), that the current unfinished week is a half-formed
  candle, and that Wikipedia uses `BRK.B` where Yahoo wants `BRK-B`.

---

## Viability assessment

### As what it is — a long-cycle scanner: **strong. Use it.**

The 200-week MA is one of the more respected long-horizon reference lines,
especially in crypto, where "price reclaims / loses its 200-week MA" has
historically marked multi-year regime changes. As a **weekly** discipline —
"what crossed this week, what's near, is the whole market rich or cheap" — this
tool is genuinely useful and cheaply run. The breadth number alone (% of the
S&P above its 200WMA) is a legitimate macro risk gauge. **Verdict: viable and
worth running weekly.**

### As a real-time, day-to-day betting engine: **not viable as-is, and not a small tweak.**

This is the honest core of the assessment. There is a fundamental
**timeframe mismatch** between the tool and your stated goal:

| Your goal | What this tool provides |
|---|---|
| Place bets *day to day* | A signal built from **weekly** bars over **~4 years** |
| React in **real time** | A line that meaningfully moves a **few times per decade** per asset |
| Frequent, actionable entries | Maybe a handful of S&P signals *per year*, total |

A 200-week MA moves by roughly `1/200th` of one new week's data each week — it is
almost flat by construction. Feeding it a real-time price stream doesn't make it
fast; it just makes the *last, unfinished bar* jitter around a line that hasn't
moved. You'd generate flicker, not signal. **"Real-time" and "200-week MA" are
close to contradictory.** Making this app tick-by-tick would be building
horsepower for a road it never drives on.

There are also structural gaps for *any* money-on-the-line use:

- **Free Yahoo data is delayed and unofficial** (~15 min, best-effort, no SLA,
  and it rate-limits / breaks without warning). Fine for a weekly scan; unfit for
  real-time execution decisions.
- **No position sizing, risk limits, stops, or execution path.** A scanner tells
  you *what* is interesting. It says nothing about *how much*, *when to exit*, or
  *what it costs you when wrong* — which is where trading accounts actually live
  or die.
- **No statistical edge is demonstrated.** The backtest is honest *precisely
  because* it refuses to claim one. "Interesting technical level" ≠ "positive
  expectancy after costs, slippage, and taxes."
- **Regulatory / personal-risk reality.** "Bets on the US stock market day to
  day" is, statistically, a way most retail participants lose money. Nothing here
  changes those odds; treat any live use as speculation with capital you can
  afford to lose.

### Recommendation

**Keep this as what it's good at** — a weekly long-cycle scanner and breadth
monitor — and don't try to stretch it into a day-trading terminal. If you want a
genuine real-time daily app, that's a *different* system with different
foundations. See below.

---

## If you genuinely want a real-time daily app

Treat that as a new build layered on top of this one, not a rewrite of it. The
scanner becomes the slow, strategic layer; a separate fast layer handles the day.

1. **Fix the data layer first.** Real-time decisions need a real feed — Polygon,
   Alpaca, Databento, or a broker's market-data API — not delayed Yahoo. This is
   the single biggest gap and it costs money. No feed, no real-time app.
2. **Use intraday / daily timeframes for the fast signals.** Day-to-day decisions
   come from daily and intraday bars (e.g. 20/50-day MAs, RSI, VWAP, ATR-based
   ranges), *contextualized* by this tool's weekly regime read. The 200WMA becomes
   the "what regime am I in" backdrop, not the trigger.
3. **Build the risk layer before the signal layer.** Position sizing, per-trade
   stop-loss, daily max-loss cutoff, and exposure caps. This matters more than any
   indicator and is the part hobby projects skip.
4. **Paper-trade through a broker API first** (Alpaca has a free paper-trading
   sandbox). Prove the strategy survives *real fills, spreads, and slippage*
   before a cent is at risk. Expect most ideas to die here — that's the point.
5. **Then, and only then,** wire alerts/automation. The existing StockMind spec
   (Supabase + Railway cron + webhook alerts) is a fine skeleton for the *weekly*
   layer; the real-time layer needs an always-on process and a streaming feed, not
   a cron job.

**Blunt bottom line:** the code is good and the weekly scanner is worth using as
built. But "real-time day-to-day betting" is a materially harder, riskier, and
more expensive system than a 200-week scanner — and the 200-week MA is the wrong
engine to drive it. Run this weekly for regime and breadth; build the fast layer
separately, risk-first, and paper-trade it hard before betting real money.

---

## Roadmap (StockMind integration)

A build spec exists to port this into the StockMind AI stack (Next.js 14 /
TypeScript / Supabase / Railway cron) as a **weekly** scanner that (a) nominates
trade candidates for a composite-scoring pipeline, (b) contributes a 10-pt
Technical/Cycle component to a 0–100 score, and (c) feeds a market-breadth
indicator into the macro watch. That's the right altitude for this tool — weekly,
strategic, breadth-aware — and a good next step. It is explicitly *not* the
real-time layer described above.

**Already delivered toward that spec:**
- `ts/` — the pure 200WMA maths (`analyse` + breadth) ported to TypeScript and
  verified against the Python golden vectors (12/12 tests, mutation-checked). The
  Next.js app can now compute signals natively.
- `web/` — a Next.js 14 dashboard (breadth strip + signal cards + inline SVG
  sparklines) that renders the **real** scanner output from
  `web/public/wma200_signals.json`. Signals are classified by the 13-week MA
  slope into **Actionable entries / Watch / Caution / Avoid** and sectioned so the
  rising-MA setups pin to the top and the falling-knife traps sink to the bottom.
  Run it with `cd web && npm install && npm run dev`.
- `scripts/weekly_scan.sh` — one command that runs the full S&P scan and wires the
  JSON into the frontend. `scripts/com.wma200.weekly.plist` schedules it every
  Sunday 08:00 via macOS launchd (fires at next wake if the Mac was asleep).
- `python/gen_value_timing.py` — the **Value Timing** pass over the current
  signals (free yfinance data, like the other generators): a Piotroski F-score
  (9 financial-health checks from the two most recent common fiscal years),
  valuation z-scores (today's P/E / P/S / P/B vs the name's own ~4-year weekly
  ratio history — split-adjusted, +90-day filing lag, P/B killed on negative
  book value), and a volatility-scaled **tranche ladder** (rung 1 at the 200WMA,
  rungs 2–3 at the p50/p10 of the name's last-10y weekly close depths below the
  line, weighted 25/35/40). Rendered per card as plain-English Health / Value /
  Buy-plan lines; crypto gets the ladder only (no statements).

**Still to build for the full StockMind integration:** the Yahoo weekly adapter in
TS (or keep Python as the scanner and have TS just consume its JSON — the current
split), Supabase persistence, the watch rules + webhook, composite-score
rebalance, promotion queue, and the two Railway cron entries.

---

## Disclaimer

This software is for research and educational use only. It is not financial
advice, not a recommendation to buy or sell any security or crypto asset, and
makes no claim of profitability. Trading and "betting" on markets can lose you
money — potentially all of it. Do your own research and only risk capital you can
afford to lose.
