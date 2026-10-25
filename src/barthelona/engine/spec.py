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
# A reasoning model spends part of this on thinking; 2048 cut the test author off mid-JSON on a 10-test quiz.
ARTIFACT_TOKENS = 8192
INTAKE_ROLE = "main"
SPEC_ROLE = "planner"

OnCall = Callable[[LLMCallRecord], None]

_INTAKE_PROMPT = """You prepare a request for an assembly-language project.
The request may be in any language. Answer with ONE JSON object and nothing else:
{"lang": "de",
 "goal_en": "Print the numbers 1 to 3, one per line.",
 "entities": ["stdout", "numbers 1 to 3"],
 "assumptions": ["Linux x86-64", "no input is read"]}
That example only shows the shape. Write your own values for the request: "lang" is its ISO 639 language
code, "goal_en" restates it in English in 1-3 sentences, "entities" lists the inputs, outputs, syscalls and
constraints it names, "assumptions" lists what you assume where it is silent."""

_SPEC_PROMPT = """You write the specification of an assembly-language project from an English goal.
Answer with ONE JSON object and nothing else:
{"slug": "count-to-three",
 "summary_en": "Prints the numbers 1 to 3, one per line.",
 "requirements": [{"id": "R1", "text": "Writes 1, 2 and 3 to stdout, each followed by a newline."}],
 "modules": [{"path": "src/count.asm", "purpose": "entry point and output", "exports": ["_start"]}],
 "constraints": [], "non_goals": [], "assumptions": []}
That example only shows the shape: write your own slug (lowercase words with dashes), summary, requirements
and modules for the goal.
Rules: 1-12 requirements (a reply with more than 12 is rejected: merge related checks into one requirement),
each checkable from the program's output or exit code; 1-6 modules; paths relative
to the project, ending in the dialect's source suffix; keep it as small as the goal allows. When the program
prints results, state the exact text or format of those lines in the requirements (for example
"Extraversion: 42"), so the tests and the code agree on them."""


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


async def ask_json[Model: DomainModel](
    gateway: ModelGateway,
    role: str,
    system: str,
    user: str,
    model: type[Model],
    on_call: OnCall,
    check: Callable[[Model], str | None] | None = None,
) -> Model:
    """One small JSON artifact; *check* names what is wrong with a valid one (sent back like an error)."""
    messages = [ChatMessage(role="system", content=system), ChatMessage(role="user", content=user)]
    problem = ""
    for _ in range(ATTEMPTS):
        completion = await gateway.complete(
            role, CompletionRequest(messages=tuple(messages), max_tokens=ARTIFACT_TOKENS)
        )
        on_call(completion.record)
        try:
            value = model.model_validate(_json_object(completion.text))
            problem = (check(value) if check else None) or ""
            if not problem:
                return value
        except (ValueError, ValidationError) as exc:  # orjson's decode error is a ValueError
            problem = str(exc)[:600]
            if completion.record.stop_reason == "length":
                problem = "the reply was cut off by the length limit: answer again, much shorter"
        messages += [
            ChatMessage(role="assistant", content=completion.text),
            ChatMessage(role="user", content=f"That reply is unusable: {problem}\nAnswer again, JSON only."),
        ]
    raise SpecError(f"{role} gave no valid {model.__name__} in {ATTEMPTS} tries: {problem}")


async def run_intake(gateway: ModelGateway, request: str, on_call: OnCall) -> Intake:
    return await ask_json(gateway, INTAKE_ROLE, _INTAKE_PROMPT, request, Intake, on_call)


def with_facts(prompt: str, facts: str) -> str:
    """*prompt* followed by the knowledge-store block (already marked as untrusted data), if there is one."""
    return f"{prompt}\n\n{facts}" if facts else prompt


async def draft_spec(
    gateway: ModelGateway, run: Run, request: str, intake: Intake, facts: str, on_call: OnCall
) -> ProjectSpec:
    target = run.target
    user = (
        f"Request (authoritative; keep its exact wording, formats and numbers):\n{request.strip()[:4000]}\n\n"
        f"Goal: {intake.goal_en}\nTarget: {target.preset} ({target.dialect.value}, {target.arch.value}, "
        f"{target.os.value}, {target.abi.value})\nEntities: {'; '.join(intake.entities) or 'none named'}"
    )
    draft = await ask_json(gateway, SPEC_ROLE, _SPEC_PROMPT, with_facts(user, facts), SpecDraft, on_call)
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
