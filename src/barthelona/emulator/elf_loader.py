"""ELF loading utilities using pyelftools for the emulator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class ElfSegment:
    """A loadable ELF segment."""

    vaddr: int
    paddr: int
    filesz: int
    memsz: int
    flags: int  # PF_R, PF_W, PF_X
    offset: int
    data: bytes


@dataclass
class ElfInfo:
    """Parsed ELF information."""

    entry_point: int
    segments: list[ElfSegment]
    sections: dict[str, dict]  # name -> {addr, size, data}
    arch: str  # 'x86-64', etc.
    is_pie: bool
    has_gnu_stack: bool
    has_dwarf: bool


PF_R = 0x4
PF_W = 0x2
PF_X = 0x1


def load_elf(elf_path: Path) -> ElfInfo | None:
    """Load and parse an ELF file."""
    try:
        from elftools.dwarf.dwarfinfo import DWARFInfo
        from elftools.elf.elffile import ELFFile
        from elftools.elf.sections import Section, SymbolTableSection
        from elftools.elf.segments import Segment
    except ImportError:
        return None

    try:
        with open(elf_path, "rb") as f:
            elffile = ELFFile(f)

            # Check architecture
            if elffile.get_machine_arch() not in ("x64", "x86-64", "AMD64"):
                return None

            # Parse segments
            segments = []
            for segment in elffile.iter_segments():
                if isinstance(segment, Segment) and segment["p_type"] == "PT_LOAD":
                    seg = ElfSegment(
                        vaddr=segment["p_vaddr"],
                        paddr=segment["p_paddr"],
                        filesz=segment["p_filesz"],
                        memsz=segment["p_memsz"],
                        flags=segment["p_flags"],
                        offset=segment["p_offset"],
                        data=segment.data(),
                    )
                    segments.append(seg)

            # Parse sections
            sections = {}
            has_gnu_stack = False
            has_dwarf = False
            for section in elffile.iter_sections():
                if isinstance(section, Section):
                    sec_info = {
                        "addr": section["sh_addr"],
                        "size": section["sh_size"],
                        "offset": section["sh_offset"],
                        "type": section["sh_type"],
                        "flags": section["sh_flags"],
                    }
                    if section.data():
                        sec_info["data"] = section.data()
                    sections[section.name] = sec_info

                    if section.name == ".note.GNU-stack":
                        has_gnu_stack = True
                    if section.name.startswith(".debug_"):
                        has_dwarf = True

            # Check for DWARF info
            if has_dwarf:
                try:
                    dwarfinfo = elffile.get_dwarf_info()
                    has_dwarf = dwarfinfo is not None
                except Exception:
                    has_dwarf = False

            # Check if PIE
            is_pie = elffile.header["e_type"] == "ET_DYN"

            return ElfInfo(
                entry_point=elffile.header["e_entry"],
                segments=segments,
                sections=sections,
                arch="x86-64",
                is_pie=is_pie,
                has_gnu_stack=has_gnu_stack,
                has_dwarf=has_dwarf,
            )
    except Exception:
        return None


def get_section_data(elf_info: ElfInfo, section_name: str) -> bytes | None:
    """Get raw data of a section."""
    if section_name in elf_info.sections:
        sec = elf_info.sections[section_name]
        return sec.get("data")
    return None


def get_symbol_table(elf_path: Path) -> dict[str, int]:
    """Extract symbol table as name -> address mapping."""
    try:
        from elftools.elf.elffile import ELFFile
        from elftools.elf.sections import SymbolTableSection
    except ImportError:
        return {}

    try:
        with open(elf_path, "rb") as f:
            elffile = ELFFile(f)
            symbols = {}

            for section in elffile.iter_sections():
                if isinstance(section, SymbolTableSection):
                    for symbol in section.iter_symbols():
                        if (
                            symbol["st_info"]["type"] == "STT_FUNC"
                            or symbol["st_info"]["type"] == "STT_OBJECT"
                        ):
                            name = symbol.name
                            if name:
                                symbols[name] = symbol["st_value"]
            return symbols
    except Exception:
        return {}


def find_function_bounds(elf_path: Path, func_name: str) -> tuple[int, int] | None:
    """Find start and end address of a function."""
    try:
        from elftools.elf.elffile import ELFFile
        from elftools.elf.sections import SymbolTableSection
    except ImportError:
        return None

    try:
        with open(elf_path, "rb") as f:
            elffile = ELFFile(f)

            for section in elffile.iter_sections():
                if isinstance(section, SymbolTableSection):
                    for symbol in section.iter_symbols():
                        if symbol.name == func_name and symbol["st_info"]["type"] == "STT_FUNC":
                            start = symbol["st_value"]
                            size = symbol["st_size"]
                            return (start, start + size)
            return None
    except Exception:
        return None
