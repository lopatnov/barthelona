"""Load a relocatable x86-64 ELF object (``nasm -f elf64``, ``as``) into memory without linking it.

Sections that occupy memory are laid out one page apart from ``IMAGE_BASE``, relocations are applied and every
undefined symbol is bound to a one-instruction ``ret`` stub, so a function that calls an external helper
can be emulated on a host that has no linker. Only the relocation types an assembler emits for plain code
are handled; anything else raises ``ImageError`` rather than guessing.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from elftools.common.exceptions import ELFError
from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection
from elftools.elf.sections import Section, SymbolTableSection

IMAGE_BASE = 0x400000
STUB_BASE = 0x7000_0000
PAGE = 0x1000
_SHF_WRITE, _SHF_ALLOC, _SHF_EXEC = 0x1, 0x2, 0x4
_R_64, _R_PC32, _R_PLT32, _R_32, _R_32S = 1, 2, 4, 10, 11
_STUB_CODE = b"\xc3"  # ret


class ImageError(ValueError):
    """The object is not a relocatable x86-64 ELF or needs something this loader does not support."""


@dataclass(frozen=True)
class Region:
    address: int
    data: bytes
    size: int
    writable: bool
    executable: bool


@dataclass(frozen=True)
class Image:
    regions: tuple[Region, ...]
    symbols: dict[str, int]  # defined named symbols -> address
    stubs: dict[str, int]  # undefined (external) symbols -> stub address


def _page_up(value: int) -> int:
    return (value + PAGE - 1) & ~(PAGE - 1)


def open_object(blob: bytes) -> ELFFile:
    try:
        elf = ELFFile(io.BytesIO(blob))
    except ELFError as exc:
        raise ImageError(f"not an ELF file: {exc}") from exc
    if elf.header["e_type"] != "ET_REL" or elf["e_machine"] != "EM_X86_64":
        raise ImageError("only relocatable x86-64 objects are supported")
    return elf


def _layout(elf: ELFFile) -> tuple[dict[int, int], list[Region], dict[int, bytearray]]:
    addresses: dict[int, int] = {}
    regions: list[Region] = []
    contents: dict[int, bytearray] = {}
    cursor = IMAGE_BASE
    for index, section in enumerate(elf.iter_sections()):
        flags = section["sh_flags"]
        if not flags & _SHF_ALLOC or section["sh_size"] == 0:
            continue
        addresses[index] = cursor
        data = bytearray(b"" if section["sh_type"] == "SHT_NOBITS" else section.data())
        contents[index] = data
        regions.append(
            Region(cursor, b"", section["sh_size"], bool(flags & _SHF_WRITE), bool(flags & _SHF_EXEC))
        )
        cursor += _page_up(section["sh_size"])
    return addresses, regions, contents


def _symbol_table(elf: ELFFile) -> SymbolTableSection:
    table = elf.get_section_by_name(".symtab")
    if not isinstance(table, SymbolTableSection):
        raise ImageError("the object has no symbol table")
    return table


def _symbol_addresses(
    table: SymbolTableSection, addresses: dict[int, int]
) -> tuple[list[int], dict[str, int], dict[str, int]]:
    by_index: list[int] = []
    named: dict[str, int] = {}
    stubs: dict[str, int] = {}
    for symbol in table.iter_symbols():
        shndx = symbol["st_shndx"]
        if shndx == "SHN_UNDEF":
            address = 0
            if symbol.name:
                address = stubs.setdefault(symbol.name, STUB_BASE + PAGE * (len(stubs) + 1))
        elif shndx == "SHN_ABS":
            address = symbol["st_value"]
        elif isinstance(shndx, int) and shndx in addresses:
            address = addresses[shndx] + symbol["st_value"]
            if symbol.name:
                named[symbol.name] = address
        else:
            address = 0
        by_index.append(address)
    return by_index, named, stubs


def _patch(data: bytearray, offset: int, value: int, size: int, signed: bool) -> None:
    low, high = (-(1 << (8 * size - 1)), (1 << (8 * size - 1)) - 1) if signed else (0, (1 << (8 * size)) - 1)
    if not low <= value <= high:
        raise ImageError(f"relocation value {value:#x} does not fit in {size} bytes")
    data[offset : offset + size] = value.to_bytes(size, "little", signed=signed)


def _relocate(
    elf: ELFFile, addresses: dict[int, int], contents: dict[int, bytearray], symbol_address: list[int]
) -> None:
    for section in elf.iter_sections():
        if not isinstance(section, RelocationSection):
            continue
        target = section["sh_info"]
        if target not in contents:
            continue
        data = contents[target]
        for reloc in section.iter_relocations():
            place = addresses[target] + reloc["r_offset"]
            value = symbol_address[reloc["r_info_sym"]] + reloc["r_addend"]
            kind = reloc["r_info_type"]
            if kind == _R_64:
                _patch(data, reloc["r_offset"], value, 8, False)
            elif kind in (_R_PC32, _R_PLT32):
                _patch(data, reloc["r_offset"], value - place, 4, True)
            elif kind == _R_32:
                _patch(data, reloc["r_offset"], value, 4, False)
            elif kind == _R_32S:
                _patch(data, reloc["r_offset"], value, 4, True)
            else:
                raise ImageError(f"unsupported relocation type {kind}")


def load_object(blob: bytes) -> Image:
    """The relocated image of the object in *blob*."""
    elf = open_object(blob)
    addresses, regions, contents = _layout(elf)
    by_index, named, stubs = _symbol_addresses(_symbol_table(elf), addresses)
    _relocate(elf, addresses, contents, by_index)
    filled = tuple(
        Region(region.address, bytes(contents[index]), region.size, region.writable, region.executable)
        for (index, _), region in zip(contents.items(), regions, strict=True)
    )
    stub_regions = tuple(Region(address, _STUB_CODE, PAGE, False, True) for address in stubs.values())
    return Image(filled + stub_regions, named, stubs)


def section_names(blob: bytes) -> list[str]:
    """Section names of the object, in file order."""
    return [section.name for section in open_object(blob).iter_sections() if isinstance(section, Section)]
