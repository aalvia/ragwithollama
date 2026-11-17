"""Procesamiento de PDF, Word, Excel, Markdown y fragmentos."""

from pathlib import Path

import fitz
from docx import Document
from openpyxl import Workbook

from app.services.document_service import (
    DocumentService,
    clean_text,
    extract_blocks,
    split_markdown_sections,
    split_text,
)
from app.services.indexing_service import plan_index_actions


def test_split_text_respeta_tamano_y_solape():
    text = "frase de muestra. " * 80
    pieces = split_text(text.strip(), size=200, overlap=40)
    assert len(pieces) > 1
    assert all(len(piece) <= 200 for piece in pieces)
    assert pieces[0][-30:] in (pieces[1][:80] + pieces[0][-30:])


def test_split_text_vacio_y_corto():
    assert split_text("   ", 100, 20) == []
    assert split_text("oxígeno disuelto", 100, 20) == ["oxígeno disuelto"]


def test_clean_text_quita_controles_y_lineas_vacias():
    raw = "línea uno\r\n\r\n\r\n\x00línea dos"
    assert clean_text(raw) == "línea uno\n\nlínea dos"


def test_markdown_se_parte_por_titulos(tmp_path: Path):
    path = tmp_path / "nota.md"
    path.write_text("# Oxígeno\n\nSe mide al amanecer.\n\n## Temperatura\n\nEl rango es orientativo.\n", encoding="utf-8")
    sections = split_markdown_sections(path.read_text(encoding="utf-8"))
    assert sections[0][0] == "Oxígeno"
    assert "amanecer" in sections[0][1]
    assert sections[1][0] == "Temperatura"


def test_extrae_markdown_pdf_docx_y_xlsx(tmp_path: Path):
    markdown = tmp_path / "nota.md"
    markdown.write_text("# Siembra\n\nLa densidad se expresa en animales por metro cuadrado.\n", encoding="utf-8")
    blocks = extract_blocks(markdown, ".md")
    assert "metro cuadrado" in blocks[0][2]

    pdf_path = tmp_path / "nota.pdf"
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "El oxígeno disuelto se mide al amanecer.")
    pdf.save(pdf_path)
    pdf.close()
    pdf_blocks = extract_blocks(pdf_path, ".pdf")
    assert pdf_blocks[0][1] == 1
    assert "amanecer" in pdf_blocks[0][2]

    word_path = tmp_path / "nota.docx"
    word = Document()
    word.add_paragraph("La bioseguridad limita el ingreso de patógenos.")
    word.save(word_path)
    assert "patógenos" in extract_blocks(word_path, ".docx")[0][2]

    excel_path = tmp_path / "costos.xlsx"
    book = Workbook()
    sheet = book.active
    sheet.title = "Costos"
    sheet["A1"] = "Alimento"
    sheet["B1"] = 1200
    book.save(excel_path)
    excel_text = extract_blocks(excel_path, ".xlsx")[0][2]
    assert "Alimento" in excel_text
    assert "1200" in excel_text


def test_chunks_incluyen_nombre_y_seccion(tmp_path: Path):
    documents = tmp_path / "docs"
    documents.mkdir()
    (documents / "fcr.md").write_text(
        "# Conversión\n\n" + ("El factor de conversión alimenticia relaciona alimento y biomasa. " * 40),
        encoding="utf-8",
    )
    service = DocumentService(documents, chunk_size=180, chunk_overlap=30)
    found = service.list_files()
    chunks = service.build_chunks(found[0])
    assert len(chunks) > 1
    assert chunks[0].source_name == "fcr.md"
    assert "Documento: fcr.md" in chunks[0].text
    assert "Sección: Conversión" in chunks[0].text
    assert chunks[0].page is None


def test_plan_detecta_nuevo_modificado_eliminado_e_igual():
    actions = plan_index_actions(
        {"nuevo.md": "a", "cambio.md": "b2", "igual.md": "c"},
        {"cambio.md": "b1", "igual.md": "c", "borrado.md": "d"},
    )
    assert actions["added"] == ["nuevo.md"]
    assert actions["updated"] == ["cambio.md"]
    assert actions["removed"] == ["borrado.md"]
    assert actions["unchanged"] == ["igual.md"]
