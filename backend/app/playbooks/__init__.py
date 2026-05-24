"""
Playbook YAML loader and schema validation. A playbook is a structured description
of a customer's acceptable contract positions (e.g., "governing law must be
California", "liability cap must be >= 2x contract value"). Playbooks live in
`data/playbooks/yaml/` (production) and `evals/playbooks/yaml/` (eval fixtures).
The schema is defined with Pydantic v2 so validation errors surface at load time,
not during a deviation run. Supports per-category severity overrides for the
flag layer.
"""
from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, model_validator


class CUADCategory(StrEnum):
    governing_law = "governing_law"
    renewal_term = "renewal_term"
    notice_period_to_terminate_renewal = "notice_period_to_terminate_renewal"
    termination_for_convenience = "termination_for_convenience"
    indemnification = "indemnification"
    confidentiality = "confidentiality"
    anti_assignment = "anti_assignment"
    non_compete = "non_compete"
    cap_on_liability = "cap_on_liability"
    change_of_control = "change_of_control"
    ip_ownership_assignment = "ip_ownership_assignment"
    uncapped_liability = "uncapped_liability"


class Severity(StrEnum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    info = "info"


class Condition(StrEnum):
    eq = "eq"            # extracted value exactly equals required_value
    contains = "contains"  # extracted value contains required_value as substring
    gte = "gte"          # numeric: extracted >= required_value
    lte = "lte"          # numeric: extracted <= required_value
    absent = "absent"    # clause must not be present / extracted is None
    present = "present"  # clause must be present / extracted is not None


class PlaybookRule(BaseModel):
    category: CUADCategory
    condition: Condition
    required_value: str | None = None
    severity: Severity = Severity.high
    description: str | None = None

    @model_validator(mode="after")
    def _required_value_for_value_conditions(self) -> PlaybookRule:
        value_conditions = {Condition.eq, Condition.contains, Condition.gte, Condition.lte}
        if self.condition in value_conditions and self.required_value is None:
            raise ValueError(
                f"required_value must be set when condition is '{self.condition.value}'"
            )
        return self


class Playbook(BaseModel):
    id: str
    name: str
    description: str | None = None
    version: str = "1.0"
    customer_id: str | None = None
    rules: list[PlaybookRule] = Field(default_factory=list)


def load_playbook(path: Path) -> Playbook:
    """Load and validate a single playbook YAML file. Raises ValidationError on bad schema."""
    raw: Any = yaml.safe_load(path.read_text())
    return Playbook.model_validate(raw)


def load_all_playbooks(directory: Path) -> dict[str, Playbook]:
    """Load every *.yaml / *.yml file in directory. Keys are playbook IDs."""
    playbooks: dict[str, Playbook] = {}
    if not directory.exists():
        return playbooks
    for path in sorted([*directory.glob("*.yaml"), *directory.glob("*.yml")]):
        pb = load_playbook(path)
        playbooks[pb.id] = pb
    return playbooks
