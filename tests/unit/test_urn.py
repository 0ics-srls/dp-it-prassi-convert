"""URN:NIR mappers (ports of NormaUrnMapper and FiscalNormaRefMapper) against the golden file shared with dp-it-giurisprudenza-convert."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dp_it_prassi_convert import urn

GOLDEN = json.loads((Path(__file__).resolve().parent.parent / "fixtures" / "urn-golden.json").read_text(encoding="utf-8"))


@pytest.mark.unit
@pytest.mark.parametrize("case", GOLDEN["norma"], ids=[c["name"] for c in GOLDEN["norma"]])
def test_should_map_a_norma_like_the_legacy_norma_urn_mapper(case: dict[str, Any]) -> None:
    assert urn.try_map_urn(case["descrizione"], case["data"], case["numero"], case["articolo"]) == case["expected"]


@pytest.mark.unit
@pytest.mark.parametrize("case", GOLDEN["fiscal"], ids=[c["name"] for c in GOLDEN["fiscal"]])
def test_should_map_a_fiscal_reference_like_the_legacy_fiscal_mapper(case: dict[str, Any]) -> None:
    assert urn.try_map_fiscal(case["descrizione"], case["articolo"]) == case["expected"]


@pytest.mark.unit
def test_should_expose_the_known_acts_by_number_and_year_and_by_alias() -> None:
    assert urn.fiscal_act_by_number("d.p.r.", "633", 1972) == "urn:nir:stato:decreto.del.presidente.della.repubblica:1972-10-26;633"
    assert urn.fiscal_act_by_number("legge", "212", 2000) == "urn:nir:stato:legge:2000-07-27;212"
    # a number of the same year that belongs to another kind of act is not the fiscal act
    assert urn.fiscal_act_by_number("legge", "633", 1972) is None
    assert urn.fiscal_act_by_number("d.p.r.", "999", 1972) is None
