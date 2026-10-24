"""Callee-saved register canary setup and verification for the emulator.

Architecture §13.1 V4 canaries:
- SysV: rbx, rbp, r12–r15
- Win64: those plus rdi, rsi, xmm6–15

Canaries are unique values placed in callee-saved registers before emulation.
After emulation, they are checked to detect clobbering violations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

try:
    from unicorn.x86_const import (
        UC_X86_REG_R12,
        UC_X86_REG_R13,
        UC_X86_REG_R14,
        UC_X86_REG_R15,
        UC_X86_REG_RBP,
        UC_X86_REG_RBX,
        UC_X86_REG_RDI,
        UC_X86_REG_RSI,
        UC_X86_REG_XMM6,
        UC_X86_REG_XMM7,
        UC_X86_REG_XMM8,
        UC_X86_REG_XMM9,
        UC_X86_REG_XMM10,
        UC_X86_REG_XMM11,
        UC_X86_REG_XMM12,
        UC_X86_REG_XMM13,
        UC_X86_REG_XMM14,
        UC_X86_REG_XMM15,
    )

    UNICORN_AVAILABLE = True
except ImportError:
    UNICORN_AVAILABLE = False


class ABI(Enum):
    SYSV64 = "sysv64"
    WIN64 = "win64"


# Canary register sets per ABI
CANARY_REGS_SYSV64 = (
    [
        UC_X86_REG_RBX,
        UC_X86_REG_RBP,
        UC_X86_REG_R12,
        UC_X86_REG_R13,
        UC_X86_REG_R14,
        UC_X86_REG_R15,
    ]
    if UNICORN_AVAILABLE
    else []
)

CANARY_REGS_WIN64 = (
    CANARY_REGS_SYSV64
    + [
        UC_X86_REG_RDI,
        UC_X86_REG_RSI,
        # XMM6-15 - FP/SIMD registers
        UC_X86_REG_XMM6,
        UC_X86_REG_XMM7,
        UC_X86_REG_XMM8,
        UC_X86_REG_XMM9,
        UC_X86_REG_XMM10,
        UC_X86_REG_XMM11,
        UC_X86_REG_XMM12,
        UC_X86_REG_XMM13,
        UC_X86_REG_XMM14,
        UC_X86_REG_XMM15,
    ]
    if UNICORN_AVAILABLE
    else []
)

# Human-readable register names for diagnostics
REG_NAMES = (
    {
        UC_X86_REG_RBX: "RBX",
        UC_X86_REG_RBP: "RBP",
        UC_X86_REG_R12: "R12",
        UC_X86_REG_R13: "R13",
        UC_X86_REG_R14: "R14",
        UC_X86_REG_R15: "R15",
        UC_X86_REG_RDI: "RDI",
        UC_X86_REG_RSI: "RSI",
        UC_X86_REG_XMM6: "XMM6",
        UC_X86_REG_XMM7: "XMM7",
        UC_X86_REG_XMM8: "XMM8",
        UC_X86_REG_XMM9: "XMM9",
        UC_X86_REG_XMM10: "XMM10",
        UC_X86_REG_XMM11: "XMM11",
        UC_X86_REG_XMM12: "XMM12",
        UC_X86_REG_XMM13: "XMM13",
        UC_X86_REG_XMM14: "XMM14",
        UC_X86_REG_XMM15: "XMM15",
    }
    if UNICORN_AVAILABLE
    else {}
)


@dataclass
class CanarySet:
    """A set of canary values for callee-saved registers."""

    abi: ABI = ABI.SYSV64
    values: dict[int, int] = field(default_factory=dict)  # reg_id -> canary_value

    def __post_init__(self):
        if not self.values:
            self.values = self._generate_canaries()

    def _generate_canaries(self) -> dict[int, int]:
        """Generate unique canary values for each register."""
        regs = CANARY_REGS_WIN64 if self.abi == ABI.WIN64 else CANARY_REGS_SYSV64
        canaries = {}
        base = 0xDEADBEEFCAFEBABE
        for i, reg in enumerate(regs):
            # Each canary is unique and has a recognizable pattern
            canaries[reg] = base + i * 0x100000000 + i
        return canaries

    def get_registers(self) -> list[int]:
        """Get the list of registers that have canaries."""
        return list(self.values.keys())

    def get_canary(self, reg: int) -> int | None:
        """Get the canary value for a register."""
        return self.values.get(reg)


def setup_canaries(uc, abi: ABI = ABI.SYSV64) -> CanarySet:
    """Set up canaries in callee-saved registers."""
    canary_set = CanarySet(abi=abi)

    for reg, value in canary_set.values.items():
        try:
            uc.reg_write(reg, value)
        except Exception:
            pass  # Register might not be writable (e.g., XMM on some configs)

    return canary_set


def verify_canaries(uc, canary_set: CanarySet) -> list[tuple[int, int, int]]:
    """Verify canaries after emulation.

    Returns list of (reg_id, expected, actual) for corrupted canaries.
    """
    violations = []

    for reg, expected in canary_set.values.items():
        try:
            actual = uc.reg_read(reg)
            if actual != expected:
                violations.append((reg, expected, actual))
        except Exception:
            # Register not readable
            pass

    return violations


def format_canary_violation(reg: int, expected: int, actual: int) -> str:
    """Format a canary violation for diagnostic output."""
    reg_name = REG_NAMES.get(reg, f"REG_{reg}")
    return f"Callee-saved register {reg_name} clobbered (expected {expected:#018x}, got {actual:#018x})"


class CanaryManager:
    """Manages canaries for an emulation session."""

    def __init__(self, abi: ABI = ABI.SYSV64):
        self.abi = abi
        self.canary_set: CanarySet | None = None
        self.violations: list[tuple[int, int, int]] = []

    def setup(self, uc) -> CanarySet:
        """Set up canaries before emulation."""
        self.canary_set = setup_canaries(uc, self.abi)
        self.violations = []
        return self.canary_set

    def check(self, uc) -> list[tuple[int, int, int]]:
        """Check canaries after emulation."""
        if self.canary_set is None:
            return []

        self.violations = verify_canaries(uc, self.canary_set)
        return self.violations

    def has_violations(self) -> bool:
        """Check if any canaries were corrupted."""
        return len(self.violations) > 0

    def get_diagnostics(self) -> list[dict]:
        """Get diagnostic information for violations."""
        diags = []
        for reg, expected, actual in self.violations:
            diags.append(
                {
                    "register": REG_NAMES.get(reg, f"REG_{reg}"),
                    "expected": expected,
                    "actual": actual,
                    "message": format_canary_violation(reg, expected, actual),
                }
            )
        return diags


# Stack canary for stack smashing detection
STACK_CANARY_VALUE = 0xDEADBEEFCAFEBABE


def setup_stack_canary(uc, stack_top: int, stack_size: int) -> int:
    """Place a stack canary at the bottom of the stack frame.

    Returns the address of the canary.
    """
    # Place canary at a known offset from stack top
    # Typically just below the saved RBP
    canary_addr = stack_top - 8
    try:
        uc.mem_write(canary_addr, STACK_CANARY_VALUE.to_bytes(8, "little"))
        return canary_addr
    except Exception:
        return 0


def check_stack_canary(uc, canary_addr: int) -> bool:
    """Check if stack canary is intact."""
    try:
        data = uc.mem_read(canary_addr, 8)
        actual = int.from_bytes(data, "little")
        return actual == STACK_CANARY_VALUE
    except Exception:
        return False
