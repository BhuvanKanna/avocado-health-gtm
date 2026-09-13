#!/usr/bin/env python3
"""
Pull live RHTP subaward records from USAspending and write JSON the dashboard
can ingest.

    python fetch_live.py                 # writes usaspending_live.json
    python fetch_live.py --listing 93.505

Then drop the JSON file on the dashboard's "Add briefing" tab. The dashboard
tries this fetch itself first; this script exists because browsers block the
cross-origin request in some contexts and a blocked fetch should not mean no
data.

Only the standard library is required.
"""
import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import date

API = "https://api.usaspending.gov/api/v2/search/spending_by_award/"

# Assistance listings worth pulling.
#
# 93.798 is the program itself. The other four are the reason --all exists: the
# recipients of MIECHV, Healthy Start, Title V and the Health Center Program ARE
# the Avocado candidate universe. They are organizations that already run home
# visiting, CHW, doula and maternal-health programs, already hold federal money,
# already clear a federal compliance bar, and are named with a state in a public
# API. That is a 50-state prospect list that needs no briefing to exist.
LISTINGS = {
    "93.798": "Rural Health Transformation Program",
    "93.505": "MIECHV — Maternal, Infant and Early Childhood Home Visiting",
    "93.926": "Healthy Start Initiative",
    "93.994": "MCH Services Block Grant (Title V)",
    "93.224": "Health Center Program (FQHC 330)",
}

# Listing -> Avocado segment. A Healthy Start grantee runs exactly the staffing
# model Avocado offloads; a Health Center Program recipient is an FQHC by
# definition. The listing is a stronger segment signal than the org name.
LISTING_SEGMENT = {
    "93.224": "FQHC", "93.505": "OB", "93.926": "OB",
    "93.994": "GOV", "93.798": None,
}

SUB_FIELDS = ["Sub-Award ID", "Sub-Awardee Name", "Sub-Award Amount",
              "Sub-Award Date", "Awarding Agency", "Awarding Sub Agency",
              "Prime Recipient Name", "Prime Award ID", "Sub-Award Primary Place of Performance"]

PRIME_FIELDS = ["Award ID", "Recipient Name", "Award Amount", "Start Date",
                "Awarding Agency", "Place of Performance State Code",
                "Description"]


def post(payload: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(
        API, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "User-Agent": "avocado-pap/1.0 (pipeline research)"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


class FetchFailed(Exception):
    """A request that never completed.

    This exists because the alternative is worse. If a network failure returns
    an empty list, "the API is unreachable" and "no state has moved any money
    yet" produce identical output -- and the second is a real, important
    finding you would act on. A failure must never be able to impersonate a
    result.
    """


def paged(payload: dict, max_pages: int = 25) -> list[dict]:
    out, page, errors = [], 1, []
    while page <= max_pages:
        try:
            j = post({**payload, "page": page, "limit": 100})
        except urllib.error.HTTPError as e:
            body = e.read()[:200].decode(errors="replace")
            errors.append(f"HTTP {e.code} on page {page}: {body}")
            break
        except Exception as e:
            errors.append(f"page {page}: {e}")
            break
        rows = j.get("results", [])
        out.extend(rows)
        if not j.get("page_metadata", {}).get("hasNext") or not rows:
            break
        page += 1
    if errors and not out:
        raise FetchFailed("; ".join(errors))
    for e in errors:
        print(f"  partial: {e}", file=sys.stderr)
    return out


def fetch(listing: str) -> dict:
    base = {"filters": {"program_numbers": [listing],
                        "award_type_codes": ["02", "03", "04", "05"]}}
    print(f"[{listing}] {LISTINGS.get(listing, '')}")
    try:
        primes = paged({**base, "fields": PRIME_FIELDS, "subawards": False})
        print(f"  prime awards:  {len(primes)}")
        subs = paged({**base, "fields": SUB_FIELDS, "subawards": True})
        print(f"  subawards:     {len(subs)}")
    except FetchFailed as e:
        print(f"\n  COULD NOT REACH USAspending: {e}", file=sys.stderr)
        print("  Nothing was written. This is a connectivity failure, not a finding.",
              file=sys.stderr)
        print("  Check your network, or a proxy/allowlist blocking api.usaspending.gov.",
              file=sys.stderr)
        raise SystemExit(2)

    by_state = {}
    for s in subs:
        # Prefer the explicit place-of-performance state; fall back to parsing
        # the prime recipient string, which is how state agencies are named.
        pop = s.get("Sub-Award Primary Place of Performance") or {}
        st = pop.get("state_code") if isinstance(pop, dict) else None
        if not st:
            name = (s.get("Prime Recipient Name") or "").upper()
            st = next((c for c in STATE_CODES if f" {c} " in f" {name} "), None)
        if not st:
            continue
        d = by_state.setdefault(st, {"moved": 0.0, "n": 0, "recipients": set()})
        d["moved"] += float(s.get("Sub-Award Amount") or 0)
        d["n"] += 1
        if s.get("Sub-Awardee Name"):
            d["recipients"].add(s["Sub-Awardee Name"])
    for d in by_state.values():
        d["recipients"] = sorted(d["recipients"])
    orgs = harvest_orgs(listing, primes, subs)
    print(f"  organizations: {len(orgs)}")
    return {"listing": listing, "primes": primes, "results": subs,
            "by_state": by_state, "organizations": orgs}


def guess_segment(name: str, listing: str) -> str:
    seg = LISTING_SEGMENT.get(listing)
    n = (name or "").lower()
    if re.search(r"\bdepartment|\bdept\b|cabinet|commonwealth|\bstate of\b|division of", n):
        return "GOV"
    if re.search(r"community health center|health center|federally qualified|\bfqhc\b|clinica", n):
        return "FQHC"
    if re.search(r"hospital|medical center|health system|regional health", n):
        return "RHS"
    if re.search(r"association|coalition|council", n):
        return "ASSOC"
    if re.search(r"university|college|board of (regents|trustees)", n):
        return "EDU"
    if re.search(r"school district|board of education|head start", n):
        return "SCH"
    if re.search(r"behavioral|counseling|autism", n):
        return "ABA"
    if re.search(r"family|parent|healthy start|maternal|birth|doula|perinatal", n):
        return "OB"
    return seg or "CBO"


def harvest_orgs(listing: str, primes: list[dict], subs: list[dict]) -> dict:
    """Named organizations with award history, keyed by normalised name.

    This is the part that makes the pipeline 50 states wide. Each recipient
    carries how many awards it holds, how much, and how recently -- which are
    exactly the award-history features Model A learns from once there is enough
    label history to train it.
    """
    orgs = {}

    def add(name, state, amount, when, tier):
        if not name:
            return
        key = re.sub(r"[^a-z0-9 ]", " ", name.lower())
        key = re.sub(r"\b(inc|llc|corp|corporation|the|of|a)\b", " ", key)
        key = re.sub(r"\s+", " ", key).strip()
        o = orgs.setdefault(key, {
            "name": name, "state": state, "n_awards": 0, "total": 0.0,
            "listings": [], "latest": None, "tiers": [],
            "segment": guess_segment(name, listing)})
        o["n_awards"] += 1
        o["total"] += float(amount or 0)
        if listing not in o["listings"]:
            o["listings"].append(listing)
        if tier not in o["tiers"]:
            o["tiers"].append(tier)
        if when and (not o["latest"] or str(when) > str(o["latest"])):
            o["latest"] = when
        if state and not o["state"]:
            o["state"] = state

    for p in primes:
        add(p.get("Recipient Name"), p.get("Place of Performance State Code"),
            p.get("Award Amount"), p.get("Start Date"), "prime")
    for s_ in subs:
        pop = s_.get("Sub-Award Primary Place of Performance") or {}
        st = pop.get("state_code") if isinstance(pop, dict) else None
        add(s_.get("Sub-Awardee Name"), st, s_.get("Sub-Award Amount"),
            s_.get("Sub-Award Date"), "sub")
    return orgs


STATE_CODES = ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
               "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
               "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
               "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
               "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--listing", action="append", default=None,
                    help="assistance listing; repeatable. Default 93.798")
    ap.add_argument("--all", action="store_true",
                    help="pull every listing in LISTINGS (slower, needed for training data)")
    ap.add_argument("--out", default="usaspending_live.json")
    a = ap.parse_args()

    listings = list(LISTINGS) if a.all else (a.listing or ["93.798"])
    blocks = [fetch(l) for l in listings]   # exits non-zero if unreachable

    merged_results = [r for b in blocks for r in b["results"]]
    merged_orgs = {}
    for b in blocks:
        for k, o in b["organizations"].items():
            m = merged_orgs.get(k)
            if not m:
                merged_orgs[k] = o
                continue
            m["n_awards"] += o["n_awards"]
            m["total"] += o["total"]
            m["listings"] = sorted(set(m["listings"]) | set(o["listings"]))
            m["tiers"] = sorted(set(m["tiers"]) | set(o["tiers"]))
            if o["latest"] and (not m["latest"] or o["latest"] > m["latest"]):
                m["latest"] = o["latest"]
            m["state"] = m["state"] or o["state"]
    merged_state = {}
    for b in blocks:
        for st, d in b["by_state"].items():
            m = merged_state.setdefault(st, {"moved": 0.0, "n": 0})
            m["moved"] += d["moved"]
            m["n"] += d["n"]

    payload = {"fetched": date.today().isoformat(), "listings": listings,
               "results": merged_results, "by_state": merged_state,
               "organizations": list(merged_orgs.values()),
               "source": "USAspending API v2 spending_by_award"}
    with open(a.out, "w") as f:
        json.dump(payload, f)

    print(f"\nwrote {a.out}")
    print(f"  {len(merged_results)} subaward records across {len(merged_state)} states")
    st_cov = len({o["state"] for o in merged_orgs.values() if o["state"]})
    print(f"  {len(merged_orgs)} named organizations across {st_cov} states")
    segs = {}
    for o in merged_orgs.values():
        segs[o["segment"]] = segs.get(o["segment"], 0) + 1
    if segs:
        print("    " + "  ".join(f"{k}={v}" for k, v in
                                 sorted(segs.items(), key=lambda kv: -kv[1])))
    if merged_state:
        top = sorted(merged_state.items(), key=lambda kv: -kv[1]["moved"])[:8]
        for st, d in top:
            print(f"    {st}  ${d['moved']:>14,.0f}  {d['n']:>4} records")
    else:
        print("  No subaward records yet. For RHTP that is the expected answer")
        print("  today and it is itself the signal: no state has moved first-tier")
        print("  money through USAspending reporting, so every award is still ahead.")
    print("\nDrop this file on the dashboard's Add-briefing tab.")


if __name__ == "__main__":
    main()
