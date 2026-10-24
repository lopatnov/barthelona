"""Run, event, LLM-call and gate models (docs/architecture.md §4 "Runs and events", §5.2, §8)."""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import Field, StringConstraints, model_validator

from barthelona.domain._base import (
    Document,
    DomainModel,
    ItemId,
    NodeId,
    PolicyVersionId,
    RelPath,
    Sha256,
    ShortText,
    Text,
)
from barthelona.domain.enums import CompositionLevel, StopReason
from barthelona.domain.project import TargetProfile

DEMOS_DIR = "demos"
_PROJECT_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,40}")


def project_workspace(name: str) -> str:
    """The `demos/<name>` folder a run's project belongs to; the name is a lowercase slug."""
    if not _PROJECT_NAME.fullmatch(name):
        raise ValueError("use lowercase letters, digits and dashes, starting with a letter or digit")
    return f"{DEMOS_DIR}/{name}"


ProviderId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,31}$")]


class RunMode(StrEnum):
    CREATE = "create"
    EDIT = "edit"


class Profile(StrEnum):
    LOCAL_ONLY = "local-only"
    HYBRID = "hybrid"
    CLOUD = "cloud"
    METERLESS = "meterless"  # the catalog profile that routes through Nightshift (Meterless Runtime)


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_GATE = "waiting_gate"
    DRAINING = "draining"
    STOPPED = "stopped"


class RunBudget(DomainModel):
    """Run limits (§8). `usd = None` means uncapped but still metered per call."""

    wall_s: float = Field(gt=0)
    tokens: int = Field(ge=1)
    usd: float | None = Field(default=None, ge=0)
    max_sprints: int = Field(default=10, ge=1)
    cloud_allowed: bool = False
    allowed_providers: list[ProviderId] = Field(default_factory=list)
    autopilot: bool = False  # G3 accepted automatically when the sprint is green


class Run(Document):
    id: ItemId
    mode: RunMode
    workspace: Annotated[str, StringConstraints(min_length=1, max_length=1024)]  # workspace directory
    target: TargetProfile
    profile: Profile = Profile.LOCAL_ONLY
    policy_version: PolicyVersionId  # pinned for the whole run
    budget: RunBudget
    composition_level: CompositionLevel = CompositionLevel.L0  # the maximum level for this run
    status: RunStatus = RunStatus.QUEUED
    stop_reason: StopReason | None = None
    collect_training_data: bool = False  # pinned at run start from the setting (D-036)

    @model_validator(mode="after")
    def _stop_has_reason(self) -> Run:
        if (self.status is RunStatus.STOPPED) != (self.stop_reason is not None):
            raise ValueError("a stopped run has a stop_reason, and only a stopped run has one")
        if self.profile is Profile.LOCAL_ONLY and self.budget.cloud_allowed:
            raise ValueError("a local-only run cannot allow cloud providers")
        return self


class EventKind(StrEnum):
    PHASE = "phase"
    NODE_START = "node_start"
    NODE_END = "node_end"
    LLM_CALL = "llm_call"
    EXEC = "exec"
    DIAGNOSTICS = "diagnostics"
    TEST_RESULT = "test_result"
    GATE_REQUESTED = "gate_requested"
    GATE_RESOLVED = "gate_resolved"
    ESCALATION = "escalation"
    INCREMENT = "increment"
    BUDGET = "budget"
    STOP = "stop"
    ERROR = "error"


class RunEvent(Document):
    """One append-only entry of a run's event log (`events` table and `events.jsonl`)."""

    run_id: ItemId
    seq: int = Field(ge=0)
    ts: datetime
    ns: Annotated[str, StringConstraints(max_length=128)] = ""  # LangGraph checkpoint namespace
    phase: ShortText = ""
    sprint: int | None = Field(default=None, ge=1)
    task_id: NodeId | None = None
    node_id: NodeId | None = None
    kind: EventKind
    payload: dict[str, Any] = Field(default_factory=dict)  # small; bulky data goes to payload_ref
    payload_ref: RelPath | None = None  # file under var/runs/<run_id>/


class LLMCallRecord(Document):
    """The ledger row of one model call (`llm_calls` table). Never holds prompt text or keys."""

    provider: ProviderId
    model: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    model_hash: Sha256 | None = None  # GGUF sha256 for local models
    params: dict[str, int | float | bool | str | None] = Field(default_factory=dict)
    prompt_hash: Sha256
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    tokens_cached: int = Field(default=0, ge=0)
    latency_ms: int = Field(ge=0)
    tok_per_s: float | None = Field(default=None, ge=0)
    schema_valid: bool | None = None  # None when no schema was requested
    repairs: int = Field(default=0, ge=0)
    usd: float | None = Field(default=None, ge=0)  # None when the price is unknown
    stop_reason: ShortText  # the provider's finish reason, e.g. "end_turn", "length"


class GateKind(StrEnum):
    G0_CLARIFY = "G0"
    G1_SPEC = "G1"
    G2_CONTRACTS = "G2"
    G3_SPRINT_REVIEW = "G3"
    G4_FINAL = "G4"
    G5_CONSENT = "G5"
    G6_POLICY = "G6"


class GateRequest(Document):
    gate_id: ItemId
    kind: GateKind
    run_id: ItemId
    payload: dict[str, Any] = Field(default_factory=dict)  # references to persisted artifacts
    options: list[ShortText] = Field(min_length=1, max_length=8)


class GateDecision(Document):
    gate_id: ItemId
    decision: ShortText  # one of the request's options
    edits: dict[str, Any] = Field(default_factory=dict)
    comment: Text = ""
    at: datetime


class CommandKind(StrEnum):
    RESUME = "resume"
    CANCEL = "cancel"
    RETRY_TASK = "retry_task"
    EXTEND_BUDGET = "extend_budget"


class RunCommand(Document):
    """A request from the UI or CLI to the worker (`commands` table, §17)."""

    run_id: ItemId
    kind: CommandKind
    decision: GateDecision | None = None  # resume only
    task_id: NodeId | None = None  # retry_task only
    budget: RunBudget | None = None  # extend_budget only: the new limits

    @model_validator(mode="after")
    def _arguments_match_kind(self) -> RunCommand:
        expected = {
            CommandKind.RESUME: "decision",
            CommandKind.RETRY_TASK: "task_id",
            CommandKind.EXTEND_BUDGET: "budget",
        }.get(self.kind)
        given = {name for name in ("decision", "task_id", "budget") if getattr(self, name) is not None}
        if given != ({expected} if expected else set()):
            raise ValueError(f"{self.kind.value!r} takes {expected or 'no arguments'}, got {sorted(given)}")
        return self
