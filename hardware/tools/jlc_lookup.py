#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Resolve JLCPCB/LCSC part numbers for a parts list and write a CSV.

Input: a JSON file mapping part keys to queries, e.g.
    {"R_10k_0402": {"kind": "resistor", "package": "0402", "value": 10000},
     "C_100n_0402": {"kind": "capacitor", "package": "0402", "value": 1e-7, "min_v": 16},
     "U_BQ25628E": {"kind": "mpn", "mpn": "BQ25628ERYKR"}}

Selection: prefer JLCPCB "basic" parts (no extra assembly fee), then the
highest stock. Resistors must be <= 1 % tolerance; capacitors must meet the
minimum voltage and use X5R/X7R (or C0G/NP0 when "dielectric": "C0G").

Data source: the public jlcsearch API (jlcsearch.tscircuit.com). Results are
a snapshot; the CSV records the lookup date so stock can be re-checked before
ordering.

Usage:
    python3 hardware/tools/jlc_lookup.py parts_query.json parts.csv
"""
import csv
import datetime
import json
import sys
import time
import urllib.parse
import urllib.request

API = "https://jlcsearch.tscircuit.com"


def get(path: str, **params) -> dict:
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "ko-jlc-lookup/1.0", "Accept": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:  # network hiccup: back off and retry
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
    return {}


def pick(rows: list[dict], ok) -> dict | None:
    """Basic parts first, then parts with known stock, then parts whose stock the API
    does not report (marked "stock unknown" in the CSV; re-check before ordering)."""
    rows = [r for r in rows if ok(r)]
    rows.sort(key=lambda r: (not r.get("is_basic"), not (r.get("stock") or 0) > 0,
                             not r.get("is_preferred"), -(r.get("stock") or 0)))
    return rows[0] if rows else None


def num(v: float):
    return int(v) if float(v).is_integer() else v


def resistor(q: dict) -> dict | None:
    ok = lambda r: (r.get("tolerance_fraction") or 1) <= 0.01
    for extra in ({"is_basic": "true"}, {}):
        rows = get("resistors/list.json", package=q["package"], resistance=num(q["value"]), **extra)
        r = pick(rows.get("resistors", []), ok)
        if r:
            return r
    return None


def capacitor(q: dict) -> dict | None:
    want = ("C0G", "NP0") if q.get("dielectric") == "C0G" else ("X5R", "X7R", "X7S", "X6S")
    ok = lambda r: ((r.get("voltage_rating") or 0) >= q.get("min_v", 6.3)
                    and any(d in (r.get("temperature_coefficient") or "") for d in want))
    for extra in ({"is_basic": "true"}, {}):
        rows = get("capacitors/list.json", package=q["package"], capacitance=q["value"], **extra)
        r = pick(rows.get("capacitors", []), ok)
        if r:
            return r
    return None


def search(q: dict) -> dict | None:
    """MPN queries need an exact manufacturer part number; the API only matches
    prefixes reliably, so shorten the search term until the exact part shows up."""
    if q.get("mpn"):
        mpn = q["mpn"].upper()
        for n in range(len(mpn), 4, -1):
            rows = get("components/list.json", search=mpn[:n], limit=50).get("components", [])
            exact = [r for r in rows if (r.get("mfr") or "").upper() == mpn]
            if exact:
                return pick(exact, lambda r: True)
        return None
    rows = get("components/list.json", search=q["search"], limit=50).get("components", [])
    return pick(rows, lambda r: q.get("package", "") in (r.get("package") or ""))


def main() -> None:
    queries = json.load(open(sys.argv[1]))
    out = sys.argv[2]
    today = datetime.date.today().isoformat()
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["key", "lcsc", "mfr", "package", "stock", "basic", "description", "checked"])
        for key, q in queries.items():
            if q["kind"] == "fixed":  # verified by hand (date in "checked"); no API call
                w.writerow([key, q["lcsc"], q["mfr"], q.get("package", ""), q.get("stock", ""),
                            q.get("basic", "no"), q.get("description", ""), q["checked"]])
                print(f"{key:22s} {q['lcsc']:10s} {q['mfr']:28s} fixed, checked {q['checked']}")
                continue
            fn = {"resistor": resistor, "capacitor": capacitor}.get(q["kind"], search)
            r = fn(q)
            if r is None:
                print(f"NOT FOUND: {key} {q}", file=sys.stderr)
                w.writerow([key, "", "", "", 0, "", "NOT FOUND", today])
                continue
            lcsc = f"C{r['lcsc']}"
            desc = (r.get("description") or "")[:90]
            stock = r.get("stock") or ("basic" if r.get("is_basic") else "unknown")
            w.writerow([key, lcsc, r.get("mfr", ""), r.get("package", ""), stock,
                        "yes" if r.get("is_basic") else "no", desc, today])
            print(f"{key:22s} {lcsc:10s} {r.get('mfr', ''):28s} stock {(r.get('stock') or 0):>8} "
                  f"{'basic' if r.get('is_basic') else ''}")


if __name__ == "__main__":
    main()
