"""The create flow's front half: `intake` and `refine_backlog` (docs/architecture.md §6.1 steps 3-4).

Each step is one small structured model call. The reply is a JSON object (invariant 5 allows JSON for small
artifacts only; no code travels in it), validated against a domain model. A bad reply is sent back once with
the validation error; a second bad reply stops the run, so the loop is bounded (invariant 6).

The prompts live here for now, like the Markovian prompt; they move to `policies/vN/prompts/` with the policy
schema (roadmap Phase 1b).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

import orjson
from pydantic import Field, StringConstraints, ValidationError

from barthelona.domain import LLMCallRecord, ModuleSpec, ProjectSpec, Requirement, Run
from barthelona.domain._base import DomainModel, ShortText
from barthelona.llm.gateway import ModelGateway
from barthelona.llm.types import ChatMessage, CompletionRequest

ATTEMPTS = 2
INTAKE_ROLE = "main"
SPEC_ROLE = "planner"

OnCall = Callable[[LLMCallRecord], None]

_INTAKE_PROMPT = """You prepare a request for an assembly-language project.
The request may be in any language. Answer with ONE JSON object and nothing else:
{"lang": "<ISO 639 code of the request, e.g. en>",
 "goal_en": "<the request restated in English, 1-3 sentences>",
 "entities": ["<inputs, outputs, syscalls, constraints named in the request>"],
 "assumptions": ["<what you assume where the request is silent>"]}"""

_SPEC_PROMPT = """You write the specification of an assembly-language project from an English goal.
Answer with ONE JSON object and nothing else:
{"slug": "<lowercase-words-with-dashes>",
 "summary_en": "<what the program does, 1-3 sentences>",
 "requirements": [{"id": "R1", "text": "<one testable requirement>"}],
 "modules": [{"path": "src/<name>.asm", "purpose": "<one line>", "exports": ["<symbol>"]}],
 "constraints": [], "non_goals": [], "assumptions": []}
Rules: 1-12 requirements, each checkable from the program's output or exit code; 1-6 modules; paths relative
to the project, ending in the dialect's source suffix; keep it as small as the goal allows."""


class SpecError(RuntimeError):
    """The model never produced a usable artifact within `ATTEMPTS` tries."""


class Intake(DomainModel):
    lang: Annotated[str, StringConstraints(pattern=r"^[a-z]{2,3}$")]
    goal_en: Annotated[str, StringConstraints(min_length=1, max_length=4000)]
    entities: list[ShortText] = Field(default_factory=list, max_length=32)
    assumptions: list[ShortText] = Field(default_factory=list, max_length=32)


class SpecDraft(DomainModel):
    slug: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")]
    summary_en: Annotated[str, StringConstraints(min_length=1, max_length=4000)]
    requirements: list[Requirement] = Field(min_length=1, max_length=12)
    modules: list[ModuleSpec] = Field(min_length=1, max_length=6)
    constraints: list[ShortText] = Field(default_factory=list, max_length=32)
    non_goals: list[ShortText] = Field(default_factory=list, max_length=32)
    assumptions: list[ShortText] = Field(default_factory=list, max_length=32)


def _json_object(text: str) -> object:
    start, end = text.find("{"), text.rfind("}")  # also skips a code fence around the object
    if start < 0 or end < start:
        raise ValueError("the reply holds no JSON object")
    return orjson.loads(text[start : end + 1])


async def _ask[Model: DomainModel](
    gateway: ModelGateway, role: str, system: str, user: str, model: type[Model], on_call: OnCall
) -> Model:
    messages = [ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)]
    problem = ""
    for _ in range(ATTEMPTS):
        completion = await gateway.complete(
            role, CompletionRequest(messages=tuple(messages), max_tokens=2048)
        )
        on_call(completion.record)
        try:
            return model.model_validate(_json_object(completion.text))
        except (ValueError, ValidationError) as exc:  # orjson's decode error is a ValueError
            problem = str(exc)[:600]
            messages += [
                ChatMessage(role="assistant", content=completion.text),
                ChatMessage(
                    role="user", content=f"That reply is unusable: {problem}\nAnswer again, JSON only."
                ),
            ]
    raise SpecError(f"{role} gave no valid {model.__name__} in {ATTEMPTS} tries: {problem}")


async def run_intake(gateway: ModelGateway, request: str, on_call: OnCall) -> Intake:
    return await _ask(gateway, INTAKE_ROLE, _INTAKE_PROMPT, request, Intake, on_call)


async def draft_spec(
    gateway: ModelGateway, run: Run, request: str, intake: Intake, on_call: OnCall
) -> ProjectSpec:
    target = run.target
    user = (
        f"Goal: {intake.goal_en}\nTarget: {target.preset} ({target.dialect.value}, {target.arch.value}, "
        f"{target.os.value}, {target.abi.value})\nEntities: {'; '.join(intake.entities) or 'none named'}"
    )
    draft = await _ask(gateway, SPEC_ROLE, _SPEC_PROMPT, user, SpecDraft, on_call)
    return ProjectSpec(
        id=run.id,
        slug=draft.slug,
        request_original=request.strip()[:4000],
        request_lang=intake.lang,
        summary_en=draft.summary_en,
        target=target,
        requirements=draft.requirements,
        modules=draft.modules,
        constraints=draft.constraints,
        non_goals=draft.non_goals,
        assumptions=[*intake.assumptions, *draft.assumptions][:32],
    )
