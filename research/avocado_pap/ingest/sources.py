"""
Ingest adapters.

Every adapter obeys the same contract: it returns typed records with a
Provenanced envelope on any field a human might later dispute, and it accepts
an `as_of` date so historical feature computation cannot leak the future.

Network calls are isolated behind `fetch_json` / `fetch_text`. In offline mode
the adapters read from cached fixtures, which is also how the test suite and
the temporal backtest run deterministically.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Optional

from ..schema import (Award, Contact, Organization, Provenanced, Solicitation,
                      Verification, P, stable_id)

CACHE = Path(os.environ.get("PAP_CACHE", "./.pap_cache"))
CACHE.mkdir(exist_ok=True, parents=True)

# Assistance listings that constitute the "adjacent prior work" universe.
# A prior award under any of these is evidence the org can win RHTP money.
LISTINGS = {
    "93.798": "Rural Health Transformation Program",
    "93.505": "MIECHV — Maternal, Infant and Early Childhood Home Visiting",
    "93.926": "Healthy Start Initiative",
    "93.994": "MCH Services Block Grant (Title V)",
    "93.110": "MCH Federal Consolidated Programs",
    "93.224": "Health Center Program (FQHC 330)",
    "93.912": "Rural Health Care Services Outreach",
    "93.870": "Nurse-Family Partnership / home visiting adjacent",
    "93.558": "TANF (state early-childhood pass-through)",
    "93.600": "Head Start",
}


# ---------------------------------------------------------------------------
# USAspending — prime awards and the first/second-tier subaward cascade
# ---------------------------------------------------------------------------

class USASpending:
    """Subaward cascade reader.

    The cascade is the map of where RHTP money actually is:

        CMS appropriation
          -> state prime award            (award_id RHTCMS3320xx)
            -> first-tier subrecipient    (county health dept, hospital, CBO)
              -> second-tier subrecipient (the CBO the county passes through to)

    Two derived quantities matter more than anything else the API returns:

      unobligated_remainder = prime_obligation - sum(first_tier_subawards)
        -> how much money the state still has to move. Ranks states.

      cascade_depth(org) = how far down the chain an org typically sits
        -> orgs that appear at tier 2 are the ones that need a *partner*,
           which is precisely Avocado's slot (04 §2).
    """

    BASE = "https://api.usaspending.gov/api/v2"

    def __init__(self, offline: bool = True, fixture_dir: Optional[Path] = None):
        self.offline = offline
        self.fixture_dir = fixture_dir or CACHE / "usaspending"
        self.fixture_dir.mkdir(exist_ok=True, parents=True)

    def _read_fixture(self, key: str):
        p = self.fixture_dir / f"{key}.json"
        return json.loads(p.read_text()) if p.exists() else None

    def prime_awards(self, listing: str, as_of: date) -> list[dict]:
        raw = self._read_fixture(f"prime_{listing}") or []
        return [r for r in raw
                if date.fromisoformat(r["action_date"]) <= as_of]

    def subawards(self, prime_award_id: str, as_of: date) -> list[dict]:
        raw = self._read_fixture(f"sub_{prime_award_id}") or []
        return [r for r in raw
                if date.fromisoformat(r["action_date"]) <= as_of]

    def cascade(self, listing: str, as_of: date) -> dict:
        """Full flow-down graph plus the unobligated remainder per state."""
        out = {"primes": [], "state_remainder": {}}
        for pr in self.prime_awards(listing, as_of):
            subs = self.subawards(pr["award_id"], as_of)
            moved = sum(s["obligated"] for s in subs)
            out["primes"].append({**pr, "subawards": subs, "moved": moved})
            st = pr["state"]
            rem = out["state_remainder"].setdefault(
                st, {"obligated": 0.0, "moved": 0.0})
            rem["obligated"] += pr["obligated"]
            rem["moved"] += moved
        for st, r in out["state_remainder"].items():
            r["remainder"] = r["obligated"] - r["moved"]
            r["pct_unmoved"] = (r["remainder"] / r["obligated"]
                                if r["obligated"] else 0.0)
        return out


# ---------------------------------------------------------------------------
# Solicitation document intelligence — drives Model C (role fit)
# ---------------------------------------------------------------------------

# Whether Avocado can legally sit inside a deal is Qualify gate 4 (04 §5) and
# is currently answered by a human reading a PDF. These patterns turn that into
# a field. Each returns (bool, evidence_span) so the answer is auditable.
_SUBGRANT_PAT = re.compile(
    r"(may|are permitted to|are encouraged to|at the .{0,30}discretion.{0,20})?"
    r"\s*(sub-?grant|sub-?award|sub-?contract|pass[- ]through)\w*", re.I)
_PARTNER_PAT = re.compile(
    r"(partnership|collaborat\w+|consorti\w+|memorand\w+ of understanding|"
    r"letters? of (support|commitment))", re.I)
_TECH_PAT = re.compile(
    r"(technolog\w+|software|platform|licens\w+|digital health|telehealth|"
    r"remote (patient|therapeutic) monitoring|text messag\w+|SMS)", re.I)
_PROHIBIT_PAT = re.compile(
    r"(may not|shall not|are prohibited from|is not an allowable)"
    r"[^.]{0,80}(sub-?award|sub-?contract|sub-?grant)", re.I)
_EVAL_PAT = re.compile(
    r"([A-Z][A-Za-z /&-]{4,60}?)\s*[\.\-–—:]?\s*\(?(\d{1,2})\s*(?:points|pts|%)\)?", re.I)


def extract_solicitation_fields(text: str, url: str = None,
                                when: date = None) -> dict:
    """Structured extraction from solicitation prose.

    Returns Provenanced values at MACHINE_READ level with the matched span as
    the note, so the briefing can print the sentence that produced the answer.
    """
    res: dict[str, Provenanced] = {}

    prohibited = _PROHIBIT_PAT.search(text)
    sub = _SUBGRANT_PAT.search(text)
    if prohibited:
        res["subgrants_permitted"] = P(False, url, when, Verification.MACHINE_READ,
                                       note=prohibited.group(0)[:200])
    elif sub:
        res["subgrants_permitted"] = P(True, url, when, Verification.MACHINE_READ,
                                       note=sub.group(0)[:200])

    pm = _PARTNER_PAT.search(text)
    if pm:
        res["partnerships_permitted"] = P(True, url, when, Verification.MACHINE_READ,
                                          note=pm.group(0)[:200])

    tm = _TECH_PAT.search(text)
    if tm:
        res["technology_allowable"] = P(True, url, when, Verification.MACHINE_READ,
                                        note=tm.group(0)[:200])

    weights = {}
    for label, pts in _EVAL_PAT.findall(text):
        weights[label.strip().lower()] = float(pts)
    total = sum(weights.values()) or 1.0
    for key, needles in (("eval_weight_innovation",
                          ("innovat", "technolog", "approach")),
                         ("eval_weight_equity",
                          ("equit", "access", "underserved", "rural"))):
        hit = sum(v for k, v in weights.items() if any(n in k for n in needles))
        if hit:
            res[key] = P(hit / total, url, when, Verification.MACHINE_READ)
    return res


# ---------------------------------------------------------------------------
# Civic Operator briefing parser — turns the daily HTML into typed records
# ---------------------------------------------------------------------------

class CivicOperatorBriefing:
    """Parse a daily Civic Operator HTML briefing into records.

    The briefing is a publication with no yesterday. Parsing each edition into
    immutable snapshots is what makes the diff engine possible: a contact
    flipping from 'Not published' to source-verified, a due date moving, or a
    subaward cohort growing are all outreach triggers that are invisible if you
    only ever read today's edition.
    """

    ROW = re.compile(r"<tr>(.*?)</tr>", re.S)
    CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)
    TAG = re.compile(r"<[^>]+>")
    MAILTO = re.compile(r"mailto:([^\"'>]+)")

    def __init__(self, html: str, edition: date):
        self.html = html
        self.edition = edition

    def _clean(self, s: str) -> str:
        return self.TAG.sub("", s).replace("&amp;", "&").strip()

    def contacts(self) -> list[dict]:
        out = []
        for rowhtml in self.ROW.findall(self.html):
            cells = self.CELL.findall(rowhtml)
            if len(cells) != 7:
                continue
            opp, name, title, org, email_c, phone, source_c = cells
            name = self._clean(name)
            if name.lower().startswith("contact") or not name:
                continue
            m = self.MAILTO.search(email_c)
            source_url = None
            sm = re.search(r'href="(https?://[^"]+)"', source_c)
            if sm:
                source_url = sm.group(1)
            # This is the field the whole thing turns on: Civic Operator marks
            # rows it could not source. Those are candidates for the resolution
            # pipeline, not facts.
            published = "not published" not in self._clean(source_c).lower()
            out.append({
                "opportunity": self._clean(opp),
                "name": name,
                "title": self._clean(title),
                "organization": self._clean(org),
                "email": m.group(1) if m else None,
                "phone": self._clean(phone),
                "source_url": source_url,
                "verification": (Verification.OPERATOR if published
                                 else Verification.ENRICHED),
                "edition": self.edition.isoformat(),
            })
        return out

    def opportunities(self) -> list[dict]:
        out = []
        for block in re.findall(r'<article class="opp[^"]*">(.*?)</article>',
                                self.html, re.S):
            h = re.search(r"<h3[^>]*>(.*?)</h3>", block, re.S)
            title = self._clean(h.group(1)) if h else ""
            title = re.sub(r"^\d+", "", title).strip()
            due = re.search(r'class="due">([^<]+)<', block)
            issuer = re.search(r"Sponsoring organization\.</span>\s*([^<]+)", block)
            out.append({
                "title": title,
                "issuer": self._clean(issuer.group(1)) if issuer else None,
                "due_raw": due.group(1).strip() if due else None,
                "urls": re.findall(r'href="(https?://[^"]+)"', block),
                "edition": self.edition.isoformat(),
            })
        return out


# ---------------------------------------------------------------------------
# Diff engine — the reason snapshots are stored at all
# ---------------------------------------------------------------------------

TRIGGER_WEIGHTS = {
    "contact_verified": 0.9,     # unsourced row became source-verified
    "new_contact": 0.7,
    "deadline_moved": 1.0,       # highest: silently invalidates a plan
    "new_subaward": 0.85,        # a new named prospect with money in hand
    "opportunity_added": 0.8,
    "opportunity_dropped": 0.6,
    "title_changed": 0.4,
    "email_added": 0.75,
    "duplicate_key": 0.5,   # parser fault, not a market event
}


def row_key(row: dict, fields: tuple[str, ...]) -> str:
    """Composite identity for a briefing row.

    Keying on a single field is wrong and fails silently. The 2026-09-03
    edition contains the literal name "No named individual published" five
    times across five different agencies; keying on name alone collapses them
    to one row and every change to the other four becomes invisible. Identity
    here is (what it is about, who it is, where they work).
    """
    return "\u241f".join(str(row.get(f, "") or "").strip().lower()
                         for f in fields)


CONTACT_KEY = ("opportunity", "name", "organization")
OPP_KEY = ("title",)


def diff_editions(prev: list[dict], curr: list[dict],
                  key_fields: tuple[str, ...] = CONTACT_KEY) -> list[dict]:
    """Field-level delta between two briefing editions.

    Collisions are surfaced rather than swallowed: if two rows in one edition
    share a composite key, that is a parser problem and it gets its own event
    instead of one row quietly winning.
    """
    def index(rows):
        out, dupes = {}, set()
        for r in rows:
            k = row_key(r, key_fields)
            if k in out:
                dupes.add(k)
            out[k] = r
        return out, dupes

    pi, _ = index(prev)
    ci, cdupes = index(curr)
    events = []

    for k in cdupes:
        events.append({"type": "duplicate_key", "key": k, "row": ci[k]})

    for k, row in ci.items():
        if k not in pi:
            events.append({"type": "new_contact" if "name" in key_fields
                           else "opportunity_added", "key": k, "row": row})
            continue
        old = pi[k]
        if old.get("verification", 0) < row.get("verification", 0):
            events.append({"type": "contact_verified", "key": k,
                           "from": old.get("verification"),
                           "to": row.get("verification"), "row": row})
        if not old.get("email") and row.get("email"):
            events.append({"type": "email_added", "key": k, "row": row})
        if old.get("due_raw") and old.get("due_raw") != row.get("due_raw"):
            events.append({"type": "deadline_moved", "key": k,
                           "from": old["due_raw"], "to": row.get("due_raw"),
                           "row": row})
        if old.get("title") and old.get("title") != row.get("title"):
            events.append({"type": "title_changed", "key": k,
                           "from": old["title"], "to": row.get("title")})

    for k in pi.keys() - ci.keys():
        events.append({"type": "opportunity_dropped", "key": k, "row": pi[k]})

    for e in events:
        e["priority"] = TRIGGER_WEIGHTS.get(e["type"], 0.3)
    return sorted(events, key=lambda e: -e["priority"])
