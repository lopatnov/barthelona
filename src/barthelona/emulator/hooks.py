"""Unicorn hook callbacks for V4 dynamic ABI checks.

Architecture §13.1 V4 hooks:
- Calls: alignment at each call site (Capstone pre-pass), Win64 shadow space
- Memory writes: red zone, return-address slot, outside declared buffers
- Syscalls/interrupts: allow-list only — write → captured stdout, exit
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from barthelona.domain.verification import Diagnostic, DiagnosticLevel, Severity
from barthelona.emulator.canary import CanaryManager

try:
    from unicorn import UC_HOOK_CODE, UC_HOOK_INSN, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
    from unicorn.x86_const import (
        UC_X86_INS_CALL,
        UC_X86_INS_POP,
        UC_X86_INS_PUSH,
        UC_X86_INS_RET,
        UC_X86_INS_SYSCALL,
        UC_X86_INS_SYSENTER,
        UC_X86_REG_R8,
        UC_X86_REG_R9,
        UC_X86_REG_RAX,
        UC_X86_REG_RCX,
        UC_X86_REG_RDI,
        UC_X86_REG_RDX,
        UC_X86_REG_RFLAGS,
        UC_X86_REG_RIP,
        UC_X86_REG_RSI,
        UC_X86_REG_RSP,
    )

    UNICORN_AVAILABLE = True
except ImportError:
    UNICORN_AVAILABLE = False


@dataclass
class HookContext:
    """Context passed to hook callbacks."""

    diagnostics: list[Diagnostic] = field(default_factory=list)
    canary_manager: CanaryManager | None = None
    dwarf_map: Any = None  # DwarfMap from dwarf_map.py
    mock_registry: Any = None  # MockRegistry from mocks.py
    stack_base: int = 0
    stack_top: int = 0
    instruction_count: int = 0
    max_instructions: int = 1_000_000
    syscall_allowlist: set[int] = field(default_factory=lambda: {1, 60, 231})  # write, exit, exit_group
    captured_stdout: bytes = b""
    captured_stderr: bytes = b""
    exit_code: int = 0
    stopped: bool = False
    stop_reason: str = ""


class HookDispatcher:
    """Dispatches Unicorn hooks to appropriate handlers."""

    def __init__(self, ctx: HookContext):
        self.ctx = ctx
        self._handlers = {}

    def hook_code(self, uc, address: int, size: int, user_data):
        """Hook for every instruction executed."""
        self.ctx.instruction_count += 1

        # Check instruction limit
        if self.ctx.instruction_count > self.ctx.max_instructions:
            self.ctx.stopped = True
            self.ctx.stop_reason = "instruction limit exceeded"
            uc.emu_stop()
            return

        # Delegate to specific handlers based on instruction
        # This is a simplified approach - real implementation would use
        # Capstone pre-pass to identify interesting instructions

        # For now, we can't easily detect instruction type without
        # disassembling. A production implementation would pre-disassemble
        # the code and register specific hooks.

    def hook_mem_write(self, uc, access: int, address: int, size: int, value: int, user_data):
        """Hook for memory writes - check red zone, return address, buffer overflows."""
        rsp = uc.reg_read(UC_X86_REG_RSP)

        # Check red zone (128 bytes below RSP)
        red_zone_start = rsp - 128
        if red_zone_start <= address < rsp:
            self.ctx.diagnostics.append(
                Diagnostic(
                    tool="unicorn",
                    level=DiagnosticLevel.V4,
                    severity=Severity.FATAL,
                    code="abi.red_zone_write",
                    message=f"Red zone write at {address:#x} (RSP={rsp:#x})",
                )
            )

        # Check return address slot (at RSP)
        if address == rsp:
            self.ctx.diagnostics.append(
                Diagnostic(
                    tool="unicorn",
                    level=DiagnosticLevel.V4,
                    severity=Severity.FATAL,
                    code="abi.return_address_corruption",
                    message=f"Write to return address slot at {address:#x}",
                )
            )

        # Check stack guard pages
        if address < self.ctx.stack_base or address >= self.ctx.stack_top:
            # Could be a buffer overflow
            pass

        # Check write to code sections (self-modifying code)
        # Would need memory map info

    def hook_mem_read(self, uc, access: int, address: int, size: int, user_data):
        """Hook for memory reads - could check uninitialized memory."""
        pass

    def hook_syscall(self, uc, user_data):
        """Hook for syscall/sysenter - allow-list only."""
        rax = uc.reg_read(UC_X86_REG_RAX)

        # Linux x86-64 syscall numbers
        SYS_READ = 0
        SYS_WRITE = 1
        SYS_OPEN = 2
        SYS_CLOSE = 3
        SYS_EXIT = 60
        SYS_EXIT_GROUP = 231
        SYS_MMAP = 9
        SYS_MUNMAP = 11
        SYS_BRK = 12

        if rax == SYS_WRITE:
            # write(fd, buf, count)
            fd = uc.reg_read(UC_X86_REG_RDI)
            buf = uc.reg_read(UC_X86_REG_RSI)
            count = uc.reg_read(UC_X86_REG_RDX)

            if fd == 1:  # stdout
                try:
                    data = uc.mem_read(buf, count)
                    self.ctx.captured_stdout += data
                    uc.reg_write(UC_X86_REG_RAX, count)
                except Exception:
                    uc.reg_write(UC_X86_REG_RAX, -1)
            elif fd == 2:  # stderr
                try:
                    data = uc.mem_read(buf, count)
                    self.ctx.captured_stderr += data
                    uc.reg_write(UC_X86_REG_RAX, count)
                except Exception:
                    uc.reg_write(UC_X86_REG_RAX, -1)
            else:
                # Other file descriptors not supported
                uc.reg_write(UC_X86_REG_RAX, -1)

        elif rax == SYS_READ:
            # read(fd, buf, count) - return 0 (EOF)
            uc.reg_write(UC_X86_REG_RAX, 0)

        elif rax in (SYS_EXIT, SYS_EXIT_GROUP):
            # exit/exit_group(code)
            code = uc.reg_read(UC_X86_REG_RDI)
            self.ctx.exit_code = code
            self.ctx.stopped = True
            self.ctx.stop_reason = f"syscall exit({code})"
            uc.emu_stop()

        elif rax in (SYS_OPEN, SYS_CLOSE, SYS_MMAP, SYS_MUNMAP, SYS_BRK):
            # Memory management syscalls - stub for now
            uc.reg_write(UC_X86_REG_RAX, 0)

        else:
            # Syscall not in allow-list
            self.ctx.diagnostics.append(
                Diagnostic(
                    tool="unicorn",
                    level=DiagnosticLevel.V4,
                    severity=Severity.FATAL,
                    code="abi.syscall_not_allowed",
                    message=f"Syscall {rax} not in allow-list",
                )
            )
            self.ctx.stopped = True
            self.ctx.stop_reason = f"disallowed syscall {rax}"
            uc.emu_stop()

    def hook_insn_call(self, uc, address: int, size: int, user_data):
        """Hook for CALL instructions - check stack alignment."""
        rsp = uc.reg_read(UC_X86_REG_RSP)

        # Before CALL, RSP should be 8 mod 16 (after pushing return addr, it becomes 0 mod 16)
        # Actually, per SysV ABI, at function entry RSP ≡ 8 (mod 16)
        # Before CALL, RSP ≡ 8 (mod 16), after CALL (inside callee) RSP ≡ 0 (mod 16)
        # But we check before the call instruction executes
        if rsp % 16 != 8:
            self.ctx.diagnostics.append(
                Diagnostic(
                    tool="unicorn",
                    level=DiagnosticLevel.V4,
                    severity=Severity.FATAL,
                    code="abi.misaligned_call",
                    message=f"Stack misaligned at CALL {address:#x}: RSP={rsp:#x} (expected 8 mod 16)",
                )
            )

        # Check Win64 shadow space (32 bytes)
        # Would need to know if we're in Win64 mode

    def hook_insn_ret(self, uc, address: int, size: int, user_data):
        """Hook for RET instructions - check stack balance."""
        # Stack should be balanced at return
        # This is a runtime check - static check in V3 is more comprehensive
        pass


def install_hooks(uc, ctx: HookContext) -> None:
    """Install all V4 hooks on a Unicorn engine."""
    if not UNICORN_AVAILABLE:
        return

    dispatcher = HookDispatcher(ctx)

    # General code hook
    uc.hook_add(UC_HOOK_CODE, dispatcher.hook_code)

    # Memory hooks
    uc.hook_add(UC_HOOK_MEM_WRITE, dispatcher.hook_mem_write)
    uc.hook_add(UC_HOOK_MEM_READ, dispatcher.hook_mem_read)

    # Syscall hook
    uc.hook_add(UC_HOOK_INSN, dispatcher.hook_syscall, None, 1, 0, UC_X86_INS_SYSCALL)
    uc.hook_add(UC_HOOK_INSN, dispatcher.hook_syscall, None, 1, 0, UC_X86_INS_SYSENTER)

    # Note: CALL and RET hooks would need instruction-specific hooks
    # which Unicorn supports via UC_HOOK_INSN with specific instruction IDs
    # but x86 CALL/RET don't have dedicated IDs in Unicorn


def create_hook_context(
    canary_manager: CanaryManager = None,
    dwarf_map: Any = None,
    mock_registry: Any = None,
    stack_base: int = 0,
    stack_top: int = 0,
    max_instructions: int = 1_000_000,
) -> HookContext:
    """Create a hook context with the given parameters."""
    return HookContext(
        canary_manager=canary_manager,
        dwarf_map=dwarf_map,
        mock_registry=mock_registry,
        stack_base=stack_base,
        stack_top=stack_top,
        max_instructions=max_instructions,
    )


class CallAlignmentChecker:
    """Pre-pass to identify call sites and verify alignment."""

    def __init__(self, code: bytes, base_addr: int):
        self.code = code
        self.base_addr = base_addr
        self.call_sites: list[int] = []

    def analyze(self) -> list[int]:
        """Find all CALL instructions and their addresses."""
        if not UNICORN_AVAILABLE:
            return []

        try:
            from capstone import CS_ARCH_X86, CS_MODE_64, Cs
        except ImportError:
            return []

        md = Cs(CS_ARCH_X86, CS_MODE_64)
        md.detail = True

        for insn in md.disasm(self.code, self.base_addr):
            if insn.mnemonic == "call":
                self.call_sites.append(insn.address)

        return self.call_sites

    def check_alignment_at_calls(self, uc) -> list[Diagnostic]:
        """Check stack alignment at each call site (would need to be done at runtime)."""
        diagnostics = []
        for _site in self.call_sites:
            # This would need to be checked when the call is actually executed
            # via a hook at that specific address
            pass
        return diagnostics


class MemoryAccessTracker:
    """Track memory accesses for buffer overflow detection."""

    def __init__(self):
        self.allocated_regions: list[tuple[int, int, str]] = []  # (start, end, name)
        self.accessed_regions: list[tuple[int, int, str]] = []  # (addr, size, type)

    def add_region(self, start: int, end: int, name: str) -> None:
        """Register an allocated memory region."""
        self.allocated_regions.append((start, end, name))

    def record_access(self, address: int, size: int, access_type: str) -> bool:
        """Record a memory access and check if it's valid."""
        self.accessed_regions.append((address, size, access_type))

        # Check if access is within any allocated region
        for start, end, _name in self.allocated_regions:
            if start <= address < end and start <= address + size <= end:
                return True

        return False  # Access outside allocated regions

    def get_violations(self) -> list[Diagnostic]:
        """Get diagnostics for memory access violations."""
        diagnostics = []
        for address, size, access_type in self.accessed_regions:
            valid = False
            for start, end, _name in self.allocated_regions:
                if start <= address < end and start <= address + size <= end:
                    valid = True
                    break
            if not valid:
                diagnostics.append(
                    Diagnostic(
                        tool="unicorn",
                        level=DiagnosticLevel.V4,
                        severity=Severity.FATAL,
                        code="abi.buffer_overflow",
                        message=f"Memory {access_type} outside allocated region: {address:#x}+{size}",
                    )
                )
        return diagnostics
