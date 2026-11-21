"""Unknown-form fallback.

TODO(browser-use): plug a browser-use agent in behind `FormFallback` to map fields of
forms no adapter knows. The contract below is what keeps it safe, whatever implements it:

- it receives EVERY field of the form and must report every key it intends to touch in
  `FallbackPlan.intended` (the engine skips the application if any field is missing);
- a proposal is used only with confidence >= APPLY_FALLBACK_MIN_CONFIDENCE and a source
  from the allowed set (profile, settings, saved, drafted, user): it may map a field
  to an existing real value, never invent one;
- any required field still without a value afterwards means: skip, never submit.
"""

from dataclasses import dataclass, field
from typing import Protocol

from app.apply.fields import FormField, Planned


@dataclass
class Proposal:
    key: str
    value: str
    source: str
    confidence: float


@dataclass
class FallbackPlan:
    intended: list[str] = field(default_factory=list)  # every field key considered
    proposals: list[Proposal] = field(default_factory=list)


class FormFallback(Protocol):
    def propose(self, fields: list[FormField], plan: list[Planned]) -> FallbackPlan: ...


class ConservativeFallback:
    """Maps nothing beyond what the standard mapper already did."""

    def propose(self, fields: list[FormField], plan: list[Planned]) -> FallbackPlan:
        return FallbackPlan(intended=[f.key for f in fields], proposals=[])
