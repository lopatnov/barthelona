"""Registry-driven import mocks for the emulator.

The ContractRegistry has complete ABI information for each symbol:
- inputs/outputs: RegisterContract{reg, type, desc}
- clobbers: list of registers
- mem_effects: list of {arg, access: r|w|rw, size_expr}
- stack: StackContract{entry_align, max_depth, red_zone}
- preconditions, calls

This module generates Python mock functions that can be called from
emulated code via Unicorn hook trampolines.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from barthelona.domain.contracts import ContractRegistry, Symbol


@dataclass
class MockFunction:
    """A mock function that can be called from emulated code."""

    name: str
    symbol: Symbol
    implementation: Callable  # Python function implementing the mock
    trampoline_addr: int = 0  # Address in emulator memory where trampoline lives


@dataclass
class MockRegistry:
    """Registry of all mock functions for an emulation session."""

    mocks: dict[str, MockFunction] = field(default_factory=dict)
    trampoline_base: int = 0x10000000  # High memory for trampolines
    _next_trampoline: int = 0

    def __post_init__(self):
        self._next_trampoline = self.trampoline_base

    def allocate_trampoline(self, size: int = 64) -> int:
        """Allocate space for a trampoline."""
        addr = self._next_trampoline
        self._next_trampoline += size
        # Align to 16 bytes
        self._next_trampoline = (self._next_trampoline + 15) & ~15
        return addr

    def register(self, mock: MockFunction) -> int:
        """Register a mock and return its trampoline address."""
        trampoline_addr = self.allocate_trampoline()
        mock.trampoline_addr = trampoline_addr
        self.mocks[mock.name] = mock
        return trampoline_addr

    def get(self, name: str) -> MockFunction | None:
        """Get a mock by name."""
        return self.mocks.get(name)

    def get_by_address(self, addr: int) -> MockFunction | None:
        """Get a mock by its trampoline address."""
        for mock in self.mocks.values():
            if mock.trampoline_addr == addr:
                return mock
        return None


def create_mock_registry(contracts: ContractRegistry, abi: str = "sysv64") -> MockRegistry:
    """Create a MockRegistry from a ContractRegistry."""
    registry = MockRegistry()

    for _name, symbol in contracts.symbols.items():
        if symbol.visibility == "extern":
            # This is an import - create a mock for it
            mock = create_mock_for_symbol(symbol, abi)
            if mock:
                registry.register(mock)

    return registry


def create_mock_for_symbol(symbol: Symbol, abi: str) -> MockFunction | None:
    """Create a mock function for an extern symbol."""

    # Determine calling convention
    if abi == "sysv64" or abi == "win64":
        pass
    else:
        pass

    def mock_impl(uc, *args, **kwargs) -> int:
        """Default mock implementation - can be overridden per symbol."""
        # Log the call
        print(f"MOCK CALL: {symbol.name} with args={args}")

        # Check preconditions if any
        for _precond in symbol.preconditions:
            # Could evaluate preconditions here
            pass

        # Return a default value based on return type
        if symbol.outputs:
            first_output = symbol.outputs[0]
            if first_output.type in ("u64", "i64", "usize") or first_output.type in ("u32", "i32"):
                return 0
            elif first_output.type in ("ptr",):
                return 0  # NULL pointer
        return 0

    # Create specific mocks for known functions
    if symbol.name in ("write", "read", "open", "close", "exit", "exit_group"):
        mock_impl = create_libc_mock(symbol.name)
    elif symbol.name.startswith("__") or symbol.name.startswith("_"):
        mock_impl = create_compiler_builtin_mock(symbol.name)

    return MockFunction(
        name=symbol.name,
        symbol=symbol,
        implementation=mock_impl,
    )


def create_libc_mock(name: str) -> Callable:
    """Create mock for standard libc functions."""

    if name == "write":

        def write_mock(uc, fd: int, buf: int, count: int) -> int:
            """write(fd, buf, count) -> bytes written"""
            try:
                data = uc.mem_read(buf, count)
                if fd == 1:  # stdout
                    print(data.decode("utf-8", errors="replace"), end="")
                elif fd == 2:  # stderr
                    import sys

                    print(data.decode("utf-8", errors="replace"), end="", file=sys.stderr)
                return count
            except Exception:
                return -1

        return write_mock

    elif name == "read":

        def read_mock(uc, fd: int, buf: int, count: int) -> int:
            """read(fd, buf, count) -> bytes read"""
            return 0  # EOF

        return read_mock

    elif name == "exit":

        def exit_mock(uc, code: int) -> int:
            """exit(code) -> noreturn"""
            uc.emu_stop()
            return 0

        return exit_mock

    elif name == "exit_group":

        def exit_group_mock(uc, code: int) -> int:
            """exit_group(code) -> noreturn"""
            uc.emu_stop()
            return 0

        return exit_group_mock

    # Default
    def default_mock(uc, *args) -> int:
        return 0

    return default_mock


def create_compiler_builtin_mock(name: str) -> Callable:
    """Create mock for compiler builtins (__stack_chk_fail, etc.)."""

    if name == "__stack_chk_fail":

        def stack_chk_fail_mock(uc) -> int:
            """Stack smashing detected - terminate."""
            uc.emu_stop()
            return 0

        return stack_chk_fail_mock

    elif name == "__stack_chk_guard":

        def stack_chk_guard_mock(uc) -> int:
            """Return stack canary value."""
            return 0xDEADBEEFCAFEBABE

        return stack_chk_guard_mock

    # Default
    def default_mock(uc, *args) -> int:
        return 0

    return default_mock


def generate_trampoline_code(mock: MockFunction, abi: str) -> bytes:
    """Generate x86-64 trampoline code for a mock function.

    The trampoline:
    1. Saves volatile registers (caller-saved)
    2. Sets up arguments for Python callback
    3. Calls Python callback via a special mechanism
    4. Restores registers
    5. Returns to caller

    In practice, this would use a Unicorn hook on a specific instruction
    or memory address to transition to Python code.
    """
    # This is a placeholder - real implementation would generate actual
    # machine code for the trampoline. For now, we use Unicorn hooks
    # on specific addresses to detect mock calls.
    return b""


def install_mock_trampolines(uc, mock_registry: MockRegistry, abi: str) -> bool:
    """Install mock trampolines in the emulator memory."""
    try:
        for mock in mock_registry.mocks.values():
            # Write a special instruction sequence that will trigger a hook
            # For example, use an invalid instruction or a specific memory access
            # that we hook on
            trampoline_code = b"\x0f\x0b"  # UD2 - undefined instruction
            uc.mem_write(mock.trampoline_addr, trampoline_code)

            # Map the trampoline address to the symbol name for the hook
            # This would be done by setting up a hook on UD2 instructions
            # and checking the RIP
        return True
    except Exception:
        return False
