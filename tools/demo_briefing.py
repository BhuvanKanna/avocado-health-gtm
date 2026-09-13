"""
Step 1 of the build order, runnable today against a real Civic Operator edition.

    python demo_briefing.py path/to/briefing.html [path/to/yesterday.html]

Stores each edition as an immutable snapshot under ./editions/ and prints the
deltas against the previous one. No model, no credentials, no ML. This is the
piece that turns a subscription that prints a document into an asset that
accumulates, and it pays for itself the first time a deadline moves.
"""
import json
import sys
from datetime import date
from pathlib import Path

from avocado_pap.ingest.sources import (CONTACT_KEY, CivicOperatorBriefing,
                                        diff_editions, row_key)

STORE = Path("./editions")
STORE.mkdir(exist_ok=True)


def snapshot(path: Path, edition: date) -> dict:
    b = CivicOperatorBriefing(path.read_text(), edition)
    snap = {"edition": edition.isoformat(),
            "contacts": b.contacts(), "opportunities": b.opportunities()}
    (STORE / f"{edition.isoformat()}.json").write_text(json.dumps(snap, indent=1))
    return snap


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    curr = snapshot(Path(sys.argv[1]), date.today())

    c = curr["contacts"]
    sourced = sum(r["verification"] >= 3 for r in c)
    print(f"\nEdition parsed: {len(c)} contact rows, "
          f"{len(curr['opportunities'])} opportunities")
    print(f"  source-verified rows : {sourced}")
    print(f"  unsourced rows       : {len(c) - sourced}  "
          f"<- candidates for the resolution pipeline, not facts")
    keys = {row_key(r, CONTACT_KEY) for r in c}
    names = {r["name"] for r in c}
    if len(names) < len(keys):
        print(f"  duplicate names      : {len(keys) - len(names)}  "
              f"(keyed compositely, so none collapse)")

    if len(sys.argv) < 3:
        print("\nNo prior edition supplied; snapshot stored for tomorrow.")
        return

    prev = snapshot(Path(sys.argv[2]), date(2000, 1, 1))
    print("\nDeltas since the previous edition")
    for e in diff_editions(prev["contacts"], curr["contacts"]):
        r = e.get("row", {})
        extra = ""
        if e["type"] == "deadline_moved":
            extra = f"  {e['from']} -> {e['to']}"
        print(f"  {e['priority']:.2f}  {e['type']:18s}  "
              f"{r.get('name', '')[:36]:36s} {r.get('organization', '')[:34]}{extra}")


if __name__ == "__main__":
    main()
