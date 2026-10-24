from barthelona.domain.enums import Dialect
from barthelona.domain.presets import builtin_presets


def test_builtin_presets_cover_nasm_and_both_gas_syntaxes() -> None:
    presets = builtin_presets()
    assert [p.dialect for p in presets] == [Dialect.NASM, Dialect.GAS_INTEL, Dialect.GAS_ATT]
    assert len({p.preset for p in presets}) == 3
