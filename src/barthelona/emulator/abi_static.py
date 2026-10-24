"""V3: static ABI lint of a relocatable object (Capstone over each function, relocations, section names).

Detects the corpus kinds that need no execution: ``missing_gnu_stack``, ``pie_absolute_reference``,
``syscall_clobber`` and ``red_zone_write``. The dynamic kinds (alignment, callee-saved registers, stack
balance, direction flag) are found by running the function (``machine.run_function``).
"""

from __future__ import annotations

from collections.abc import Iterator

from capstone import CS_AC_WRITE, CS_ARCH_X86, CS_MODE_64, Cs, CsInsn
from capstone import x86_const as x86
from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection
from elftools.elf.sections import SymbolTableSection

from barthelona.emulator.machine import Violation
from barthelona.emulator.object_image import open_object, section_names

_SHF_EXEC = 0x4
_ABSOLUTE_32 = (10, 11)  # R_X86_64_32, R_X86_64_32S
_SYSCALL_CLOBBERED = {
    "rcx": {"rcx", "ecx", "cx", "cl", "ch"},
    "r11": {"r11", "r11d", "r11w", "r11b"},
}


def _functions(elf: ELFFile) -> Iterator[tuple[str, bytes]]:
    """(name, code) of every named symbol in an executable section, up to the next symbol."""
    table = elf.get_section_by_name(".symtab")
    if not isinstance(table, SymbolTableSection):
        return
    symbols = [s for s in table.iter_symbols() if s.name and isinstance(s["st_shndx"], int)]
    for index, section in enumerate(elf.iter_sections()):
        if not section["sh_flags"] & _SHF_EXEC:
            continue
        inside = sorted((s for s in symbols if s["st_shndx"] == index), key=lambda s: s["st_value"])
        data = section.data()
        for position, symbol in enumerate(inside):
            end = inside[position + 1]["st_value"] if position + 1 < len(inside) else len(data)
            if end > symbol["st_value"]:
                yield symbol.name, data[symbol["st_value"] : end]


def _absolute_relocations(elf: ELFFile) -> list[Violation]:
    found: list[Violation] = []
    for section in elf.iter_sections():
        if not isinstance(section, RelocationSection):
            continue
        target = elf.get_section(section["sh_info"])
        if not target["sh_flags"] & _SHF_EXEC:
            continue
        symbols = elf.get_section(section["sh_link"])
        if not isinstance(symbols, SymbolTableSection):
            continue
        for reloc in section.iter_relocations():
            if reloc["r_info_type"] in _ABSOLUTE_32:
                name = symbols.get_symbol(reloc["r_info_sym"]).name or "a section"
                found.append(
                    Violation(
                        "pie_absolute_reference",
                        f"{target.name}+{reloc['r_offset']:#x}: absolute 32-bit address of {name}; "
                        "use a RIP-relative one",
                    )
                )
    return found


def _family(insn: CsInsn, registers: list[int]) -> set[str]:
    names = {insn.reg_name(reg) for reg in registers}
    return {base for base, aliases in _SYSCALL_CLOBBERED.items() if names & aliases}


def _is_zeroing(insn: CsInsn) -> bool:
    ops = insn.operands
    return (
        insn.mnemonic in ("xor", "sub")
        and len(ops) == 2
        and ops[0].type == ops[1].type == x86.X86_OP_REG
        and ops[0].reg == ops[1].reg
    )


def _syscall_clobbers(name: str, instructions: list[CsInsn]) -> list[Violation]:
    clobbered: set[str] = set()
    for insn in instructions:
        if insn.mnemonic == "syscall":
            clobbered = set(_SYSCALL_CLOBBERED)
            continue
        read, written = insn.regs_access()
        used = clobbered & _family(insn, read if not _is_zeroing(insn) else [])
        if used:
            return [
                Violation(
                    "syscall_clobber",
                    f"{name}+{insn.address:#x}: {insn.mnemonic} reads "
                    f"{', '.join(sorted(used))} after a syscall",
                )
            ]
        clobbered -= _family(insn, written)
        if insn.mnemonic in ("ret", "jmp", "call"):
            clobbered.clear()
    return []


def _writes_below_rsp(insn: CsInsn) -> bool:
    return any(
        op.type == x86.X86_OP_MEM
        and op.mem.base == x86.X86_REG_RSP
        and op.mem.disp < 0
        and op.access & CS_AC_WRITE
        for op in insn.operands
    )


def _red_zone(name: str, instructions: list[CsInsn]) -> list[Violation]:
    if not any(insn.mnemonic == "call" for insn in instructions):
        return []
    return [
        Violation(
            "red_zone_write", f"{name}+{insn.address:#x}: write below rsp in a function that makes a call"
        )
        for insn in instructions
        if _writes_below_rsp(insn)
    ][:1]


def lint_object(blob: bytes) -> list[Violation]:
    """The static ABI violations of the relocatable object in *blob* (empty when it is clean)."""
    elf = open_object(blob)
    found: list[Violation] = []
    if ".note.GNU-stack" not in section_names(blob):
        found.append(
            Violation(
                "missing_gnu_stack", "no .note.GNU-stack section: the linker will make the stack executable"
            )
        )
    found += _absolute_relocations(elf)
    disassembler = Cs(CS_ARCH_X86, CS_MODE_64)
    disassembler.detail = True
    for name, code in _functions(elf):
        instructions = list(disassembler.disasm(code, 0))
        found += _syscall_clobbers(name, instructions)
        found += _red_zone(name, instructions)
    return found
