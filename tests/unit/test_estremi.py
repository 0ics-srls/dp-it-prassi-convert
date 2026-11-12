"""The act is the oracle of its own number and year (port of the branch-53 EstremiDichiaratiTests / PrassiBulkService.ConEstremiDellAtto)."""
from __future__ import annotations

import re
from datetime import date

import pytest

from dp_it_prassi_convert import estremi
from dp_it_prassi_convert.estremi import EstremiAtto, Registrato


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "numero", "anno"),
    [
        ("# **Risposta n. 118/2022** blah", 118, 2022),
        ("Risposta n. 338 / 2020 con spazi", 338, 2020),
        ("CIRCOLARE N. 3/E Roma, 8 febbraio 2023 OGGETTO: ...", 3, None),
        ("# Prot. n. 120706/2023 **_Approvazione del modello", 120706, 2023),
        ("Prot. n. 120760/2023 **_Modalita di versamento", 120760, 2023),
        ("# **Interpello n. 3** **_OGGETTO: ...", 3, None),
    ],
)
def test_should_read_the_declared_estremi_when_the_act_states_them(text: str, numero: int, anno: int | None) -> None:
    declared = estremi.leggi(text)

    assert declared == EstremiAtto(numero=numero, anno=anno)


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "Divisione Contribuenti - Direzione Centrale Piccole e medie imprese",
        "",
        "Provvedimento del Direttore senza numero in testa",
        # the trap: the number after the formula is the LAW cited in the subject, not the act
        "OGGETTO: Interpello articolo 11, comma 2, legge 27 luglio 2000, n. 212 - disapplicazione",
    ],
)
def test_should_abstain_when_the_act_declares_nothing(text: str) -> None:
    assert estremi.leggi(text) is None
    assert estremi.leggi(None) is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "expected"),
    [("# **Risposta n. 118/2022**", True), ("CIRCOLARE N. 3/E Roma", True), ("Divisione Contribuenti", False)],
)
def test_should_use_one_pattern_for_ingest_and_the_sql_control(text: str, expected: bool) -> None:
    by_sql_pattern = re.search(estremi.PATTERN_SQL, text, re.IGNORECASE) is not None

    assert by_sql_pattern is expected
    assert (estremi.leggi(text) is not None) is by_sql_pattern


@pytest.mark.unit
def test_should_derive_the_year_from_the_date_when_the_name_year_contradicts_it() -> None:
    # file "Circolare 10bis art 119 dl 34 2020" is the circolare 3/E of 8 February 2023
    assert estremi.anno_coerente(date(2023, 2, 8), 2020) == 2023
    assert estremi.anno_coerente(date(2020, 2, 21), 2020) == 2020
    assert estremi.anno_coerente(None, 2021) == 2021


@pytest.mark.unit
def test_should_let_the_date_win_over_the_year_declared_next_to_the_number() -> None:
    # interpello of 18/06/2021 headed "Risposta n. 417/2020": the Agency's typo, the date wins
    assert estremi.anno_dell_atto(EstremiAtto(417, 2020), date(2021, 6, 18), 2021) == 2021
    assert estremi.anno_dell_atto(EstremiAtto(417, 2020), None, 1999) == 2020
    assert estremi.anno_dell_atto(None, None, 2021) == 2021
    assert estremi.anno_dell_atto(None, date(2025, 9, 19), 2019) == 2025


@pytest.mark.unit
def test_should_correct_number_and_year_from_the_act_when_it_declares_them() -> None:
    registered = Registrato(numero="212", anno=2020, data=date(2023, 2, 8), text_raw="CIRCOLARE N. 3/E Roma, 8 febbraio 2023 OGGETTO: x")

    corrected = estremi.con_estremi_dell_atto(registered)

    assert (corrected.numero, corrected.anno) == ("3", 2023)


@pytest.mark.unit
def test_should_keep_the_number_but_still_derive_the_year_when_nothing_is_declared() -> None:
    registered = Registrato(numero=None, anno=2019, data=date(2025, 9, 19), text_raw="Provvedimento del Direttore - ravvedimento CPB 2019-2023")

    corrected = estremi.con_estremi_dell_atto(registered)

    assert (corrected.numero, corrected.anno) == (None, 2025)


@pytest.mark.unit
def test_should_give_two_provvedimenti_of_the_same_day_their_own_protocols() -> None:
    first = estremi.con_estremi_dell_atto(Registrato(numero="05", anno=2023, data=date(2023, 4, 5), text_raw="# Prot. n. 120706/2023 Approvazione"))
    second = estremi.con_estremi_dell_atto(Registrato(numero="05", anno=2023, data=date(2023, 4, 5), text_raw="Prot. n. 120760/2023 Modalita"))

    assert (first.numero, second.numero) == ("120706", "120760")
