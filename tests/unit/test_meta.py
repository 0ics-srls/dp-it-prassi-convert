"""Metadata of a prassi PDF: sidecar of the grab first, then the file name, then the header of the act (port of the lexcrps-prassi-extract tests)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from dp_it_prassi_convert import meta

GUID = "8C708965-7201-43BE-B7BE-71FF1FED384B"
HEADER_12E = "CIRCOLARE N. 12/E\n\n_Direzione Centrale_\n\nRoma, 8 agosto 2025\n\n**OGGETTO**: Riforma Irpef"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "tipo", "numero", "anno", "data"),
    [
        ("Circolare_n_9_del_24_06_2025.pdf", "circolare", "9", 2025, "2025-06-24"),
        ("RIS_n_16_del_04_03_2025.pdf", "risoluzione", "16", 2025, "2025-03-04"),
        ("Risoluzione_n._29_2025.pdf", "risoluzione", "29", 2025, None),
        ("CIRCOLARE_TASSAZIONE_AUTO_USO_PROMISCUO_n._10_del_3_luglio_2025.pdf", "circolare", "10", 2025, None),
        ("Risoluzione 11 del 7 febbraio 2025.pdf", "risoluzione", "11", 2025, "2025-02-07"),
        ("Circolare+n.+18+del+7+agosto+2019.pdf", "circolare", "18", 2019, None),
    ],
)
def test_should_read_metadata_from_the_file_name_when_it_carries_them(name: str, tipo: str, numero: str, anno: int, data: str | None) -> None:
    got = meta.meta_from_name(name)

    assert (got.tipo, got.numero, got.anno) == (tipo, numero, anno)
    if data is not None:
        assert got.data == data


@pytest.mark.unit
def test_should_not_invent_a_year_or_a_number_from_a_compact_date_or_a_date_part() -> None:
    compact = meta.meta_from_name("RISOLUZIONE N. 69_22072019.pdf")
    assert compact.numero == "69"
    assert compact.anno != 2072
    assert compact.anno in (2019, None)
    assert meta.meta_from_name("Circolare Redditi terreni 08.08.25.pdf").numero is None


@pytest.mark.unit
def test_should_keep_the_number_when_an_underscore_follows_it() -> None:
    assert meta.meta_from_name("Circolare_20_del_4_11_2024_Eng.pdf").numero == "20"


@pytest.mark.unit
def test_should_detect_provvedimenti_by_word_or_prefix() -> None:
    assert meta.meta_from_name("Provvedimento_n_123_del_04_03_2024.pdf").tipo == "provvedimento"
    assert meta.meta_from_name("Provv cambio valute 09/02/2021.pdf").tipo == "provvedimento"
    assert meta.meta_from_name("Provvedimento del Direttore prot. 456 del 2024.pdf").tipo == "provvedimento"
    assert meta.meta_from_name("Circolare_n_9.pdf").tipo == "circolare"


@pytest.mark.unit
def test_should_read_the_header_of_the_act_when_the_name_is_silent() -> None:
    got = meta.meta_from_text(HEADER_12E)

    assert (got.numero, got.anno, got.data) == ("12/E", 2025, "2025-08-08")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("header", "anno", "data"),
    [
        ("RISOLUZIONE N. 61/E\n\nRoma, 20 0ttobre 2025\n\nOGGETTO:", 2025, None),
        ("RISOLUZIONE N. 15/E\n\nRoma, 18/03/2020\n\nOGGETTO:", 2020, "2020-03-18"),
        ("RISOLUZIONE N. 20/E\n\nRoma, 1° marzo 2021", 2021, "2021-03-01"),
        ("RISOLUZIONE\n\nRoma, 29ottobre 2019", 2019, "2019-10-29"),
    ],
)
def test_should_read_the_three_dateline_shapes(header: str, anno: int, data: str | None) -> None:
    got = meta.meta_from_text(header)

    assert got.anno == anno
    assert got.data == data


@pytest.mark.unit
def test_should_return_nothing_when_there_is_no_header() -> None:
    got = meta.meta_from_text("testo qualunque senza intestazione formale")

    assert got.numero is None
    assert got.data is None


@pytest.mark.unit
def test_should_give_the_sidecar_precedence_over_the_file_name(tmp_path: Path) -> None:
    pdf = tmp_path / "AGE.AGEDC001.REGISTRO UFFICIALE.0034958.04-02-2021-U.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    (tmp_path / (pdf.name + ".meta.json")).write_text(
        json.dumps({"tipo": "Provvedimento", "titolo": "Provvedimento del 4 febbraio 2021", "data": "2021-02-04", "numero": 34958,
                    "sourceUrl": "https://www.agenziaentrate.gov.it/portale/documents/x.pdf", "struttura": "Direttore", "fonte": "ade-portale",
                    "sourceId": "AGE.AGEDC001.REGISTRO UFFICIALE.0034958.04-02-2021-U", "ente": "Agenzia delle Entrate"}),
        encoding="utf-8",
    )

    got = meta.meta_from_sidecar(pdf)

    assert got is not None
    assert (got.tipo, got.numero, got.anno, got.data) == ("provvedimento", "34958", 2021, "2021-02-04")
    assert got.titolo == "Provvedimento del 4 febbraio 2021"
    assert got.source_url == "https://www.agenziaentrate.gov.it/portale/documents/x.pdf"
    assert got.source_id == "AGE.AGEDC001.REGISTRO UFFICIALE.0034958.04-02-2021-U"


@pytest.mark.unit
def test_should_fall_back_when_the_sidecar_is_missing_or_broken(tmp_path: Path) -> None:
    pdf = tmp_path / "Circolare_n_12_del_08_08_2025.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    assert meta.meta_from_sidecar(pdf) is None

    (tmp_path / (pdf.name + ".meta.json")).write_text("{not json", encoding="utf-8")
    assert meta.meta_from_sidecar(pdf) is None

    resolved = meta.resolve(pdf, "")
    assert (resolved.tipo, resolved.numero, resolved.anno) == ("circolare", "12", 2025)
    assert resolved.source_id == "Circolare_n_12_del_08_08_2025"


@pytest.mark.unit
def test_should_fill_gaps_from_the_header_and_keep_the_pdf_stem_as_identity(tmp_path: Path) -> None:
    pdf = tmp_path / "Risoluzione_n._29_2025.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    resolved = meta.resolve(pdf, "RISOLUZIONE N. 29/E\n\nRoma, 11 aprile 2025\n\nOGGETTO: x")

    assert resolved.tipo == "risoluzione"
    assert resolved.numero == "29"
    assert resolved.data == "2025-04-11"
    assert resolved.source_id == "Risoluzione_n._29_2025"


@pytest.mark.unit
def test_should_parse_the_doctrib_file_name_including_nd() -> None:
    got = meta.meta_doctrib(f"Interpello_2024-12-23_269__{GUID}.pdf")
    assert (got.tipo, got.numero, got.anno, got.data, got.source_id) == ("interpello", "269", 2024, "2024-12-23", GUID)

    nd = meta.meta_doctrib(f"Nota_2020-03-05_nd__{GUID}.pdf")
    assert (nd.tipo, nd.numero, nd.anno, nd.source_id) == ("nota", None, 2020, GUID)

    with pytest.raises(ValueError, match="doctrib"):
        meta.meta_doctrib("Interpello_2024_269.pdf")


@pytest.mark.unit
def test_should_prefer_the_doctrib_sidecar_identity_and_lower_case_the_tipo(tmp_path: Path) -> None:
    pdf = tmp_path / f"Interpello_2025-10-28_274__{GUID}.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    (tmp_path / (pdf.name + ".meta.json")).write_text(
        json.dumps({"kind": "doctrib", "tipo": "Interpello", "titolo": "Interpello del 28/10/2025 n. 274", "numero": "274", "data": "2025-10-28",
                    "struttura": "Direzione Centrale Persone Fisiche", "ente": "Agenzia delle Entrate",
                    "sourceUrl": "https://def.finanze.it/DocTribFrontend/getPrassiDetail.do?id={ABC}", "fonte": "doctrib", "sourceId": GUID}),
        encoding="utf-8",
    )

    resolved = meta.resolve(pdf, "testo senza intestazione")

    assert resolved.tipo == "interpello"
    assert (resolved.numero, resolved.anno, resolved.data) == ("274", 2025, "2025-10-28")
    assert resolved.source_id == GUID
    assert resolved.fonte == "doctrib"
    assert resolved.struttura == "Direzione Centrale Persone Fisiche"
    assert resolved.oggetto == "Interpello del 28/10/2025 n. 274"


@pytest.mark.unit
def test_should_take_the_doctrib_identity_from_the_file_name_when_there_is_no_sidecar(tmp_path: Path) -> None:
    pdf = tmp_path / f"Interpello_2024-12-23_269__{GUID}.pdf"
    pdf.write_bytes(b"%PDF-1.4")

    resolved = meta.resolve(pdf, "testo", fonte="doctrib")

    assert (resolved.tipo, resolved.numero, resolved.anno, resolved.source_id) == ("interpello", "269", 2024, GUID)


@pytest.mark.unit
def test_should_extract_the_subject_from_the_oggetto_line_else_the_first_line() -> None:
    assert meta.oggetto("CIRCOLARE N. 12/E\n\n**OGGETTO**: Riforma Irpef - novita\n\ntesto") == "Riforma Irpef - novita"
    assert meta.oggetto("\n\n# Primo rigo del documento\naltro") == "Primo rigo del documento"
    assert len(meta.oggetto("OGGETTO: " + "x" * 800)) == 500
    assert meta.oggetto("") == ""


@pytest.mark.unit
@pytest.mark.parametrize("name", ["Circolare_n_9.pdf", "Provv_x.pdf", "xyz.pdf", "RIS_n_1.pdf"])
def test_should_always_return_a_lower_case_tipo(name: str) -> None:
    tipo = meta.meta_from_name(name).tipo
    assert tipo == tipo.lower()
