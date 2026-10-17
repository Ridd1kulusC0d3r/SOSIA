"""Modelos de dados. Separa existência, semelhança, vínculo, evidência de abuso, severidade e confiança."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .textutil import skeleton, slugify


class Priority(str, Enum):
    CRITICAL = "CRITICO"
    HIGH = "ALTO"
    MEDIUM = "MEDIO"
    LOW = "BAIXO"
    INFO = "INFO"

    @property
    def rank(self) -> int:
        return {"CRITICO": 4, "ALTO": 3, "MEDIO": 2, "BAIXO": 1, "INFO": 0}[self.value]


class Existence(str, Enum):
    CONFIRMED = "confirmed"
    PROBABLE = "probable"
    NOT_FOUND = "not_found"
    INCONCLUSIVE = "inconclusive"


@dataclass
class Brand:
    name: str
    handle: str
    display_names: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    official: dict[str, set[str]] = field(default_factory=dict)  # plataforma|"*" -> handles autorizados
    extra_affixes: list[str] = field(default_factory=list)
    ambiguous: bool = False   # a marca é palavra comum (washington, privacy…): limita a prioridade a ALTO

    @property
    def names(self) -> list[str]:
        return list(dict.fromkeys([self.name, *self.display_names]))

    @property
    def slug(self) -> str:
        return slugify(self.handle) or slugify(self.name)

    @property
    def skeleton_slug(self) -> str:
        return skeleton(self.slug)

    def is_official(self, platform_id: str, username: str) -> bool:
        u = username.lower()
        return u in self.official.get(platform_id, set()) or u in self.official.get("*", set())

    def official_handles(self, platform_id: str) -> set[str]:
        return set(self.official.get(platform_id, set())) | set(self.official.get("*", set()))


@dataclass
class Signal:
    id: str
    group: str
    weight: float
    levers: list[str]
    evidence: str
    negated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "group": self.group, "weight": self.weight, "levers": self.levers,
                "evidence": self.evidence, "negated": self.negated}


@dataclass
class SignalReport:
    signals: list[Signal] = field(default_factory=list)
    mitigators: list[Signal] = field(default_factory=list)
    domains: list[dict[str, Any]] = field(default_factory=list)
    levers: list[str] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)
    abuse_level: str = "none"          # none | weak | moderate | strong
    abuse_score: float = 0.0
    brand_mention: bool = False
    claims_authority: bool = False
    disclaimed: bool = False
    links_authorized_domain: bool = False
    bio_available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "abuse_level": self.abuse_level, "abuse_score": round(self.abuse_score, 3), "groups": self.groups,
            "levers": self.levers, "brand_mention": self.brand_mention, "claims_authority": self.claims_authority,
            "disclaimed": self.disclaimed, "links_authorized_domain": self.links_authorized_domain,
            "bio_available": self.bio_available,
            "signals": [s.to_dict() for s in self.signals], "mitigators": [s.to_dict() for s in self.mitigators],
            "domains": self.domains,
        }


@dataclass
class Assessment:
    priority: Priority
    existence_confidence: float
    similarity: float
    affiliation: str            # authorized | unknown | disclaimed | claims_link
    abuse_level: str
    severity: str               # impacto potencial: financeiro | credencial | reputacao | baixo
    confidence: float
    needs_review: bool
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"priority": self.priority.value, "existence_confidence": round(self.existence_confidence, 2),
                "similarity": round(self.similarity, 3), "affiliation": self.affiliation,
                "abuse_level": self.abuse_level, "severity": self.severity,
                "confidence": round(self.confidence, 2), "needs_review": self.needs_review, "reasons": self.reasons}


@dataclass
class Finding:
    platform: str
    username: str
    url: str
    existence: Existence
    reason: str
    variant: dict[str, Any] = field(default_factory=dict)
    profile: dict[str, Any] | None = None
    signals: dict[str, Any] | None = None
    assessment: Assessment | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    raw_body: bytes | None = field(default=None, repr=False)

    @property
    def id(self) -> str:
        return hashlib.sha1(f"{self.platform}|{self.username}".encode()).hexdigest()[:10]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "platform": self.platform, "username": self.username, "url": self.url,
            "existence": self.existence.value, "reason": self.reason, "variant": self.variant,
            "profile": self.profile, "signals": self.signals,
            "assessment": self.assessment.to_dict() if self.assessment else None, "evidence": self.evidence,
        }


@dataclass
class ScanResult:
    meta: dict[str, Any]
    brand: dict[str, Any]
    calibrations: list[Any]            # list[calibrate.Calibration]
    findings: list[Finding]
    stats: dict[str, Any]

    def sorted_findings(self) -> list[Finding]:
        def key(f: Finding) -> tuple:
            a = f.assessment
            return (-(a.priority.rank if a else -1), -(a.confidence if a else 0), f.platform, f.username)
        return sorted(self.findings, key=key)

    def to_dict(self) -> dict[str, Any]:
        return {"meta": self.meta, "brand": self.brand,
                "calibrations": [c.to_dict() for c in self.calibrations],
                "stats": self.stats, "findings": [f.to_dict() for f in self.sorted_findings()]}
