#!/usr/bin/env python3
"""Inject data/real_data.json into the template and write dashboard/dist/.

Run after any change to data/ or dashboard/dashboard_template.html.
Refuses to write a build with an unsubstituted placeholder, because a dashboard
that loads with no data looks like a broken app rather than a build error.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TPL = ROOT / "dashboard" / "dashboard_template.html"
DATA = ROOT / "data" / "real_data.json"
OUT = ROOT / "dashboard" / "dist" / "avocado-pipeline.html"


def main():
    if not DATA.exists():
        sys.exit("data/real_data.json missing — run `python data/real_data.py` first")
    payload = json.loads(DATA.read_text())      # parse to catch malformed JSON early
    html = TPL.read_text().replace("__DATA__", json.dumps(payload, default=str))
    if "__DATA__" in html:
        sys.exit("placeholder still present after substitution — template is malformed")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html)

    states = len(payload.get("states", []))
    eds = payload.get("editions", [])
    contacts = sum(len(e["contacts"]) for e in eds)
    covered = {c["state"] for e in eds for c in e["contacts"] if c.get("state")}
    print(f"built {OUT.relative_to(ROOT)}  {len(html):,} bytes")
    print(f"  {states} states · {len(eds)} editions · {contacts} contacts "
          f"· {len(covered)} states covered")

    # Cheap regression guard. These have all been broken at least once.
    for needle, why in [
        ("COVERED_ONLY", "covered-states toggle"),
        ("function oppKey", "cross-edition opportunity matching"),
        ("function dealRole", "issuer vs applicant classification"),
        ("function patternCheck", "email pattern conformance check"),
    ]:
        if needle not in html:
            sys.exit(f"build is missing {why} — did the template get clobbered?")
    print("  regression guards passed")


if __name__ == "__main__":
    main()
