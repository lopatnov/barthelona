"""V4: Dynamic ABI checks using Unicorn emulation.

Architecture §13.1 "How V4 works":
1. Image: Link module at fixed base in bart-tc, load segments with pyelftools
2. Memory: Stack with guard pages, rsp ≡ 8 (mod 16), return address → trap
3. Canaries: Callee-saved registers seeded with canaries
   - SysV: rbx, rbp, r12–r15
   - Win64: those plus rdi, rsi, xmm6–15
4. Hooks:
   - Calls: alignment at each call site (Capstone pre-pass), Win64 shadow space
   - Memory writes: red zone, return-address slot, outside declared buffers
   - Syscalls/interrupts: allow-list only — write → captured stdout, exit
5. Imports: Served by Python mocks from registry (mock stubs between sprints)
6. Limits: Instruction-count cap, microsecond timeout
7. Error mapping: Faulting PC → file:line via DWARF
8. AVX: Unicorn rejects 256-bit VEX; route to V5 (setup probe confirms)

Only enabled for mutation-corpus kinds where V3 + V5 canary miss (roadmap #102).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from barthelona.domain.contracts import ContractRegistry
from barthelona.domain.enums import DiagnosticLevel, Level
from barthelona.domain.verification import Diagnostic, LevelResult, Severity
from barthelona.verification.registry import LadderContext, Unsupported


@dataclass
class EmulatorConfig:
    """Configuration for the Unicorn emulator."""

    instruction_limit: int = 1_000_000
    timeout_us: int = 100_000  # 100ms
    stack_size: int = 1024 * 1024  # 1MB
    guard_page_size: int = 4096
    base_address: int = 0x400000


@dataclass
class EmulationResult:
    """Result of emulating one test case."""

    success: bool
    exit_code: int = 0
    stdout: bytes = b""
    stderr: bytes = b""
    diagnostics: list[Diagnostic] = field(default_factory=list)
    instructions_executed: int = 0
    error_pc: int | None = None
    error_message: str | None = None


class UnicornEmulator:
    """Unicorn-based x86-64 emulator for ABI contract checking."""

    def __init__(self, config: EmulatorConfig | None = None):
        self.config = config or EmulatorConfig()
        self._uc = None
        self._hooks = {}
        self._mock_functions = {}
        self._canary_values = {}
        self._instruction_count = 0

    def _init_unicorn(self) -> bool:
        """Initialize Unicorn engine."""
        try:
            from unicorn import UC_ARCH_X86, UC_MODE_64, Uc
            from unicorn.x86_const import (
                UC_X86_REG_R8,
                UC_X86_REG_R9,
                UC_X86_REG_R10,
                UC_X86_REG_R11,
                UC_X86_REG_R12,
                UC_X86_REG_R13,
                UC_X86_REG_R14,
                UC_X86_REG_R15,
                UC_X86_REG_RAX,
                UC_X86_REG_RBP,
                UC_X86_REG_RBX,
                UC_X86_REG_RCX,
                UC_X86_REG_RDI,
                UC_X86_REG_RDX,
                UC_X86_REG_RFLAGS,
                UC_X86_REG_RIP,
                UC_X86_REG_RSI,
                UC_X86_REG_RSP,
            )

            self._uc = Uc(UC_ARCH_X86, UC_MODE_64)
            return True
        except ImportError:
            return False
        except Exception:
            return False

    def load_elf(self, elf_path: Path, contracts: ContractRegistry) -> bool:
        """Load ELF file into emulator memory using pyelftools."""
        try:
            from elftools.elf.elffile import ELFFile
            from elftools.elf.sections import Section
        except ImportError:
            return False

        try:
            with open(elf_path, "rb") as f:
                elffile = ELFFile(f)

                # Load PT_LOAD segments
                for segment in elffile.iter_segments():
                    if segment["p_type"] == "PT_LOAD":
                        vaddr = segment["p_vaddr"]
                        memsz = segment["p_memsz"]
                        data = segment.data()

                        # Map memory
                        perms = 0
                        if segment["p_flags"] & 0x4:  # PF_R
                            perms |= 1  # UC_PROT_READ
                        if segment["p_flags"] & 0x2:  # PF_W
                            perms |= 2  # UC_PROT_WRITE
                        if segment["p_flags"] & 0x1:  # PF_X
                            perms |= 4  # UC_PROT_EXEC

                        self._uc.mem_map(vaddr, memsz, perms)
                        if data:
                            self._uc.mem_write(vaddr, data)

                # Set entry point
                self._uc.reg_write(UC_X86_REG_RIP, elffile.header["e_entry"])
                return True
        except Exception:
            return False

    def setup_stack(self) -> bool:
        """Set up stack with guard pages."""
        stack_top = self.config.base_address + 0x100000  # 1MB above base
        stack_base = stack_top - self.config.stack_size

        try:
            # Map stack memory
            self._uc.mem_map(stack_base, self.config.stack_size, 7)  # RWX

            # Map guard pages (unmapped)
            # Guard below stack
            self._uc.mem_unmap(stack_base - self.config.guard_page_size, self.config.guard_page_size)
            # Guard above stack
            self._uc.mem_unmap(stack_top, self.config.guard_page_size)

            # Set RSP ≡ 8 (mod 16)
            rsp = stack_top - 8  # 8 mod 16
            self._uc.reg_write(UC_X86_REG_RSP, rsp)

            # Set return address to trap
            trap_addr = self.config.base_address + 0x1000
            self._uc.mem_write(rsp, trap_addr.to_bytes(8, "little"))

            return True
        except Exception:
            return False

    def setup_canaries(self, abi: str = "sysv64") -> bool:
        """Seed callee-saved registers with canary values."""
        canary_regs = {
            "sysv64": [
                UC_X86_REG_RBX,
                UC_X86_REG_RBP,
                UC_X86_REG_R12,
                UC_X86_REG_R13,
                UC_X86_REG_R14,
                UC_X86_REG_R15,
            ],
            "win64": [
                UC_X86_REG_RBX,
                UC_X86_REG_RBP,
                UC_X86_REG_R12,
                UC_X86_REG_R13,
                UC_X86_REG_R14,
                UC_X86_REG_R15,
                UC_X86_REG_RDI,
                UC_X86_REG_RSI,
                # XMM6-15 would need FPU register access
            ],
        }

        regs = canary_regs.get(abi, canary_regs["sysv64"])

        for i, reg in enumerate(regs):
            canary = 0xDEADBEEFCAFEBABE + i
            self._canary_values[reg] = canary
            self._uc.reg_write(reg, canary)

        return True

    def verify_canaries(self) -> list[Diagnostic]:
        """Check that callee-saved registers still have their canary values."""
        diagnostics = []
        for reg, expected in self._canary_values.items():
            actual = self._uc.reg_read(reg)
            if actual != expected:
                diagnostics.append(
                    Diagnostic(
                        tool="unicorn",
                        level=DiagnosticLevel.V4,
                        severity=Severity.FATAL,
                        code="abi.callee_saved_clobbered",
                        message=f"Callee-saved register {reg} modified (expected {expected:#x}, got {actual:#x})",
                    )
                )
        return diagnostics

    def setup_hooks(self, contracts: ContractRegistry) -> bool:
        """Set up Unicorn hooks for calls, memory, syscalls."""
        try:
            from unicorn import UC_HOOK_CODE, UC_HOOK_INSN, UC_HOOK_MEM_WRITE
            from unicorn.x86_const import UC_X86_INS_SYSCALL, UC_X86_INS_SYSENTER
        except ImportError:
            return False

        # Hook for instruction execution (call alignment, etc.)
        self._uc.hook_add(UC_HOOK_CODE, self._hook_code)

        # Hook for memory writes (red zone, return address, buffer overflows)
        self._uc.hook_add(UC_HOOK_MEM_WRITE, self._hook_mem_write)

        # Hook for syscalls
        self._uc.hook_add(UC_HOOK_INSN, self._hook_syscall, None, 1, 0, UC_X86_INS_SYSCALL)
        self._uc.hook_add(UC_HOOK_INSN, self._hook_syscall, None, 1, 0, UC_X86_INS_SYSENTER)

        return True

    def _hook_code(self, uc, address: int, size: int, user_data):
        """Hook for every instruction - check call alignment, instruction count."""
        self._instruction_count += 1

        if self._instruction_count > self.config.instruction_limit:
            uc.emu_stop()
            return

        # Check for call instructions
        # This is a simplified check - real implementation would use Capstone pre-pass
        # to identify call sites and verify alignment

        # Check for AVX instructions (Unicorn will fault on 256-bit VEX)
        # The fault will be caught by the mem_invalid hook

    def _hook_mem_write(self, uc, access: int, address: int, size: int, value: int, user_data):
        """Hook for memory writes - check red zone, return address, buffer overflows."""
        rsp = uc.reg_read(UC_X86_REG_RSP)

        # Check red zone (128 bytes below RSP)
        if rsp - 128 <= address < rsp:
            # Red zone write - could be a violation
            pass  # Report via diagnostic

        # Check return address slot
        if address == rsp:
            # Writing to return address - potential ROP or corruption
            pass

        # Check stack guard pages
        # Would need to track stack boundaries

    def _hook_syscall(self, uc, user_data):
        """Hook for syscall/sysenter - allow-list only."""
        rax = uc.reg_read(UC_X86_REG_RAX)

        # Linux x86-64 syscall numbers
        SYS_WRITE = 1
        SYS_EXIT = 60
        SYS_EXIT_GROUP = 231

        if rax == SYS_WRITE:
            # write(fd, buf, count)
            fd = uc.reg_read(UC_X86_REG_RDI)
            buf = uc.reg_read(UC_X86_REG_RSI)
            count = uc.reg_read(UC_X86_REG_RDX)

            if fd == 1 or fd == 2:  # stdout/stderr
                uc.mem_read(buf, count)
                # Capture stdout
                pass
            uc.reg_write(UC_X86_REG_RAX, count)  # return bytes written

        elif rax in (SYS_EXIT, SYS_EXIT_GROUP):
            # exit/exit_group
            uc.reg_read(UC_X86_REG_RDI)
            uc.emu_stop()
            # Store exit code for result

        else:
            # Syscall not allowed
            uc.emu_stop()
            # Report violation

    def run_test(self, entry_point: int, args: list[int] | None = None) -> EmulationResult:
        """Run emulation from entry point with given arguments."""
        result = EmulationResult(success=False)

        if not self._uc:
            result.error_message = "Unicorn not initialized"
            return result

        try:
            # Set up arguments if provided (SysV: RDI, RSI, RDX, RCX, R8, R9)
            if args:
                arg_regs = [
                    UC_X86_REG_RDI,
                    UC_X86_REG_RSI,
                    UC_X86_REG_RDX,
                    UC_X86_REG_RCX,
                    UC_X86_REG_R8,
                    UC_X86_REG_R9,
                ]
                for i, arg in enumerate(args):
                    if i < len(arg_regs):
                        self._uc.reg_write(arg_regs[i], arg)

            # Start emulation
            self._uc.emu_start(entry_point, 0, self.config.timeout_us, self.config.instruction_limit)

            # Check canaries after emulation
            canary_diags = self.verify_canaries()
            result.diagnostics.extend(canary_diags)

            result.success = len(canary_diags) == 0
            result.instructions_executed = self._instruction_count

        except Exception as e:
            result.error_message = str(e)
            result.error_pc = self._uc.reg_read(UC_X86_REG_RIP) if self._uc else None

        return result


def run_v4_unicorn(
    ctx: LadderContext,
    command_timeout: float = 30.0,
) -> LevelResult:
    """V4: Dynamic ABI checks using Unicorn emulation."""

    t0 = time.monotonic()
    diagnostics: list[Diagnostic] = []

    diagnostics.append(
        Diagnostic(
            tool="unicorn",
            level=DiagnosticLevel.V4,
            severity=Severity.NOTE,
            code="v4.not_implemented",
            message="V4 dynamic ABI checks (Unicorn) not yet implemented",
            file=None,
        )
    )

    return LevelResult(
        level=Level.V4,
        status="unsupported",
        diagnostics=diagnostics,
        secs=time.monotonic() - t0,
    )


class DynamicCheck:
    """V4 as a registered check."""

    level = Level.V4
    always_run = False

    def supports(self, ctx: LadderContext) -> Unsupported | None:
        if ctx.contracts is None:
            return Unsupported("V4 requires contract registry for ABI checks and mocks")
        # Check if unicorn is available
        try:
            import unicorn  # noqa: F401
        except ImportError:
            return Unsupported("unicorn not installed")
        # Check if sandbox/executor available for linking
        if ctx.sandbox is None:
            return Unsupported("V4 needs sandbox executor for linking test binaries")
        # Only run for mutation-corpus kinds that V3 + V5 canary miss
        # This would be determined by the test cases provided
        return None

    async def run(self, ctx: LadderContext) -> LevelResult:
        return run_v4_unicorn(ctx)
