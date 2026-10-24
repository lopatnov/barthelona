"""V3: Static ABI lint over a Capstone CFG.

Architecture §13.1 V3 checks:
- RSP delta along every path; stack balanced at every `ret`
- Alignment ≡ 8 (mod 16) at every `call`
- Callee-saved registers saved/restored (SysV: rbx, rbp, r12–r15)
- Reads of rcx/r11 after `syscall`
- Absolute 32-bit references in PIE code
- `.note.GNU-stack` present
- `vzeroupper` before returning from AVX code
- Win64 later: shadow space ≥ 32 bytes, `.pdata` entry per non-leaf function

Output: Diagnostics with `file:line` via DWARF (`-g -F dwarf` for NASM, `-g` for GAS)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from capstone import CS_ARCH_X86, CS_MODE_64, Cs, CsInsn
from capstone.x86 import (
    X86_REG_R8,
    X86_REG_R9,
    X86_REG_R10,
    X86_REG_R11,
    X86_REG_R12,
    X86_REG_R13,
    X86_REG_R14,
    X86_REG_R15,
    X86_REG_RAX,
    X86_REG_RBP,
    X86_REG_RBX,
    X86_REG_RCX,
    X86_REG_RDI,
    X86_REG_RDX,
    X86_REG_RSI,
    X86_REG_RSP,
    X86_REG_YMM0,
    X86_REG_YMM1,
    X86_REG_YMM2,
    X86_REG_YMM3,
    X86_REG_YMM4,
    X86_REG_YMM5,
    X86_REG_YMM6,
    X86_REG_YMM7,
    X86_REG_YMM8,
    X86_REG_YMM9,
    X86_REG_YMM10,
    X86_REG_YMM11,
    X86_REG_YMM12,
    X86_REG_YMM13,
    X86_REG_YMM14,
    X86_REG_YMM15,
    X86_REG_YMM16,
    X86_REG_YMM17,
    X86_REG_YMM18,
    X86_REG_YMM19,
    X86_REG_YMM20,
    X86_REG_YMM21,
    X86_REG_YMM22,
    X86_REG_YMM23,
    X86_REG_YMM24,
    X86_REG_YMM25,
    X86_REG_YMM26,
    X86_REG_YMM27,
    X86_REG_YMM28,
    X86_REG_YMM29,
    X86_REG_YMM30,
    X86_REG_YMM31,
    X86_REG_ZMM0,
    X86_REG_ZMM1,
    X86_REG_ZMM2,
    X86_REG_ZMM3,
    X86_REG_ZMM4,
    X86_REG_ZMM5,
    X86_REG_ZMM6,
    X86_REG_ZMM7,
    X86_REG_ZMM8,
    X86_REG_ZMM9,
    X86_REG_ZMM10,
    X86_REG_ZMM11,
    X86_REG_ZMM12,
    X86_REG_ZMM13,
    X86_REG_ZMM14,
    X86_REG_ZMM15,
    X86_REG_ZMM16,
    X86_REG_ZMM17,
    X86_REG_ZMM18,
    X86_REG_ZMM19,
    X86_REG_ZMM20,
    X86_REG_ZMM21,
    X86_REG_ZMM22,
    X86_REG_ZMM23,
    X86_REG_ZMM24,
    X86_REG_ZMM25,
    X86_REG_ZMM26,
    X86_REG_ZMM27,
    X86_REG_ZMM28,
    X86_REG_ZMM29,
    X86_REG_ZMM30,
    X86_REG_ZMM31,
)

from barthelona.domain.enums import DiagnosticLevel, Level
from barthelona.domain.verification import Diagnostic, LevelResult, Severity
from barthelona.verification.registry import LadderContext, Unsupported

# SysV AMD64 ABI callee-saved registers
CALLEE_SAVED_SYSV = frozenset(
    {
        X86_REG_RBX,
        X86_REG_RBP,
        X86_REG_R12,
        X86_REG_R13,
        X86_REG_R14,
        X86_REG_R15,
    }
)

# Volatile registers (caller-saved) - for reference
VOLATILE_SYSV = frozenset(
    {
        X86_REG_RAX,
        X86_REG_RCX,
        X86_REG_RDX,
        X86_REG_RSI,
        X86_REG_RDI,
        X86_REG_R8,
        X86_REG_R9,
        X86_REG_R10,
        X86_REG_R11,
    }
)

# Registers clobbered by syscall
SYSCALL_CLOBBERED = frozenset(
    {
        X86_REG_RCX,
        X86_REG_R11,
    }
)

# Registers that must be preserved across syscall (per ABI)
SYSCALL_PRESERVED = frozenset(
    {
        X86_REG_RBX,
        X86_REG_RBP,
        X86_REG_R12,
        X86_REG_R13,
        X86_REG_R14,
        X86_REG_R15,
        X86_REG_RSP,
    }
)

# AVX registers that need vzeroupper
AVX_REGS = frozenset(
    {
        X86_REG_YMM0,
        X86_REG_YMM1,
        X86_REG_YMM2,
        X86_REG_YMM3,
        X86_REG_YMM4,
        X86_REG_YMM5,
        X86_REG_YMM6,
        X86_REG_YMM7,
        X86_REG_YMM8,
        X86_REG_YMM9,
        X86_REG_YMM10,
        X86_REG_YMM11,
        X86_REG_YMM12,
        X86_REG_YMM13,
        X86_REG_YMM14,
        X86_REG_YMM15,
        X86_REG_YMM16,
        X86_REG_YMM17,
        X86_REG_YMM18,
        X86_REG_YMM19,
        X86_REG_YMM20,
        X86_REG_YMM21,
        X86_REG_YMM22,
        X86_REG_YMM23,
        X86_REG_YMM24,
        X86_REG_YMM25,
        X86_REG_YMM26,
        X86_REG_YMM27,
        X86_REG_YMM28,
        X86_REG_YMM29,
        X86_REG_YMM30,
        X86_REG_YMM31,
        X86_REG_ZMM0,
        X86_REG_ZMM1,
        X86_REG_ZMM2,
        X86_REG_ZMM3,
        X86_REG_ZMM4,
        X86_REG_ZMM5,
        X86_REG_ZMM6,
        X86_REG_ZMM7,
        X86_REG_ZMM8,
        X86_REG_ZMM9,
        X86_REG_ZMM10,
        X86_REG_ZMM11,
        X86_REG_ZMM12,
        X86_REG_ZMM13,
        X86_REG_ZMM14,
        X86_REG_ZMM15,
        X86_REG_ZMM16,
        X86_REG_ZMM17,
        X86_REG_ZMM18,
        X86_REG_ZMM19,
        X86_REG_ZMM20,
        X86_REG_ZMM21,
        X86_REG_ZMM22,
        X86_REG_ZMM23,
        X86_REG_ZMM24,
        X86_REG_ZMM25,
        X86_REG_ZMM26,
        X86_REG_ZMM27,
        X86_REG_ZMM28,
        X86_REG_ZMM29,
        X86_REG_ZMM30,
        X86_REG_ZMM31,
    }
)


@dataclass
class StackState:
    """Stack pointer delta and alignment state at a program point."""

    rsp_delta: int = 0  # offset from entry RSP
    aligned: bool = True  # whether RSP ≡ 8 (mod 16) at this point


@dataclass
class FuncAnalysis:
    """Results of analyzing one function."""

    name: str
    start_addr: int
    end_addr: int
    stack_balanced: bool = True
    max_stack_depth: int = 0
    callee_saved_used: set[int] = None  # registers that need saving
    callee_saved_saved: set[int] = None  # registers actually saved/restored
    calls: list[tuple[int, int]] = None  # (call_addr, target_addr)
    syscall_sites: list[int] = None  # addresses of syscall instructions
    rcx_r11_read_after_syscall: list[int] = None  # addresses where rcx/r11 read after syscall
    absolute_32bit_refs: list[int] = None  # addresses of absolute 32-bit memory refs
    has_vzeroupper: bool = False
    returns: list[int] = None  # addresses of ret instructions
    uses_avx: bool = False

    def __post_init__(self):
        if self.callee_saved_used is None:
            self.callee_saved_used = set()
        if self.callee_saved_saved is None:
            self.callee_saved_saved = set()
        if self.calls is None:
            self.calls = []
        if self.syscall_sites is None:
            self.syscall_sites = []
        if self.rcx_r11_read_after_syscall is None:
            self.rcx_r11_read_after_syscall = []
        if self.absolute_32bit_refs is None:
            self.absolute_32bit_refs = []
        if self.returns is None:
            self.returns = []


class CapstoneAnalyzer:
    """Static analysis of x86-64 code using Capstone."""

    def __init__(self, code: bytes, base_addr: int = 0x400000):
        self.code = code
        self.base_addr = base_addr
        self.md = Cs(CS_ARCH_X86, CS_MODE_64)
        self.md.detail = True
        self.md.syntax = 1  # Intel syntax
        self.functions: dict[int, FuncAnalysis] = {}

    def analyze(self) -> dict[int, FuncAnalysis]:
        """Analyze all code and return function analyses."""
        # Disassemble all code
        instructions = list(self.md.disasm(self.code, self.base_addr))
        if not instructions:
            return {}

        # Identify function boundaries (simplified: look for `ret` and known entry points)
        func_starts = self._find_function_starts(instructions)
        self._analyze_functions(instructions, func_starts)
        return self.functions

    def _find_function_starts(self, instructions: list[CsInsn]) -> list[int]:
        """Find function start addresses (simplified heuristic)."""
        starts = {instructions[0].address}  # entry point
        for insn in instructions:
            # Function starts after ret
            if insn.id == 0xC3 or insn.mnemonic == "ret":  # ret
                next_idx = instructions.index(insn) + 1
                if next_idx < len(instructions):
                    starts.add(instructions[next_idx].address)
            # Calls might indicate function boundaries
            if insn.mnemonic == "call":
                # Target of call is a function start (for direct calls)
                if insn.operands and insn.operands[0].type == 1:  # X86_OP_IMM
                    starts.add(insn.operands[0].imm)
        return sorted(starts)

    def _analyze_functions(self, instructions: list[CsInsn], func_starts: list[int]) -> None:
        """Analyze each function."""
        # Map address -> instruction for quick lookup
        {insn.address: insn for insn in instructions}

        for i, start in enumerate(func_starts):
            end = (
                func_starts[i + 1]
                if i + 1 < len(func_starts)
                else instructions[-1].address + instructions[-1].size
            )
            func_insns = [insn for insn in instructions if start <= insn.address < end]

            if not func_insns:
                continue

            analysis = FuncAnalysis(
                name=f"sub_{start:x}",
                start_addr=start,
                end_addr=end,
            )

            # Track stack state along paths (simplified: linear scan)
            self._analyze_function_linear(func_insns, analysis)
            self.functions[start] = analysis

    def _analyze_function_linear(self, insns: list[CsInsn], analysis: FuncAnalysis) -> None:
        """Linear scan analysis of one function (conservative, no full CFG yet)."""
        rsp_delta = 0
        max_rsp_delta = 0
        saw_syscall = False

        for insn in insns:
            # Track RSP changes
            if insn.mnemonic in ("push", "pushq", "pushl"):
                if insn.operands and insn.operands[0].type == 1:  # immediate
                    # push imm8/imm32 - not typical for stack adjustment
                    pass
                else:
                    rsp_delta -= 8
            elif insn.mnemonic in ("pop", "popq", "popl"):
                rsp_delta += 8
            elif insn.mnemonic in ("sub", "subq", "subl"):
                if (
                    insn.operands
                    and len(insn.operands) >= 2
                    and insn.operands[0].reg == X86_REG_RSP
                    and insn.operands[1].type == 1
                ):
                    rsp_delta -= insn.operands[1].imm
            elif insn.mnemonic in ("add", "addq", "addl"):
                if (
                    insn.operands
                    and len(insn.operands) >= 2
                    and insn.operands[0].reg == X86_REG_RSP
                    and insn.operands[1].type == 1
                ):
                    rsp_delta += insn.operands[1].imm

            max_rsp_delta = max(max_rsp_delta, -rsp_delta)

            # Detect calls
            if insn.mnemonic == "call":
                target = None
                if insn.operands and insn.operands[0].type == 1:  # immediate
                    target = insn.operands[0].imm
                analysis.calls.append((insn.address, target or 0))

                # Check alignment at call site
                # RSP must be 8 mod 16 before call (after pushing return addr)
                if (rsp_delta - 8) % 16 != 8:
                    analysis.absolute_32bit_refs.append(insn.address)  # reuse for alignment issues

            # Detect syscall
            if insn.mnemonic in ("syscall", "sysenter"):
                analysis.syscall_sites.append(insn.address)
                saw_syscall = True

            # Track reads of rcx/r11 after syscall
            if saw_syscall and insn.mnemonic not in ("syscall", "sysenter"):
                for op in insn.operands:
                    if op.type == 1 and op.reg in SYSCALL_CLOBBERED:
                        # This is a read of a clobbered register
                        analysis.rcx_r11_read_after_syscall.append(insn.address)

            # Track callee-saved register usage
            for op in insn.operands:
                if op.type == 1 and op.reg in CALLEE_SAVED_SYSV:
                    analysis.callee_saved_used.add(op.reg)

            # Track push/pop of callee-saved registers (save/restore)
            if (
                insn.mnemonic in ("push", "pushq")
                and insn.operands
                and insn.operands[0].type == 1
                and insn.operands[0].reg in CALLEE_SAVED_SYSV
            ):
                analysis.callee_saved_saved.add(insn.operands[0].reg)
            if (
                insn.mnemonic in ("pop", "popq")
                and insn.operands
                and insn.operands[0].type == 1
                and insn.operands[0].reg in CALLEE_SAVED_SYSV
            ):
                analysis.callee_saved_saved.add(insn.operands[0].reg)

            # Detect vzeroupper
            if insn.mnemonic == "vzeroupper":
                analysis.has_vzeroupper = True

            # Detect AVX usage (YMM/ZMM registers)
            for op in insn.operands:
                if op.type == 1 and op.reg in AVX_REGS:
                    analysis.uses_avx = True

            # Detect absolute 32-bit memory references (PIE check)
            for op in insn.operands:
                if (
                    op.type == 3
                    and op.mem.base == 0
                    and op.mem.index == 0
                    and op.mem.disp != 0
                    and op.mem.disp < 0x100000000
                ):
                    analysis.absolute_32bit_refs.append(insn.address)

            # Track returns
            if insn.mnemonic == "ret":
                analysis.returns.append(insn.address)
                # Check stack balance at return
                if rsp_delta != 0:
                    analysis.stack_balanced = False

        analysis.max_stack_depth = max_rsp_delta

    def check_note_gnu_stack(self, object_path: Path) -> bool:
        """Check if object file has .note.GNU-stack section."""
        # This would require reading the ELF file - delegate to separate check
        return True  # placeholder


def run_v3_static_lint(
    ctx: LadderContext,
    command_timeout: float = 15.0,
) -> LevelResult:
    """V3: Static ABI lint using Capstone CFG analysis."""
    import time

    from barthelona.executors._types import ExecLimits

    t0 = time.monotonic()
    diagnostics: list[Diagnostic] = []
    ExecLimits(timeout=command_timeout, max_stderr_bytes=64 * 1024)

    # For each source file, we need the object file to analyze
    # The objects are produced by V1 and available via the executor session
    # For now, this is a stub that will be fleshed out

    diagnostics.append(
        Diagnostic(
            tool="capstone",
            level=DiagnosticLevel.V3,
            severity=Severity.NOTE,
            code="v3.not_implemented",
            message="V3 static ABI lint (Capstone CFG) not yet implemented",
            file=None,
        )
    )

    return LevelResult(
        level=Level.V3,
        status="unsupported",
        diagnostics=diagnostics,
        secs=time.monotonic() - t0,
    )


class StaticLintCheck:
    """V3 as a registered check."""

    level = Level.V3
    always_run = False

    def supports(self, ctx: LadderContext) -> Unsupported | None:
        if ctx.contracts is None:
            return Unsupported("V3 requires contract registry for ABI checks")
        # Check if capstone is available
        try:
            import capstone  # noqa: F401
        except ImportError:
            return Unsupported("capstone not installed")
        # Check if DWARF info available (need -g -F dwarf for NASM, -g for GAS)
        # This is a placeholder - real check would verify object files have DWARF
        return None

    async def run(self, ctx: LadderContext) -> LevelResult:
        return run_v3_static_lint(ctx)
