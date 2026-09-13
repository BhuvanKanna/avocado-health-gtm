"""
Builds the real-data payload the dashboard ships with.

Everything here is primary-source or parsed from a document Avocado already
holds. Nothing is generated. The provenance of each block is recorded in the
payload itself so the dashboard can show it.
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'research'))
from avocado_pap.ingest.sources import CivicOperatorBriefing

# CMS, "CMS Announces $50 Billion in Awards to Strengthen Rural Health in All
# 50 States," 2025-12-29. FY26 award amounts, verbatim from the State Award
# List table in the press release.
CMS_FY26 = {
    "AL": 203404327, "AK": 272174856, "AZ": 166988956, "AR": 208779396,
    "CA": 233639308, "CO": 200105604, "CT": 154249106, "DE": 157394964,
    "FL": 209938195, "GA": 218862170, "HI": 188892440, "ID": 185974368,
    "IL": 193418216, "IN": 206927897, "IA": 209040064, "KS": 221898008,
    "KY": 212905591, "LA": 208374448, "ME": 190008051, "MD": 168180838,
    "MA": 162005238, "MI": 173128201, "MN": 193090618, "MS": 205907220,
    "MO": 216276818, "MT": 233509359, "NE": 218529075, "NV": 179931608,
    "NH": 204016550, "NJ": 147250806, "NM": 211484741, "NY": 212058208,
    "NC": 213008356, "ND": 198936970, "OH": 202030262, "OK": 223476949,
    "OR": 197271578, "PA": 193294054, "RI": 156169931, "SC": 200030252,
    "SD": 189477607, "TN": 206888882, "TX": 281319361, "UT": 195743566,
    "VT": 195053740, "VA": 189544888, "WA": 181257515, "WV": 199476099,
    "WI": 203670005, "WY": 205004743,
}

STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut",
    "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine",
    "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
    "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri",
    "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota",
    "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming",
}

# Observed first-tier subaward movement, accumulated across editions. A state
# absent here has no observed movement, which is itself the signal -- but note
# it is also what a state looks like before anyone has looked. The "observed"
# flag in the payload keeps those two cases distinguishable.
sys.path.insert(0, str(Path(__file__).parent / 'editions'))
from edition_0910 import SUBAWARDS as _SUB_0910
OBSERVED_SUBAWARDS = dict(_SUB_0910)

# Avocado segment economics. Source: ICP Matrix, August 2026 (project doc 02
# §2). ACV midpoints and cycle lengths only -- no partner terms.
SEGMENTS = {
    "RHS": {"label": "Rural hospital / health system", "acv": 62500,
            "cycle_months": 15, "tier": 2},
    "FQHC": {"label": "FQHC / community health center", "acv": 220000,
             "cycle_months": 6.5, "tier": 1.5},
    "CBO": {"label": "CBO / parent advocacy", "acv": 37500,
            "cycle_months": 4.5, "tier": 1},
    "OB": {"label": "Perinatal / maternal network", "acv": 60000,
           "cycle_months": 4.5, "tier": 1},
    "GOV": {"label": "State / local public health", "acv": 400000,
            "cycle_months": 12, "tier": 1.5},
    "SCH": {"label": "School district / early childhood", "acv": 50000,
            "cycle_months": 6, "tier": 3},
    "ASSOC": {"label": "State association (channel)", "acv": 0,
              "cycle_months": 3, "tier": 1},
    "ABA": {"label": "ABA / behavioral health clinic", "acv": 45000,
            "cycle_months": 2, "tier": 1},
    "EDU": {"label": "University / academic", "acv": 50000,
            "cycle_months": 9, "tier": 3},
}

# Organization -> segment. Assigned by reading the organization name and its
# role in the briefing. Where a call is genuinely ambiguous it is marked so the
# dashboard can show it as unconfirmed rather than asserting.
ORG_SEGMENT = {
    "Harrison County Community Hospital": ("RHS", True),
    "Mosaic Life Care": ("RHS", True),
    "HCC Network": ("FQHC", True),
    "Lake Regional Health System": ("RHS", True),
    "Arthur Center Community Health": ("FQHC", True),
    "Missouri Highlands Health Care": ("FQHC", True),
    "FCC Behavioral Health": ("ABA", True),
    "Community Counseling Center": ("ABA", True),
    "Phelps Health": ("RHS", True),
    "Hermann Area District Hospital": ("RHS", True),
    "Hannibal Regional Health Center": ("RHS", True),
    "A.T. Still University of Health Sciences – Kirksville": ("EDU", True),
    "Idaho Community Health Centers Association": ("ASSOC", True),
    "Idaho Hospital Association": ("ASSOC", True),
    "Jannus": ("CBO", True),
    "UofL Health – Shelbyville Hospital": ("RHS", True),
    "Commonwealth of Kentucky": ("GOV", False),
}

ORG_STATE = {
    "Harrison County Community Hospital": "MO", "Mosaic Life Care": "MO",
    "HCC Network": "MO", "Lake Regional Health System": "MO",
    "Arthur Center Community Health": "MO",
    "Missouri Highlands Health Care": "MO", "FCC Behavioral Health": "MO",
    "Community Counseling Center": "MO", "Phelps Health": "MO",
    "Hermann Area District Hospital": "MO",
    "Hannibal Regional Health Center": "MO",
    "A.T. Still University of Health Sciences – Kirksville": "MO",
    "Idaho Community Health Centers Association": "ID",
    "Idaho Hospital Association": "ID", "Jannus": "ID",
    "UofL Health – Shelbyville Hospital": "KY",
    "Commonwealth of Kentucky": "KY",
}


def build_states() -> list[dict]:
    equal_share = 100_000_000   # $10B/yr x 50% / 50 states, per PL 119-21
    out = []
    for code, award in CMS_FY26.items():
        obs = OBSERVED_SUBAWARDS.get(code)
        moved = obs["moved"] if obs else None
        out.append({
            "code": code, "name": STATE_NAMES[code], "award": award,
            "discretionary": award - equal_share,
            "moved": moved,
            "recipients": obs["recipients"] if obs else None,
            "prime_award_id": obs["prime_award_id"] if obs else None,
            "remainder": (award - moved) if moved is not None else None,
            "observed": obs is not None,
            "source": obs["source"] if obs else None,
        })
    return sorted(out, key=lambda s: -s["award"])


def build_edition(path: Path, edition: date) -> dict:
    b = CivicOperatorBriefing(path.read_text(), edition)
    contacts, opps = b.contacts(), b.opportunities()
    for c in contacts:
        org = c["organization"]
        seg, confirmed = ORG_SEGMENT.get(org, (None, False))
        # Government bodies are recognisable from the name itself.
        if seg is None:
            g = re.search(r"(Department|Dept\.|Cabinet|Office of Administration|"
                          r"Commonwealth|Division)", org)
            seg, confirmed = ("GOV", bool(g)) if g else (None, False)
        c["segment"] = seg
        c["segment_confirmed"] = confirmed
        c["state"] = ORG_STATE.get(org) or _state_from_org(org)
    return {"edition": edition.isoformat(), "contacts": contacts,
            "opportunities": opps, "source_file": path.name}


def _state_from_org(org: str) -> str | None:
    for needle, code in (("Idaho", "ID"), ("Missouri", "MO"),
                         ("Kentucky", "KY"), ("Commonwealth of Kentucky", "KY")):
        if needle in org:
            return code
    return None


def main():
    here = Path(__file__).resolve().parent
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        here / "briefings" / "2026-09-03-avocado-verified-intelligence.html")
    from edition_0910 import (CONTACTS as C10, OPPORTUNITIES as O10,
                              PARTNER_TARGETS as PT10, EDITION as ED10)
    ed_0910 = {
        "edition": ED10,
        "contacts": [dict(c, opportunity=c.get("opportunity", "")) for c in C10],
        "opportunities": [dict(o, edition=ED10, urls=[]) for o in O10],
        "partner_targets": PT10,
        "source_file": "9-10_Avocado_Verified_Intelligence.pdf",
    }
    payload = {
        "generated": date.today().isoformat(),
        "states": build_states(),
        "segments": SEGMENTS,
        "editions": [build_edition(src, date(2026, 9, 3)), ed_0910],
        "provenance": {
            "cms_awards": {
                "label": "CMS FY26 Rural Health Transformation awards, all 50 states",
                "url": "https://www.cms.gov/newsroom/press-releases/cms-announces-50-billion-awards-strengthen-rural-health-all-50-states",
                "retrieved": date.today().isoformat(),
                "note": "Verbatim from the State Award List table. Assistance listing 93.798.",
            },
            "subawards": {
                "label": "Observed first-tier subaward movement",
                "url": None,
                "retrieved": "2026-09-10",
                "note": "From Civic Operator editions citing USAspending, TAGGS, NYSDOH and NJ DHS. Refresh live via fetch_live.py --all.",
            },
            "segments": {
                "label": "Avocado segment economics",
                "url": None, "retrieved": "2026-08-14",
                "note": "ACV midpoints and cycle lengths from the ICP Matrix (doc 02 §2). No partner terms.",
            },
        },
    }
    (here / "real_data.json").write_text(json.dumps(payload, default=str))
    for e in payload["editions"]:
        print(f"edition {e['edition']}: {len(e['contacts'])} contacts, "
              f"{len(e['opportunities'])} opportunities, "
              f"{len(e.get('partner_targets', []))} partner targets")
    sts = {c["state"] for e in payload["editions"] for c in e["contacts"] if c.get("state")}
    print(f"states with contacts: {len(sts)} — {' '.join(sorted(sts))}")
    obs = [s for s in payload["states"] if s["observed"]]
    print(f"states with observed subawards: {len(obs)}  "
          f"total moved ${sum(s['moved'] or 0 for s in obs):,.0f}")
    print(f"total FY26 obligated: ${sum(CMS_FY26.values()):,}")
    return payload


if __name__ == "__main__":
    main()
