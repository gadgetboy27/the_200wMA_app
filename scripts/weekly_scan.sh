#!/usr/bin/env bash
# Weekly 200WMA refresh: run the scanner over the S&P 500 and wire its output
# into the frontend. 200WMA is a weekly signal (Friday's weekly bar is final),
# so once a week is the correct cadence — nothing here needs to run intraday.
#
# Manual run:   ./scripts/weekly_scan.sh
# Scheduled:    see scripts/com.wma200.weekly.plist (macOS launchd) or crontab.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/python/.venv/bin/python"
STAMP="$(date '+%Y-%m-%d %H:%M:%S')"

echo "[$STAMP] starting S&P 500 200WMA scan"

# The scanner writes wma200_signals.{json,csv} + wma200_report.html into its CWD.
cd "$ROOT/python"
"$PY" wma200_scanner.py --universe sp500 --band 10

# Wire the fresh output into the frontend (Server Component reads this file).
cp "$ROOT/python/wma200_signals.json" "$ROOT/web/public/wma200_signals.json"

echo "[$STAMP] wired $(du -h "$ROOT/web/public/wma200_signals.json" | cut -f1) into web/public/wma200_signals.json"

# ---------------------------------------------------------------------------
# Crypto scan -> web/public/wma200_signals_crypto.json
# Run the scanner in a scratch dir so it can't clobber the S&P wma200_signals.json.
# ---------------------------------------------------------------------------
echo "[$STAMP] starting crypto 200WMA scan"
CRYPTO_DIR="$(mktemp -d)"
trap 'rm -rf "$CRYPTO_DIR"' EXIT
( cd "$CRYPTO_DIR" && "$PY" "$ROOT/python/wma200_scanner.py" --universe crypto --band 10 )
cp "$CRYPTO_DIR/wma200_signals.json" "$ROOT/web/public/wma200_signals_crypto.json"
echo "[$STAMP] wired crypto signals into web/public/wma200_signals_crypto.json"

# ---------------------------------------------------------------------------
# Per-name base rates (event study) -> web/public/base_rates.json
# Reads both current-signal files above; safe to run after both exist.
# ---------------------------------------------------------------------------
echo "[$STAMP] computing per-name base rates"
"$PY" "$ROOT/python/gen_base_rates.py"

# ---------------------------------------------------------------------------
# Append THIS week's breadth point to web/public/breadth_history.json.
# Idempotent: dedup by weekly-bar date so a re-run of the same week overwrites,
# never duplicates. This does NOT regenerate the full 3-year history — that is
# gen_breadth_history.py, run once/occasionally.
# ---------------------------------------------------------------------------
echo "[$STAMP] appending latest breadth point to breadth_history.json"
"$PY" - "$ROOT/web/public/wma200_signals.json" "$ROOT/web/public/breadth_history.json" <<'PYAPPEND'
import json, os, sys
signals_path, hist_path = sys.argv[1], sys.argv[2]

with open(signals_path) as f:
    sig = json.load(f)
pct = sig["breadth"]["pct_above_200wma"]
# Use the latest weekly-bar date (matches gen_breadth_history's date convention),
# derived from the signal charts so no extra network fetch is needed.
bar_dates = [c["dates"][-1] for s in sig["signals"]
             if (c := s.get("chart")) and c.get("dates")]
if not bar_dates or pct is None:
    print("  no bar date / breadth available — nothing to append")
    sys.exit(0)
latest = max(bar_dates)

if os.path.exists(hist_path):
    with open(hist_path) as f:
        hist = json.load(f)
else:
    hist = {"universe": "sp500", "generated": latest, "series": []}

by_date = {p["date"]: p for p in hist.get("series", [])}
by_date[latest] = {"date": latest, "pct_above_200wma": round(float(pct), 1)}  # overwrite
hist["series"] = [by_date[d] for d in sorted(by_date)]
hist["generated"] = hist["series"][-1]["date"]

with open(hist_path, "w") as f:
    json.dump(hist, f, indent=2)
print(f"  appended/updated {latest}: {round(float(pct),1)}% "
      f"({len(hist['series'])} points total)")
PYAPPEND

echo "[$STAMP] done — signals(sp500,crypto), base_rates and breadth_history refreshed in web/public/"
echo "[$STAMP] if serving a production build, run 'cd web && npm run build' to re-render;"
echo "         'npm run dev' picks up the new JSON on next request automatically."
