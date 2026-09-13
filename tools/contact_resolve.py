#!/usr/bin/env python3
"""
Contact resolution.

    python contact_resolve.py briefing.pdf
    python contact_resolve.py briefing.html --csv contacts.csv
    python contact_resolve.py real_data.json --verify

Takes the contacts a Civic Operator briefing surfaces and does the three things
the briefing deliberately does not:

  1. Learns each domain's email pattern from the addresses that ARE published,
     and applies it to the rows that are not.
  2. Classifies every title into economic buyer / champion / gatekeeper, so the
     entry point is a field rather than a judgement call made per row.
  3. Scores confidence, and never writes an inferred address into the same
     column as a verified one.

Why this and not a model: in the 2026-09-03 edition, 6 of 45 contact rows carry
a public source. The other 39 are real people at real agencies whose addresses
follow a pattern visible in the 6. That is a deterministic problem, and solving
it deterministically means the output can be checked.

`--verify` attempts MX lookup on the inferred domains. It confirms the domain
accepts mail; it does not confirm the mailbox exists. Nothing here sends mail or
probes a mailbox, which would be both rude and a good way to get a domain
blocklisted.
"""
import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# --------------------------------------------------------------------------
# Role classification
# --------------------------------------------------------------------------
# Ordered: the first match wins, so the most specific patterns come first.
# The champion rule is the one that matters. Doc 04 §2: the champion is the
# operational person whose time Avocado gives back, and is usually the actual
# entry point. A list of CEOs is a list of cold calls with titles attached.
ROLE_RULES = [
    (r"chief executive|(^|\b)ceo\b|president and ceo|executive director|"
     r"\bsecretary\b|commissioner|chief financial|(^|\b)cfo\b|administrator",
     "economic_buyer"),
    (r"government (affairs|relations)|vp of government|legislative|"
     r"vice president of development|development\b|strategic partners",
     "gatekeeper"),
    (r"chief operating|(^|\b)coo\b|chief nursing|chief quality|chief strategy|"
     r"chief administrative|program (director|lead|manager|inbox)|coordinator|"
     r"outreach|deputy (director|commissioner)|specialist|interim lead|"
     r"point of contact|director, rural health|director, state office|"
     r"primary care office|informatics|grants",
     "champion"),
    (r"^director$|\bdirector\b", "economic_buyer"),
]

PATTERNS = [
    ("first.last", lambda f, l: f"{f}.{l}"),
    ("First.Last", lambda f, l: f"{f.capitalize()}.{l.capitalize()}"),
    ("flast", lambda f, l: f"{f[0]}{l}"),
    ("firstl", lambda f, l: f"{f}{l[0]}"),
    ("first_last", lambda f, l: f"{f}_{l}"),
    ("firstlast", lambda f, l: f"{f}{l}"),
    ("last.first", lambda f, l: f"{l}.{f}"),
    ("lastf", lambda f, l: f"{l}{f[0]}"),
    ("f.last", lambda f, l: f"{f[0]}.{l}"),
]


def classify_role(title: str) -> str:
    if not title or "no title" in title.lower():
        return "unknown"
    for pat, role in ROLE_RULES:
        if re.search(pat, title, re.I):
            return role
    return "unknown"


def name_parts(name: str):
    if not name or "no named individual" in name.lower():
        return None
    toks = [t for t in re.sub(r"^(Dr|Mr|Ms|Mrs)\.?\s+", "", name.strip()).split()
            if len(t) > 1]
    if len(toks) < 2:
        return None
    clean = lambda s: re.sub(r"[^a-z]", "", s.lower())
    return clean(toks[0]), clean(toks[-1])


def learn_patterns(contacts: list[dict]) -> dict:
    """Domain -> {pattern, confirming, seen, confidence}."""
    hits = defaultdict(Counter)
    seen = Counter()
    org_of = {}
    for c in contacts:
        email, name = c.get("email"), c.get("name")
        if not email or "@" not in email:
            continue
        local, dom = email.rsplit("@", 1)
        np = name_parts(name)
        if not np:
            continue
        seen[dom] += 1
        org_of.setdefault(dom, c.get("organization"))
        for pid, fn in PATTERNS:
            if fn(*np).lower() == local.lower():
                hits[dom][pid] += 1
    out = {}
    for dom, c in hits.items():
        # Case variants of the same shape (first.last vs First.Last) are not
        # competing patterns; they are one pattern. Only count a domain as
        # ambiguous when genuinely different shapes tie.
        shapes = Counter()
        for pid_, n_ in c.items():
            shapes[pid_.lower()] += n_
        pid_l, n = shapes.most_common(1)[0]
        pid = next(k for k in c if k.lower() == pid_l)
        # Confidence needs both agreement and volume. One matching address is
        # a coincidence as often as a pattern; three is a pattern.
        agreement = n / max(seen[dom], 1)
        volume = min(n / 3, 1.0)
        out[dom] = {"pattern": pid, "confirming": n, "seen": seen[dom],
                    "confidence": round(agreement * volume, 3),
                    "organization": org_of.get(dom),
                    "ambiguous": len(shapes) > 1 and
                                 shapes.most_common(2)[1][1] == n}
    return out


def validate(contact: dict, patterns: dict) -> dict | None:
    """Check a published-but-unsourced address against its domain's pattern.

    This is the operation that actually matters on a real briefing. Civic
    Operator's "Not published" flag means it could not cite a public page for
    the row, not that the address is missing -- most unsourced rows DO carry an
    address. So the useful question is not "can we recover it" but "does it
    conform to the pattern the sourced addresses on that domain establish."

    Conforming is corroboration, not proof. Deviating is the interesting case:
    either the pattern has an exception (hyphenated surnames, duplicate names,
    a legacy account) or the address is wrong. Either way a human should look
    before it goes into a sequence.
    """
    email = contact.get("email")
    if not email or "@" not in email:
        return None
    if contact.get("verification", 1) >= 3:
        return None                       # already vouched by a human
    local, dom = email.rsplit("@", 1)
    p = patterns.get(dom)
    np = name_parts(contact.get("name", ""))
    if not p or not np:
        return None
    expected = dict(PATTERNS)[p["pattern"]](*np)
    conforms = expected.lower() == local.lower()
    return {"pattern_check": "conforms" if conforms else "deviates",
            "expected_local": expected,
            "check_confidence": p["confidence"]}


def infer(contact: dict, patterns: dict, org_domains: dict) -> dict | None:
    if contact.get("email"):
        return None
    np = name_parts(contact.get("name", ""))
    if not np:
        return None
    dom = org_domains.get(contact.get("organization"))
    if not dom or dom not in patterns:
        return None
    p = patterns[dom]
    fn = dict(PATTERNS)[p["pattern"]]
    return {"email_inferred": f"{fn(*np)}@{dom}",
            "pattern": p["pattern"],
            "confidence": p["confidence"],
            "basis": f"{p['confirming']}/{p['seen']} confirmed addresses on {dom}"}


def load_contacts(path: Path) -> list[dict]:
    if path.suffix == ".json":
        d = json.loads(path.read_text())
        if "editions" in d:
            return [c for e in d["editions"] for c in e["contacts"]]
        return d.get("contacts", d if isinstance(d, list) else [])
    if path.suffix in (".html", ".htm"):
        sys.path.insert(0, str(Path(__file__).parent))
        from datetime import date
        from avocado_pap.ingest.sources import CivicOperatorBriefing
        return CivicOperatorBriefing(path.read_text(), date.today()).contacts()
    if path.suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            sys.exit("pip install pypdf to read PDFs, or export the briefing as HTML")
        text = "\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages)
        rows = []
        for m in re.finditer(
                r"([A-Z][a-zA-Z.'\u2019-]+(?:\s+[A-Z][a-zA-Z.'\u2019-]+){1,3})\s+"
                r"([A-Z][^\n|]{3,70}?)\s+([\w.+-]+@[\w.-]+\.\w{2,})", text):
            rows.append({"name": m.group(1).strip(), "title": m.group(2).strip(),
                         "organization": "", "email": m.group(3), "verification": 1})
        return rows
    sys.exit(f"unsupported file type: {path.suffix}")


def verify_mx(domains: list[str]) -> dict:
    try:
        import dns.resolver
    except ImportError:
        print("  (pip install dnspython for MX verification — skipping)", file=sys.stderr)
        return {}
    out = {}
    for d in domains:
        try:
            dns.resolver.resolve(d, "MX")
            out[d] = True
        except Exception:
            out[d] = False
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--csv", help="write resolved contacts to this path")
    ap.add_argument("--verify", action="store_true", help="MX-check inferred domains")
    ap.add_argument("--min-confidence", type=float, default=0.35)
    a = ap.parse_args()

    contacts = load_contacts(Path(a.source))
    if not contacts:
        sys.exit("no contacts parsed")

    patterns = learn_patterns(contacts)
    org_domains = {}
    for c in contacts:
        if c.get("email") and "@" in c["email"] and c.get("organization"):
            org_domains.setdefault(c["organization"], c["email"].rsplit("@", 1)[1])

    print(f"parsed {len(contacts)} contacts")
    verified = sum(1 for c in contacts if c.get("verification", 1) >= 3)
    print(f"  source-verified by Civic Operator : {verified}")
    print(f"  unsourced                         : {len(contacts) - verified}")

    print(f"\ndomain patterns learned ({len(patterns)}):")
    for dom, p in sorted(patterns.items(), key=lambda kv: -kv[1]["confidence"]):
        flag = "  AMBIGUOUS" if p["ambiguous"] else ""
        print(f"  {dom:<28} {p['pattern']:<12} {p['confirming']}/{p['seen']}"
              f"  conf {p['confidence']:.2f}{flag}")

    resolved, recovered, conform, deviate = [], 0, 0, 0
    for c in contacts:
        row = dict(c)
        row["role"] = classify_role(c.get("title", ""))
        row["email_verified"] = c.get("email") if c.get("verification", 1) >= 3 else None
        row["email_published"] = c.get("email")
        inf = infer(c, patterns, org_domains)
        if inf and inf["confidence"] >= a.min_confidence:
            row.update(inf)
            recovered += 1
        chk = validate(c, patterns)
        if chk:
            row.update(chk)
            if chk["pattern_check"] == "conforms":
                conform += 1
            else:
                deviate += 1
        resolved.append(row)

    roles = Counter(r["role"] for r in resolved)
    print(f"\nroles: " + "  ".join(f"{k}={v}" for k, v in roles.most_common()))
    print(f"\nunsourced addresses checked against their domain pattern:")
    print(f"  conform  : {conform}  (corroborated, safe to sequence)")
    print(f"  deviate  : {deviate}  (review before sending -- pattern exception or error)")
    print(f"addresses recovered where none was published: {recovered}")
    for r in resolved:
        if r.get("pattern_check") == "deviates":
            print(f"    ! {r['name']:<22} {r.get('email','')!s:<34} "
                  f"expected {r['expected_local']}@{r['email'].rsplit('@',1)[1]}")
    champions = [r for r in resolved if r["role"] == "champion"]
    print(f"champions (the actual entry point, per doc 04 §2): {len(champions)}")

    if a.verify:
        doms = sorted({r["email_inferred"].rsplit("@", 1)[1]
                       for r in resolved if r.get("email_inferred")})
        if doms:
            print("\nMX verification:")
            for d, ok in verify_mx(doms).items():
                print(f"  {d:<28} {'accepts mail' if ok else 'NO MX RECORD'}")

    if a.csv:
        cols = ["name", "title", "role", "organization", "state", "opportunity",
                "email_published", "email_verified", "email_inferred", "pattern",
                "confidence", "basis", "pattern_check", "expected_local",
                "check_confidence", "verification"]
        with open(a.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            w.writerows(resolved)
        print(f"\nwrote {a.csv}")
        print("Note: email_verified and email_inferred are separate columns on purpose.")
        print("Never merge them. An inferred address that bounces is recoverable;")
        print("an inferred address filed as verified poisons the CRM permanently.")


if __name__ == "__main__":
    main()
