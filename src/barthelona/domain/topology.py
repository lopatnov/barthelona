"""Topology DSL models: task pipelines, sprint topologies and planner requests (docs/architecture.md §9).

These models check field shapes only. Graph rules (vocabulary, reachability, totality, bounded cycles,
verification dominance, write scopes, budgets, roles, gate hygiene) are validator rules T1-T10 in
`engine/sprint/validate.py`, so the planner gets one error list per proposal.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field, StringConstraints, model_validator

from barthelona.domain._base import (
    NODE_ID_PATTERN,
    Document,
    DomainModel,
    NodeId,
    PolicyVersionId,
    Sha256,
    require_unique,
)
from barthelona.domain.enums import CompositionLevel, Outcome, Role

ParamStr = Annotated[str, StringConstraints(max_length=200)]
ParamValue = int | float | bool | ParamStr | Annotated[list[ParamStr], Field(max_length=16)] | None
KnobValue = int | float | bool | Annotated[str, StringConstraints(max_length=64)]
# A back edge written as "src->dst", e.g. "fix->apply" (dict keys must be strings in JSON).
BackEdgeKey = Annotated[
    str, StringConstraints(pattern=rf"^{NODE_ID_PATTERN[1:-1]}->{NODE_ID_PATTERN[1:-1]}$")
]


MAX_LOOP_ITERS = 16


class StallRule(StrEnum):
    SAME_ERROR_SIG_TWICE = "same_error_sig_twice"
    REPEATED_PATCH_HASH = "repeated_patch_hash"


class UnitSize(StrEnum):
    SYMBOL = "symbol"
    MODULE = "module"
    MODULE_GROUP = "module_group"


class NodeSpec(DomainModel):
    id: NodeId
    type: NodeId  # a registered node type (rule T1)
    params: dict[NodeId, ParamValue] = Field(default_factory=dict, max_length=16)
    role: Role = Role.DET
    timeout_s: float | None = Field(default=None, gt=0)


class EdgeSpec(DomainModel):
    src: NodeId
    dst: NodeId
    when: Outcome


class LoopBudget(DomainModel):
    """Per-loop limits; the loop stops at whichever fires first (§9.5)."""

    # Absolute ceilings; the policy caps checked by T5 and T8 are tighter.
    max_iters: int = Field(ge=1, le=MAX_LOOP_ITERS)
    max_wall_s: float | None = Field(default=None, gt=0, le=86_400)
    max_tokens: int | None = Field(default=None, ge=1, le=10_000_000)
    max_usd: float | None = Field(default=None, ge=0, le=1_000)


class LoopBound(LoopBudget):
    back_edge: tuple[NodeId, NodeId]
    on_exhaust: NodeId
    stall: StallRule = StallRule.SAME_ERROR_SIG_TWICE


class TaskPipeline(DomainModel):
    """A template expanded with its insertions and knob values, or an L2 pipeline."""

    nodes: list[NodeSpec] = Field(min_length=1, max_length=64)
    edges: list[EdgeSpec] = Field(max_length=256)
    loops: list[LoopBound] = Field(default_factory=list, max_length=16)
    entry: NodeId
    exits_ok: list[NodeId] = Field(min_length=1, max_length=8)
    exits_fail: list[NodeId] = Field(default_factory=list, max_length=8)
    max_llm_calls: int = Field(ge=0)
    hash: Sha256 | None = None


class SprintBudget(DomainModel):
    max_llm_calls: int = Field(ge=0)
    max_tokens: int | None = Field(default=None, ge=1)
    max_wall_s: float | None = Field(default=None, gt=0)
    max_usd: float | None = Field(default=None, ge=0)  # None = uncapped but metered


class SprintTopology(Document):
    """The compiled-from data for one sprint, persisted as `.barthelona/sprints/NN/topology[.rK].json`."""

    sprint_no: int = Field(ge=1)
    revision: int = Field(default=0, ge=0)  # K in topology.rK.json; 0 is the first plan
    policy_version: PolicyVersionId
    builder_version: Annotated[str, StringConstraints(min_length=1, max_length=32)]
    composition_level: CompositionLevel
    pre: list[NodeId] = Field(default_factory=lambda: ["header_gen"])
    layers: list[list[NodeId]] = Field(min_length=1)  # task ids, layer by layer
    pipelines: dict[Sha256, TaskPipeline]
    task_pipeline: dict[NodeId, Sha256]  # task id -> pipeline hash
    post: list[NodeId] = Field(default_factory=lambda: ["integration", "verify_dod", "review_gate"])
    budget: SprintBudget
    spec_hash: Sha256 | None = None

    @model_validator(mode="after")
    def _tasks_map_to_pipelines(self) -> SprintTopology:
        layered = [task_id for layer in self.layers for task_id in layer]
        require_unique("task id in layers", layered)
        if sorted(layered) != sorted(self.task_pipeline):
            raise ValueError("layers must list every task of task_pipeline exactly once")
        missing = sorted(set(self.task_pipeline.values()) - set(self.pipelines))
        if missing:
            raise ValueError(f"task_pipeline refers to unknown pipelines: {missing}")
        for key, pipeline in self.pipelines.items():
            if pipeline.hash is not None and pipeline.hash != key:
                raise ValueError(f"pipeline key {key} does not match its hash")
        return self


class TaskTopologyChoice(DomainModel):
    """L1: one task's template, slot insertions, knob values, loop budgets and unit size."""

    task_id: NodeId
    template_id: NodeId
    insertions: dict[NodeId, list[NodeId]] = Field(default_factory=dict, max_length=8)  # slot -> node types
    knobs: dict[NodeId, KnobValue] = Field(default_factory=dict, max_length=16)
    loop_budgets: dict[BackEdgeKey, LoopBudget] = Field(default_factory=dict, max_length=8)
    unit_size: UnitSize = UnitSize.MODULE

    @model_validator(mode="after")
    def _at_most_two_per_slot(self) -> TaskTopologyChoice:
        for slot, types in self.insertions.items():
            if len(types) > 2:
                raise ValueError(f"slot {slot!r}: at most 2 insertions")
        return self


class TopologyRequest(Document):
    """The planner's proposal: L1 choices per task, or whole L2 pipelines per task."""

    tasks: list[TaskTopologyChoice] = Field(default_factory=list, max_length=64)
    pipelines: dict[NodeId, TaskPipeline] = Field(
        default_factory=dict, max_length=64
    )  # L2: task id -> pipeline
    rationale: str = Field(default="", max_length=300)

    @model_validator(mode="after")
    def _one_level(self) -> TopologyRequest:
        if bool(self.tasks) == bool(self.pipelines):
            raise ValueError("give either per-task choices (L1) or pipelines (L2), not both or neither")
        return self
