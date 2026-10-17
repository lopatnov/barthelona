"""Closed vocabularies shared by the domain models (docs/architecture.md §4, §9, §13)."""

from __future__ import annotations

from enum import StrEnum


class Dialect(StrEnum):
    NASM = "nasm"
    GAS_INTEL = "gas-intel"
    GAS_ATT = "gas-att"
    FASM = "fasm"
    FASMG = "fasmg"
    FASM2 = "fasm2"
    YASM = "yasm"
    ASMC = "asmc"
    UASM = "uasm"
    MASM_ML64 = "masm-ml64"


class Arch(StrEnum):
    X86_16 = "x86-16"
    X86 = "x86"
    X86_64 = "x86-64"
    AARCH64 = "aarch64"
    RISCV64 = "riscv64"


class OS(StrEnum):
    LINUX = "linux"
    WINDOWS = "windows"
    BARE = "bare"
    DOS = "dos"


class ABI(StrEnum):
    SYSV64 = "sysv64"
    WIN64 = "win64"
    CDECL32 = "cdecl32"
    AAPCS64 = "aapcs64"
    LP64D = "lp64d"
    NONE = "none"


class ObjFormat(StrEnum):
    ELF64 = "elf64"
    ELF32 = "elf32"
    WIN64 = "win64"
    PE64_DIRECT = "pe64-direct"
    BIN = "bin"


class Linker(StrEnum):
    NONE = "none"
    LD = "ld"
    LIBC = "libc"
    MINGW = "mingw"
    MSVC = "msvc"
    LLD_LINK = "lld-link"


class RunEnv(StrEnum):
    DOCKER_NATIVE = "docker-native"
    DOCKER_QEMU_USER = "docker-qemu-user"
    DOCKER_WINE = "docker-wine"
    QEMU_SYSTEM = "qemu-system"
    EMU_ONLY = "emu-only"


class Level(StrEnum):
    """Verification ladder levels (§13.1)."""

    V0 = "V0"
    V1 = "V1"
    V2 = "V2"
    V3 = "V3"
    V4 = "V4"
    V5 = "V5"
    V6 = "V6"
    V7 = "V7"
    V8 = "V8"


class DiagnosticLevel(StrEnum):
    """Where a diagnostic came from: a ladder level or one of the non-ladder gates."""

    V0 = "V0"
    V1 = "V1"
    V2 = "V2"
    V3 = "V3"
    V4 = "V4"
    V5 = "V5"
    V6 = "V6"
    V7 = "V7"
    V8 = "V8"
    TAMPER = "tamper"
    MINIMALITY = "minimality"
    SCHEMA = "schema"


class StoryKind(StrEnum):
    CREATE_MODULE = "create_module"
    IMPLEMENT_SYMBOL = "implement_symbol"
    FIX_BUG = "fix_bug"
    CHANGE_BEHAVIOR = "change_behavior"
    REFACTOR = "refactor"
    CONTRACT_CHANGE = "contract_change"
    FIX_BUILD = "fix_build"
    INTEGRATION = "integration"
    SPIKE = "spike"


class Role(StrEnum):
    """Node roles (rule T9); `det` nodes make no LLM calls."""

    DET = "det"
    MAIN = "main"
    PLANNER = "planner"
    WORKER = "worker"
    CHEAP = "cheap"
    ESCALATION = "escalation"


class Outcome(StrEnum):
    """Edge conditions in a task pipeline (§9.1)."""

    OK = "ok"
    FAIL = "fail"
    ALWAYS = "always"


class StopReason(StrEnum):
    """Why a run, a sprint or a loop stopped (invariant 6). `green` is the only success."""

    GREEN = "green"
    BUDGET_TOKENS = "budget_tokens"
    BUDGET_TIME = "budget_time"
    BUDGET_COST = "budget_cost"
    MAX_ATTEMPTS = "max_attempts"
    MAX_SPRINTS = "max_sprints"
    HUMAN_ABORT = "human_abort"
    UNSUPPORTED_TARGET = "unsupported_target"
    REFUSAL = "refusal"
    NO_MODEL_AVAILABLE = "no_model_available"
    INFRA_ERROR = "infra_error"


class CompositionLevel(StrEnum):
    """Who composes sprint graphs (§9.5)."""

    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
