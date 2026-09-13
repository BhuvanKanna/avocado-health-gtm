"""
Typed records and the provenance envelope.

Design rule inherited from Civic Operator: "the machine finds, the operator
vouches." Every atomic fact carries where it came from, when it was read, and
whether a human has confirmed it. Model-inferred values may never silently
overwrite a human-verified value; the merge policy in `Provenanced.merge`
enforces that ordering.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from enum import IntEnum
from typing import Any, Generic, Optional, TypeVar

T = TypeVar("T")


class Verification(IntEnum):
    """Ordered by authority. Higher always wins a merge."""
    INFERRED = 0        # model or heuristic produced this
    ENRICHED = 1        # third-party vendor / derived join
    MACHINE_READ = 2    # scraped verbatim from a primary public page
    OPERATOR = 3        # a human read the page and vouched
    CONTRACTUAL = 4     # appears in an executed document


@dataclass
class Provenanced(Generic[T]):
    value: T
    source_url: Optional[str] = None
    retrieved_at: Optional[date] = None
    verification: Verification = Verification.INFERRED
    verifier: Optional[str] = None
    note: Optional[str] = None

    def merge(self, other: "Provenanced[T]") -> "Provenanced[T]":
        """Higher verification wins. Ties break toward the more recent read."""
        if other.verification > self.verification:
            return other
        if other.verification < self.verification:
            return self
        a, b = self.retrieved_at or date.min, other.retrieved_at or date.min
        return other if b >= a else self

    @property
    def is_actionable(self) -> bool:
        """Below MACHINE_READ, a field should be shown but not acted on."""
        return self.verification >= Verification.MACHINE_READ


def P(value, url=None, when=None, level=Verification.INFERRED, by=None, note=None):
    return Provenanced(value, url, when, level, by, note)


# --------------------------------------------------------------------------
# Core entities. Field names align with 04 §7 so the dashboard is a rendering
# job and not a rebuild.
# --------------------------------------------------------------------------

SEGMENTS = ("OB", "ABA", "CBO", "HR", "FQHC", "GOV", "RHS", "MCO",
            "BRK", "API", "CW", "K12", "SCH", "FDN")

# Staff roles whose time Avocado gives back. Detecting these is the single
# most Avocado-specific signal in the feature set (01 §5, 06 §2).
OFFLOAD_ROLES = ("community_health_worker", "home_visitor", "doula",
                 "lactation_consultant", "healthysteps_specialist",
                 "care_coordinator", "perinatal_mental_health",
                 "family_resource_navigator", "parent_educator")


@dataclass
class Organization:
    org_id: str
    name: str
    segment_code: str
    state: str
    county_fips: Optional[str] = None
    ein: Optional[str] = None
    uei: Optional[str] = None
    ntee_code: Optional[str] = None
    website: Optional[str] = None
    total_revenue: Optional[float] = None
    govt_grant_revenue: Optional[float] = None
    employees: Optional[int] = None
    incumbent_platform: Optional[str] = None
    program_text: str = ""            # 990 Part III + site copy, concatenated
    staff_model: dict[str, float] = field(default_factory=dict)
    fields: dict[str, Provenanced] = field(default_factory=dict)

    @property
    def grant_dependency(self) -> float:
        if not self.total_revenue:
            return 0.0
        return min(1.0, (self.govt_grant_revenue or 0.0) / self.total_revenue)


@dataclass
class Award:
    award_id: str
    recipient_org_id: str
    assistance_listing: str           # e.g. 93.798 RHTP, 93.505 MIECHV
    prime_award_id: Optional[str]     # null => this IS a prime
    obligated: float
    action_date: date
    state: str
    program_label: str = ""

    @property
    def is_subaward(self) -> bool:
        return self.prime_award_id is not None


@dataclass
class Solicitation:
    """A funding event. Includes forthcoming ones inferred from leading
    indicators (RFIs, plan documents, appropriation lines), not just posted."""
    opp_id: str
    title: str
    issuer: str
    state: str
    assistance_listing: str
    status: str                       # signal|forthcoming|posted|closed|awarded
    posted_date: Optional[date]
    close_date: Optional[date]
    ceiling: Optional[float]
    expected_awards: Optional[int]
    eligible_county_fips: tuple[str, ...] = ()
    eligible_org_types: tuple[str, ...] = ()
    text: str = ""
    # extracted by ingest.solicitation — these drive Model C
    subgrants_permitted: Optional[bool] = None
    partnerships_permitted: Optional[bool] = None
    technology_allowable: Optional[bool] = None
    eval_weight_innovation: Optional[float] = None
    eval_weight_equity: Optional[float] = None
    fields: dict[str, Provenanced] = field(default_factory=dict)


@dataclass
class Contact:
    contact_id: str
    org_id: str
    name: str
    title: str
    role: Optional[str] = None        # economic_buyer|champion|gatekeeper
    email: Optional[Provenanced] = None
    linkedin: Optional[str] = None
    warm_path_via: Optional[str] = None
    personalization_hook: Optional[str] = None


@dataclass
class Prediction:
    """One scored (solicitation, organization) pair."""
    opp_id: str
    org_id: str
    p_win: float                      # Model A, isotonic-calibrated
    p_fit: float                      # Model B, PU-corrected
    p_role: float                     # Model C, Avocado can sit as sub
    expected_acv: float
    reach: float                      # warm-path multiplier
    time_discount: float
    eav: float                        # expected Avocado value, dollars
    conformal_set: bool               # inside the 90% coverage set
    rubric: dict[str, int] = field(default_factory=dict)   # 04 §4 bridge
    attribution: list[tuple[str, float]] = field(default_factory=list)
    rationale: str = ""
    data_completeness: float = 1.0
    flags: list[str] = field(default_factory=list)


def stable_id(*parts: Any) -> str:
    h = hashlib.sha1("||".join(str(p) for p in parts).encode()).hexdigest()
    return h[:12]


def to_row(obj) -> dict:
    d = asdict(obj)
    for k, v in list(d.items()):
        if isinstance(v, (date, datetime)):
            d[k] = v.isoformat()
    return d
