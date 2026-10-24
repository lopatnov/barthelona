"""DWARF debugging information mapping: PC → file:line.

Uses pyelftools DWARF parsing to map program counter addresses to source locations.
This is needed for both V3 (static lint diagnostics) and V4 (emulation fault mapping).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class SourceLocation:
    """A source code location."""

    file: str
    line: int
    column: int = 0
    function: str | None = None
    inlined: bool = False


@dataclass
class DwarfMap:
    """Mapping from PC addresses to source locations."""

    # Sorted list of (pc_start, pc_end, location) for binary search
    ranges: list[tuple[int, int, SourceLocation]] = None
    # Map of function names to their entry PC
    functions: dict[str, int] = None

    def __post_init__(self):
        if self.ranges is None:
            self.ranges = []
        if self.functions is None:
            self.functions = {}

    def lookup(self, pc: int) -> SourceLocation | None:
        """Find source location for a PC address using binary search."""
        if not self.ranges:
            return None

        lo, hi = 0, len(self.ranges) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            start, end, loc = self.ranges[mid]
            if pc < start:
                hi = mid - 1
            elif pc >= end:
                lo = mid + 1
            else:
                return loc
        return None

    def add_range(self, start: int, end: int, loc: SourceLocation) -> None:
        """Add a PC range mapping."""
        self.ranges.append((start, end, loc))
        # Keep sorted by start address
        self.ranges.sort(key=lambda x: x[0])


def build_dwarf_map(elf_path: Path) -> DwarfMap | None:
    """Build PC → source location map from ELF DWARF info."""
    try:
        from elftools.dwarf.descriptions import describe_form_class
        from elftools.dwarf.dwarfinfo import DWARFInfo
        from elftools.dwarf.lineprogram import LineProgram
        from elftools.elf.elffile import ELFFile
    except ImportError:
        return None

    try:
        with open(elf_path, "rb") as f:
            elffile = ELFFile(f)

            if not elffile.has_dwarf_info():
                return None

            dwarfinfo = elffile.get_dwarf_info()
            dwarf_map = DwarfMap()

            # Parse line number program
            for cu in dwarfinfo.iter_CUs():
                lineprog = dwarfinfo.line_program_for_CU(cu)
                if not lineprog:
                    continue

                # Get compilation directory
                comp_dir = cu.get_top_DIE().attributes.get("DW_AT_comp_dir")
                comp_dir = comp_dir.value.decode("utf-8") if comp_dir else ""

                # Get file name table
                file_entries = lineprog["file_entry"]

                # Process line program
                prev_state = None
                for entry in lineprog.get_entries():
                    if entry.state is None:
                        continue

                    state = entry.state
                    if state.end_sequence:
                        prev_state = None
                        continue

                    pc = state.address
                    line = state.line
                    file_idx = state.file - 1  # 1-based in DWARF

                    if file_idx >= 0 and file_idx < len(file_entries):
                        file_entry = file_entries[file_idx]
                        file_name = (
                            file_entry.name.decode("utf-8")
                            if isinstance(file_entry.name, bytes)
                            else file_entry.name
                        )
                        dir_idx = file_entry.dir_index - 1
                        if dir_idx >= 0 and "include_directory" in lineprog.header:
                            dir_name = lineprog.header["include_directory"][dir_idx]
                            dir_name = dir_name.decode("utf-8") if isinstance(dir_name, bytes) else dir_name
                            full_path = f"{dir_name}/{file_name}"
                        else:
                            full_path = file_name

                        SourceLocation(
                            file=full_path,
                            line=line,
                            column=state.column or 0,
                        )

                        if prev_state and prev_state.address != pc:
                            # Add range from previous PC to current PC
                            dwarf_map.add_range(prev_state.address, pc, prev_loc)

                        prev_state = state

            # Parse function DIEs for function entry points
            for cu in dwarfinfo.iter_CUs():
                for die in cu.iter_DIEs():
                    if die.tag == "DW_TAG_subprogram":
                        name_attr = die.attributes.get("DW_AT_name")
                        low_pc_attr = die.attributes.get("DW_AT_low_pc")
                        die.attributes.get("DW_AT_high_pc")

                        if name_attr and low_pc_attr:
                            name = (
                                name_attr.value.decode("utf-8")
                                if isinstance(name_attr.value, bytes)
                                else name_attr.value
                            )
                            low_pc = low_pc_attr.value
                            dwarf_map.functions[name] = low_pc

            return dwarf_map
    except Exception:
        return None


def get_function_name(dwarf_map: DwarfMap, pc: int) -> str | None:
    """Get function name containing PC."""
    for name, addr in dwarf_map.functions.items():
        # Simple check - in practice would need function size
        if addr <= pc < addr + 1000:  # rough estimate
            return name
    return None
