"""
Append THIS week's breadth point to web/public/breadth_history.json.

Idempotent: dedup by the latest weekly-bar date (derived from the signal charts,
so no extra network fetch), so a re-run of the same week overwrites in place and
never duplicates. This does NOT regenerate the full multi-year history — that is
gen_breadth_history.py, run once/occasionally.

Usage:
    python append_breadth.py [signals.json] [breadth_history.json]
Defaults resolve to web/public/ relative to this file.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PUB = os.path.join(HERE, "..", "web", "public")

signals_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(PUB, "wma200_signals.json")
hist_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(PUB, "breadth_history.json")

with open(signals_path) as f:
    sig = json.load(f)

pct = sig["breadth"]["pct_above_200wma"]
# Latest weekly-bar date across the signal charts (matches gen_breadth_history's
# date convention) — no extra network call needed.
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
print(f"  appended/updated {latest}: {round(float(pct), 1)}% "
      f"({len(hist['series'])} points total)")
