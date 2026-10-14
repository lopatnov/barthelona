"""Backlog and sprint planning models (docs/architecture.md §4 "Backlog and sprints", §7)."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from barthelona.domain._base import (
    Document,
    DomainModel,
    ItemId,
    NodeId,
    RelPath,
    ShortText,
    SymbolName,
    Text,
    require_unique,
)
from barthelona.domain.enums import Role, StopReason, StoryKind
from barthelona.domain.topology import SprintBudget, TopologyRequest


class ItemStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    READY = "ready"
    IN_SPRINT = "in_sprint"
    DONE = "done"
    BLOCKED = "blocked"
    DROPPED = "dropped"


class BacklogItem(Document):
    id: ItemId
    kind: StoryKind
    title: ShortText
    narrative: Text = ""
    requirement_ids: list[ItemId] = Field(default_factory=list, max_length=32)
    acceptance_test_ids: list[ItemId] = Field(default_factory=list, max_length=64)
    modules: list[RelPath] = Field(default_factory=list, max_length=16)
    symbols: list[SymbolName] = Field(default_factory=list, max_length=64)
    depends_on: list[ItemId] = Field(default_factory=list, max_length=32)
    size: Literal["XS", "S", "M"] = "S"
    priority: int = Field(default=0, ge=0, le=1000)  # lower runs first
    tags: list[ShortText] = Field(default_factory=list, max_length=16)
    status: ItemStatus = ItemStatus.PROPOSED
    attempts: int = Field(default=0, ge=0)
    stop_reason: StopReason | None = None

    @model_validator(mode="after")
    def _not_self_dependent(self) -> BacklogItem:
        if self.id in self.depends_on:
            raise ValueError("an item cannot depend on itself")
        return self


class Task(DomainModel):
    id: NodeId
    item_id: ItemId
    module: RelPath
    symbols: list[SymbolName] = Field(default_factory=list, max_length=64)
    depends_on: list[NodeId] = Field(default_factory=list, max_length=32)
    write_scope: list[RelPath] = Field(min_length=1, max_length=16)  # globs; checked by rule T7
    role_hint: Role | None = None


class SprintPlan(Document):
    sprint_no: int = Field(ge=1)
    goal: ShortText
    item_ids: list[ItemId] = Field(min_length=1)
    tasks: list[Task] = Field(min_length=1, max_length=64)
    layers: list[list[NodeId]] = Field(min_length=1)  # tasks of one layer run in parallel
    topology_request: TopologyRequest | None = None  # None at L0: rules choose the templates
    budget: SprintBudget

    @model_validator(mode="after")
    def _layers_cover_tasks(self) -> SprintPlan:
        task_ids = [t.id for t in self.tasks]
        require_unique("task id", task_ids)
        layered = [task_id for layer in self.layers for task_id in layer]
        require_unique("task id in layers", layered)
        if sorted(layered) != sorted(task_ids):
            raise ValueError("layers must list every task exactly once")
        position = {task_id: n for n, layer in enumerate(self.layers) for task_id in layer}
        for task in self.tasks:
            for dep in task.depends_on:
                if dep not in position:
                    raise ValueError(f"task {task.id!r} depends on unknown task {dep!r}")
                if position[dep] >= position[task.id]:
                    raise ValueError(f"task {task.id!r} must be in a later layer than {dep!r}")
        return self
