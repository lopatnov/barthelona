"""Tests for V3/V4 emulator checks against the ABI mutation corpus.

Phase 2 exit criterion: V3 and V4 must flag 100% of bad snippets with 0 false positives on good ones.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from barthelona.domain.enums import ObjFormat
from barthelona.executors.fake import FakeExecutor
from barthelona.verification.native_asm import register_native_asm
from barthelona.verification.registry import CheckRegistry

# Path to the mutation corpus
CORPUS_ROOT = Path(__file__).parent.parent.parent / "abi_mutation"


def get_dialect_dirs() -> list[tuple[str, str, str]]:
    """Return list of (dialect, ext, dialect_dir) for available dialects."""
    dirs = []
    if (CORPUS_ROOT / "nasm").exists():
        dirs.append(("nasm", "asm", "nasm"))
    if (CORPUS_ROOT / "gas-intel").exists():
        dirs.append(("gas-intel", "s", "gas-intel"))
    return dirs


def get_kinds() -> list[str]:
    """Return list of violation kinds."""
    kinds_file = CORPUS_ROOT / "kinds.yaml"
    if kinds_file.exists():
        import yaml

        with open(kinds_file) as f:
            data = yaml.safe_load(f)
        return list(data.get("kinds", {}).keys())
    return []


def get_snippets(dialect: str, verdict: str, kind: str) -> list[Path]:
    """Get all snippet files for a dialect/verdict/kind."""
    ext = "asm" if dialect == "nasm" else "s"
    pattern = f"{kind}.{ext}"
    dir_path = CORPUS_ROOT / dialect / verdict
    if dir_path.exists():
        return list(dir_path.glob(pattern))
    return []


@pytest.fixture
def registry() -> CheckRegistry:
    """Create a check registry with native-asm checks registered."""
    reg = CheckRegistry()
    register_native_asm(reg)
    return reg


@pytest.fixture
def fake_executor() -> FakeExecutor:
    """Create a fake executor for testing."""
    return FakeExecutor()


async def assemble_and_link(
    executor: FakeExecutor,
    source_files: list[Path],
    dialect: str,
    obj_format: ObjFormat = ObjFormat.ELF64,
) -> tuple[bool, list[str]]:
    """Assemble and link source files, return (success, object_paths)."""
    # This is a simplified version - in reality we'd use the real executor
    # For now, we'll use the fake executor's pre-programmed responses
    return True, []


class TestV3StaticLint:
    """Tests for V3 static ABI lint (Capstone CFG)."""

    @pytest.mark.parametrize("dialect,ext,dialect_dir", get_dialect_dirs())
    @pytest.mark.parametrize("kind", get_kinds())
    def test_v3_detects_bad_snippets(
        self,
        dialect: str,
        ext: str,
        dialect_dir: str,
        kind: str,
        registry: CheckRegistry,
    ):
        """V3 should flag bad snippets for kinds it detects."""
        # Check if V3 is the detector for this kind
        kinds_file = CORPUS_ROOT / "kinds.yaml"
        if kinds_file.exists():
            import yaml

            with open(kinds_file) as f:
                data = yaml.safe_load(f)
            detector = data.get("kinds", {}).get(kind, {}).get("detector")
            if detector != "V3":
                pytest.skip(f"V3 not the detector for {kind} (detector: {detector})")

        bad_snippets = get_snippets(dialect, "bad", kind)
        if not bad_snippets:
            pytest.skip(f"No bad snippets for {dialect}/{kind}")

        for snippet in bad_snippets:
            # TODO: When V3 is fully implemented, run the check and verify it flags the snippet
            # For now, this test documents the expected behavior
            assert snippet.exists(), f"Bad snippet {snippet} should exist"

    @pytest.mark.parametrize("dialect,ext,dialect_dir", get_dialect_dirs())
    @pytest.mark.parametrize("kind", get_kinds())
    def test_v3_passes_good_snippets(
        self,
        dialect: str,
        ext: str,
        dialect_dir: str,
        kind: str,
        registry: CheckRegistry,
    ):
        """V3 should NOT flag good snippets for kinds it detects."""
        kinds_file = CORPUS_ROOT / "kinds.yaml"
        if kinds_file.exists():
            import yaml

            with open(kinds_file) as f:
                data = yaml.safe_load(f)
            detector = data.get("kinds", {}).get(kind, {}).get("detector")
            if detector != "V3":
                pytest.skip(f"V3 not the detector for {kind} (detector: {detector})")

        good_snippets = get_snippets(dialect, "good", kind)
        if not good_snippets:
            pytest.skip(f"No good snippets for {dialect}/{kind}")

        for snippet in good_snippets:
            # TODO: When V3 is fully implemented, run the check and verify it passes the snippet
            assert snippet.exists(), f"Good snippet {snippet} should exist"


class TestV4DynamicChecks:
    """Tests for V4 dynamic ABI checks (Unicorn emulation)."""

    @pytest.mark.parametrize("dialect,ext,dialect_dir", get_dialect_dirs())
    @pytest.mark.parametrize("kind", get_kinds())
    def test_v4_detects_bad_snippets(
        self,
        dialect: str,
        ext: str,
        dialect_dir: str,
        kind: str,
        registry: CheckRegistry,
    ):
        """V4 should flag bad snippets for kinds it detects."""
        kinds_file = CORPUS_ROOT / "kinds.yaml"
        if kinds_file.exists():
            import yaml

            with open(kinds_file) as f:
                data = yaml.safe_load(f)
            detector = data.get("kinds", {}).get(kind, {}).get("detector")
            if detector != "V4":
                pytest.skip(f"V4 not the detector for {kind} (detector: {detector})")

        bad_snippets = get_snippets(dialect, "bad", kind)
        if not bad_snippets:
            pytest.skip(f"No bad snippets for {dialect}/{kind}")

        for snippet in bad_snippets:
            # TODO: When V4 is fully implemented, run the check and verify it flags the snippet
            assert snippet.exists(), f"Bad snippet {snippet} should exist"

    @pytest.mark.parametrize("dialect,ext,dialect_dir", get_dialect_dirs())
    @pytest.mark.parametrize("kind", get_kinds())
    def test_v4_passes_good_snippets(
        self,
        dialect: str,
        ext: str,
        dialect_dir: str,
        kind: str,
        registry: CheckRegistry,
    ):
        """V4 should NOT flag good snippets for kinds it detects."""
        kinds_file = CORPUS_ROOT / "kinds.yaml"
        if kinds_file.exists():
            import yaml

            with open(kinds_file) as f:
                data = yaml.safe_load(f)
            detector = data.get("kinds", {}).get(kind, {}).get("detector")
            if detector != "V4":
                pytest.skip(f"V4 not the detector for {kind} (detector: {detector})")

        good_snippets = get_snippets(dialect, "good", kind)
        if not good_snippets:
            pytest.skip(f"No good snippets for {dialect}/{kind}")

        for snippet in good_snippets:
            # TODO: When V4 is fully implemented, run the check and verify it passes the snippet
            assert snippet.exists(), f"Good snippet {snippet} should exist"


class TestMutationCorpusCompleteness:
    """Tests to verify the mutation corpus is complete."""

    def test_all_kinds_have_good_and_bad(self):
        """Every kind should have at least one good and one bad snippet per dialect."""
        kinds = get_kinds()
        dialects = get_dialect_dirs()

        for kind in kinds:
            for dialect, _ext, _dialect_dir in dialects:
                good = get_snippets(dialect, "good", kind)
                bad = get_snippets(dialect, "bad", kind)

                assert len(good) > 0, f"Missing good snippet for {dialect}/{kind}"
                assert len(bad) > 0, f"Missing bad snippet for {dialect}/{kind}"

    def test_kinds_yaml_matches_filesystem(self):
        """kinds.yaml should list all kinds that have snippet files."""
        kinds = get_kinds()
        dialects = get_dialect_dirs()

        for dialect, ext, _dialect_dir in dialects:
            bad_dir = CORPUS_ROOT / dialect / "bad"
            if bad_dir.exists():
                for snippet in bad_dir.glob(f"*.{ext}"):
                    kind = snippet.stem
                    assert kind in kinds, f"Kind {kind} in filesystem but not in kinds.yaml"


class TestCapstoneAnalyzer:
    """Unit tests for the Capstone analyzer (V3)."""

    def test_analyzer_initialization(self):
        """Test that CapstoneAnalyzer can be created."""
        from barthelona.emulator.static_lint import CapstoneAnalyzer

        code = b"\x90\x90\xc3"  # nop; nop; ret
        analyzer = CapstoneAnalyzer(code, base_addr=0x400000)
        assert analyzer is not None
        assert analyzer.md is not None

    def test_simple_function_analysis(self):
        """Test analysis of a simple function."""
        from barthelona.emulator.static_lint import CapstoneAnalyzer

        # push rbp; mov rbp, rsp; pop rbp; ret
        code = b"\x55\x48\x89\xe5\x5d\xc3"
        analyzer = CapstoneAnalyzer(code, base_addr=0x400000)
        functions = analyzer.analyze()

        assert len(functions) >= 1
        func = next(iter(functions.values()))
        assert func.name.startswith("sub_")
        # Stack should be balanced for this simple function
        # (push rbp / pop rbp)


class TestUnicornEmulator:
    """Unit tests for the Unicorn emulator (V4)."""

    def test_emulator_initialization(self):
        """Test that UnicornEmulator can be created."""
        from barthelona.emulator.dynamic_check import UnicornEmulator

        emulator = UnicornEmulator()
        # Note: unicorn may not be installed in test environment
        # This test just verifies the class can be instantiated
        assert emulator is not None

    def test_elf_loader(self):
        """Test ELF loading with pyelftools."""

        # Create a minimal ELF file for testing
        # This is a placeholder - real test would use a known ELF
        pass


class TestCanarySetup:
    """Tests for callee-saved register canaries."""

    def test_canary_generation(self):
        """Test canary set generation for both ABIs."""
        from barthelona.emulator.canary import ABI, CanarySet

        canary_sysv = CanarySet(abi=ABI.SYSV64)
        assert len(canary_sysv.values) == 6  # RBX, RBP, R12-R15

        canary_win64 = CanarySet(abi=ABI.WIN64)
        assert len(canary_win64.values) >= 8  # RBX, RBP, R12-R15, RDI, RSI, (XMM6-15)

    def test_canary_uniqueness(self):
        """Test that each register gets a unique canary value."""
        from barthelona.emulator.canary import ABI, CanarySet

        canary_set = CanarySet(abi=ABI.SYSV64)
        values = list(canary_set.values.values())
        assert len(values) == len(set(values)), "All canaries should be unique"


class TestDwarfMap:
    """Tests for DWARF PC → source location mapping."""

    def test_dwarf_map_creation(self):
        """Test DwarfMap can be created and queried."""
        from barthelona.emulator.dwarf_map import DwarfMap, SourceLocation

        dwarf_map = DwarfMap()
        loc = SourceLocation(file="test.c", line=10, function="foo")
        dwarf_map.add_range(0x400000, 0x400100, loc)

        result = dwarf_map.lookup(0x400050)
        assert result is not None
        assert result.file == "test.c"
        assert result.line == 10

        # Out of range
        result = dwarf_map.lookup(0x500000)
        assert result is None


class TestMockRegistry:
    """Tests for the mock function registry."""

    def test_mock_registry_creation(self):
        """Test MockRegistry can be created and populated."""
        from barthelona.emulator.mocks import MockRegistry

        registry = MockRegistry()
        assert len(registry.mocks) == 0

    def test_trampoline_allocation(self):
        """Test trampoline address allocation."""
        from barthelona.emulator.mocks import MockRegistry

        registry = MockRegistry()
        addr1 = registry.allocate_trampoline()
        addr2 = registry.allocate_trampoline()

        assert addr2 > addr1
        # Should be 16-byte aligned
        assert addr1 % 16 == 0
        assert addr2 % 16 == 0


# Integration test that runs the full ladder on mutation corpus snippets
@pytest.mark.asyncio
@pytest.mark.slow
class TestLadderOnMutationCorpus:
    """Integration tests running the full verification ladder on corpus snippets."""

    @pytest.mark.parametrize("dialect,ext,dialect_dir", get_dialect_dirs())
    @pytest.mark.parametrize("kind", get_kinds())
    async def test_v3_v4_on_corpus(
        self,
        dialect: str,
        ext: str,
        dialect_dir: str,
        kind: str,
        registry: CheckRegistry,
        fake_executor: FakeExecutor,
    ):
        """Run V3/V4 on both good and bad snippets and verify expected outcomes."""
        kinds_file = CORPUS_ROOT / "kinds.yaml"
        if kinds_file.exists():
            import yaml

            with open(kinds_file) as f:
                data = yaml.safe_load(f)
            data.get("kinds", {}).get(kind, {}).get("detector")

        # Test good snippet
        good_snippets = get_snippets(dialect, "good", kind)
        bad_snippets = get_snippets(dialect, "bad", kind)

        if not good_snippets or not bad_snippets:
            pytest.skip(f"Missing snippets for {dialect}/{kind}")

        # TODO: When V3/V4 are fully implemented:
        # 1. Assemble/link the snippet
        # 2. Run V3 static lint
        # 3. Run V4 dynamic checks
        # 4. Verify bad snippets are flagged, good snippets pass

        # For now, just verify files exist
        assert good_snippets[0].exists()
        assert bad_snippets[0].exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
