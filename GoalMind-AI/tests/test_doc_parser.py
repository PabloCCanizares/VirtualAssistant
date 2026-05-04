"""Tests para ai.services.doc_parser: extraccion textual segun tipo de fichero."""

from __future__ import annotations

from ai.services.doc_parser import extract_text


class TestExtractTextDispatch:
    def test_txt_decoded_directly(self):
        out = extract_text(b"hola mundo", content_type="text/plain", filename="nota.txt")
        assert out == "hola mundo"

    def test_md_extension_decoded(self):
        out = extract_text(b"# titulo", content_type="", filename="readme.md")
        assert out == "# titulo"

    def test_json_extension_decoded(self):
        out = extract_text(b'{"a":1}', content_type="", filename="data.json")
        assert out == '{"a":1}'

    def test_log_extension_decoded(self):
        out = extract_text(b"line", content_type="", filename="server.log")
        assert out == "line"

    def test_text_content_type_decoded_even_without_extension(self):
        out = extract_text(b"sin extension", content_type="text/plain", filename="raw")
        assert out == "sin extension"

    def test_image_returns_placeholder(self):
        out = extract_text(b"\x89PNG", content_type="image/png", filename="logo.png")
        assert "imagen" in out.lower()

    def test_unsupported_format_message(self):
        out = extract_text(b"...", content_type="application/zip", filename="paquete.zip")
        assert "Formato no soportado" in out

    def test_unicode_chars_replaced_on_bad_bytes(self):
        out = extract_text(b"\xff\xfe", content_type="text/plain", filename="x.txt")
        assert isinstance(out, str)


class TestExtractCsv:
    def test_csv_renders_markdown_table(self):
        raw = b"name,age\nAna,30\nBob,40\n"
        out = extract_text(raw, content_type="text/csv", filename="people.csv")
        assert "| name | age |" in out
        assert "| Ana | 30 |" in out
        assert "| --- | --- |" in out

    def test_empty_csv_message(self):
        out = extract_text(b"", content_type="text/csv", filename="empty.csv")
        # csv.reader sobre cadena vacia produce 0 filas
        assert "vacio" in out.lower() or out == ""


class TestExtensionDetection:
    def test_uppercase_extension_works(self):
        out = extract_text(b"hello", content_type="", filename="DOC.TXT")
        assert out == "hello"

    def test_no_extension_with_unknown_type(self):
        out = extract_text(b"...", content_type="", filename="archivo")
        assert "Formato no soportado" in out
