from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator

class Evidence(BaseModel):
    id: str = Field(min_length=1, max_length=90)
    kind: str = Field(min_length=1, max_length=90)
    reference: str | None = Field(default=None, max_length=250)
    excerpt: str | None = Field(default=None, max_length=600)
    # Use only extracts authorized for the purpose; never attach patient identifiers by default.

class AccountInput(BaseModel):
    account_ref: str = Field(min_length=1, max_length=120)
    payer: str | None = Field(default=None, max_length=180)
    modality: str | None = Field(default=None, max_length=120)
    service_type: str | None = Field(default=None, max_length=120)
    issued_on: date | None = None
    facts: dict[str, Any] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list, max_length=150)

class ObjectionInput(BaseModel):
    objection_ref: str = Field(min_length=1, max_length=120)
    account: AccountInput
    kind: Literal["GLOSA", "DEVOLUCION"]
    code: str | None = Field(default=None, max_length=30)
    description: str = Field(min_length=1, max_length=3000)
    amount: Decimal | None = Field(default=None, ge=0)
    notified_on: date | None = None
    facts: dict[str, Any] = Field(default_factory=dict)

class RuleCheck(BaseModel):
    field: str = Field(min_length=1, max_length=180, pattern=r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*$")
    operator: Literal["exists", "eq", "neq", "in", "gte", "lte", "gt", "lt"]
    value: Any = None

    @model_validator(mode="after")
    def require_comparable_value(self):
        if self.operator != "exists" and self.value is None:
            raise ValueError("Comparison requires an expected value")
        if self.operator == "in" and not isinstance(self.value, (list, tuple, set)):
            raise ValueError("Membership comparison requires a list")
        return self

class RuleDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule_key: str = Field(min_length=2, max_length=120, pattern=r"^[a-zA-Z0-9_.-]+$")
    name: str = Field(min_length=2, max_length=180)
    phase: Literal["PREVENT", "RESPOND", "BOTH"]
    category: str = Field(min_length=2, max_length=90)
    scope: dict[str, str] = Field(default_factory=dict)
    when: RuleCheck | None = None
    check: RuleCheck
    evidence_kinds: list[str] = Field(default_factory=list, max_length=30)
    severity: Literal["LOW", "MEDIUM", "HIGH"] = "MEDIUM"
    finding: str = Field(min_length=5, max_length=700)
    recommendation: str = Field(min_length=5, max_length=1200)
    source_ref: str | None = Field(default=None, max_length=350)
    response_action: Literal["CONTROVERTIR", "SUBSANAR", "ACEPTAR", "ESCALAR"] | None = None
    response_template: str | None = Field(default=None, max_length=3000)
    effective_from: date | None = None
    effective_until: date | None = None

    @field_validator("scope")
    @classmethod
    def validate_scope(cls, value: dict[str, str]):
        if len(value) > 20 or any(k not in {"payer", "modality", "service_type", "objection_kind", "objection_code"} for k in value):
            raise ValueError("Scope must use payer, modality, service_type, objection_kind or objection_code")
        return value

class MappingDefinition(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    source_type: Literal["CSV", "JSON"]
    columns: dict[str, str] = Field(min_length=1, max_length=120)
    # Columns: account_ref, payer, modality, service_type, issued_on,
    # or facts.any_nested_attribute. Values are source column names.

class PreventBatch(BaseModel):
    accounts: list[AccountInput] = Field(min_length=1, max_length=500)

class RespondBatch(BaseModel):
    objections: list[ObjectionInput] = Field(min_length=1, max_length=500)

class TenantInput(BaseModel):
    name: str = Field(min_length=2, max_length=200)
