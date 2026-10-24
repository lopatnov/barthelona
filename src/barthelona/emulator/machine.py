"""Run an object image in Unicorn: whole programs (stdout, exit code) and single functions (SysV ABI checks).

Generated code never runs on the host: it is emulated, with a small allow-list of Linux syscalls, an
instruction cap and a wall-clock timeout. In function mode the machine also records the ABI violations the
corpus names (``misaligned_call``, ``callee_saved_clobber``, ``unbalanced_stack``, ``df_left_set``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from unicorn import UC_ARCH_X86, UC_HOOK_CODE, UC_HOOK_INSN, UC_MODE_64
from unicorn.unicorn import Uc, UcError
from unicorn.x86_const import (
    UC_X86_INS_SYSCALL,
    UC_X86_REG_EFLAGS,
    UC_X86_REG_R11,
    UC_X86_REG_RAX,
    UC_X86_REG_RCX,
    UC_X86_REG_RDI,
    UC_X86_REG_RDX,
    UC_X86_REG_RIP,
    UC_X86_REG_RSI,
    UC_X86_REG_RSP,
)

from barthelona.emulator.object_image import PAGE, Image

STACK_TOP = 0x7FFF_0000
STACK_SIZE = 0x10000
RETURN_ADDRESS = 0x7FF0_0000
_FIXED_PID = 4242
_DF = 1 << 10
_RET_OPCODES = (0xC3, 0xC2)
_ARG_REGISTERS = ("rdi", "rsi", "rdx", "rcx", "r8", "r9")
_CALLEE_SAVED = ("rbx", "rbp", "r12", "r13", "r14", "r15")
_CANARY = {name: 0xCA11EE5A_00000000 + index for index, name in enumerate(_CALLEE_SAVED)}

Status = Literal["exit", "returned", "fault", "limit", "timeout", "bad_syscall"]


def _register(name: str) -> int:
    from unicorn import x86_const

    return int(getattr(x86_const, f"UC_X86_REG_{name.upper()}"))


@dataclass(frozen=True)
class Violation:
    kind: str
    message: str


@dataclass
class RunResult:
    status: Status
    stdout: bytes = b""
    stderr: bytes = b""
    exit_code: int | None = None
    steps: int = 0
    violations: list[Violation] = field(default_factory=list)
    detail: str = ""


class _Machine:
    def __init__(self, image: Image, stdin: bytes, max_instructions: int, check_abi: bool) -> None:
        self.uc = Uc(UC_ARCH_X86, UC_MODE_64)
        self.result = RunResult("fault")
        self.stdin = stdin
        self.max_instructions = max_instructions
        self.check_abi = check_abi
        self.entry_rsp = 0
        self._previous: tuple[int, int, int] | None = None  # address, size, rsp before it ran
        for region in image.regions:
            self.uc.mem_map(region.address, max(PAGE, -(-region.size // PAGE) * PAGE))
            if region.data:
                self.uc.mem_write(region.address, region.data)
        self.uc.mem_map(STACK_TOP - STACK_SIZE, STACK_SIZE)
        self.uc.hook_add(UC_HOOK_CODE, self._on_instruction)
        self.uc.hook_add(UC_HOOK_INSN, self._on_syscall, None, 1, 0, UC_X86_INS_SYSCALL)

    def _on_instruction(self, uc: Uc, address: int, size: int, _data: object) -> None:
        self.result.steps += 1
        if self.result.steps > self.max_instructions:
            self.result.status = "limit"
            uc.emu_stop()
            return
        rsp = uc.reg_read(UC_X86_REG_RSP)
        if self.check_abi and self._previous is not None:
            self._check_call(uc, address, rsp)
        self._previous = (address, size, rsp)

    def _check_call(self, uc: Uc, address: int, rsp: int) -> None:
        previous, size, previous_rsp = self._previous or (0, 0, 0)
        return_address = previous + size
        if address == return_address or rsp != previous_rsp - 8:
            return
        if int.from_bytes(uc.mem_read(rsp, 8), "little") != return_address or rsp % 16 == 8:
            return
        self.result.violations.append(
            Violation(
                "misaligned_call", f"call at {previous:#x} reaches {address:#x} with rsp % 16 == {rsp % 16}"
            )
        )

    def _on_syscall(self, uc: Uc, _data: object) -> None:
        number = uc.reg_read(UC_X86_REG_RAX)
        rdi, rsi, rdx = (uc.reg_read(r) for r in (UC_X86_REG_RDI, UC_X86_REG_RSI, UC_X86_REG_RDX))
        rip = uc.reg_read(UC_X86_REG_RIP)
        flags = uc.reg_read(UC_X86_REG_EFLAGS)
        if number in (60, 231):
            self.result.status, self.result.exit_code = "exit", rdi & 0xFF
            uc.emu_stop()
            return
        if number == 1 and rdi in (1, 2):
            data = bytes(uc.mem_read(rsi, rdx))
            if rdi == 1:
                self.result.stdout += data
            else:
                self.result.stderr += data
            returned = rdx
        elif number == 0 and rdi == 0:
            data, self.stdin = self.stdin[:rdx], self.stdin[rdx:]
            uc.mem_write(rsi, data)
            returned = len(data)
        elif number == 39:
            returned = _FIXED_PID
        else:
            self.result.status, self.result.detail = "bad_syscall", f"syscall {number} is not allowed"
            uc.emu_stop()
            return
        uc.reg_write(UC_X86_REG_RAX, returned)
        uc.reg_write(UC_X86_REG_RCX, rip + 2)  # the hardware clobbers rcx and r11 on every syscall
        uc.reg_write(UC_X86_REG_R11, flags)

    def start(self, entry: int, until: int, timeout_us: int) -> None:
        try:
            self.uc.emu_start(entry, until, timeout_us)
        except UcError as exc:
            self.result.detail = f"{exc} at {self.uc.reg_read(UC_X86_REG_RIP):#x}"
            self._explain_fault()
            return
        if self.result.status == "fault":  # emu_start returned without a stop request: until or timeout
            at_end = self.uc.reg_read(UC_X86_REG_RIP) == until
            self.result.status = "returned" if at_end else "timeout"

    def _explain_fault(self) -> None:
        if self._previous is None or not self.check_abi:
            return
        address, _, _ = self._previous
        if self.uc.mem_read(address, 1)[0] in _RET_OPCODES:
            self.result.violations.append(
                Violation(
                    "unbalanced_stack",
                    f"ret at {address:#x} did not return to the caller: {self.result.detail}",
                )
            )

    def check_function_exit(self) -> None:
        if self.result.status != "returned":
            return
        rsp = self.uc.reg_read(UC_X86_REG_RSP)
        if rsp != self.entry_rsp + 8:
            self.result.violations.append(
                Violation("unbalanced_stack", f"rsp is {rsp - self.entry_rsp - 8:+d} bytes off at return")
            )
        clobbered = [n for n in _CALLEE_SAVED if self.uc.reg_read(_register(n)) != _CANARY[n]]
        if clobbered:
            self.result.violations.append(
                Violation("callee_saved_clobber", f"callee-saved registers changed: {', '.join(clobbered)}")
            )
        if self.uc.reg_read(UC_X86_REG_EFLAGS) & _DF:
            self.result.violations.append(Violation("df_left_set", "the direction flag is set on return"))


def run_program(
    image: Image,
    entry: int,
    stdin: bytes = b"",
    max_instructions: int = 1_000_000,
    timeout_us: int = 2_000_000,
) -> RunResult:
    """Run a ``_start`` program until it calls exit; the result holds its stdout, stderr and exit code."""
    machine = _Machine(image, stdin, max_instructions, check_abi=False)
    machine.uc.reg_write(UC_X86_REG_RSP, STACK_TOP)
    machine.start(entry, 0, timeout_us)
    return machine.result


def run_function(
    image: Image,
    entry: int,
    args: tuple[int, ...] = (),
    max_instructions: int = 100_000,
    timeout_us: int = 1_000_000,
) -> RunResult:
    """Call a function as a SysV caller would and report the ABI violations seen on the way."""
    machine = _Machine(image, b"", max_instructions, check_abi=True)
    uc = machine.uc
    uc.mem_map(RETURN_ADDRESS, PAGE)
    for name, value in _CANARY.items():
        uc.reg_write(_register(name), value)
    for name, value in zip(_ARG_REGISTERS, args, strict=False):
        uc.reg_write(_register(name), value)
    machine.entry_rsp = STACK_TOP - 8
    uc.mem_write(machine.entry_rsp, RETURN_ADDRESS.to_bytes(8, "little"))
    uc.reg_write(UC_X86_REG_RSP, machine.entry_rsp)
    machine.start(entry, RETURN_ADDRESS, timeout_us)
    machine.check_function_exit()
    return machine.result
