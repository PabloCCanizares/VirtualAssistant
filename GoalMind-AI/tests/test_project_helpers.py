"""Tests para los helpers puros de controllers.project_controller."""

from __future__ import annotations

from bson import ObjectId

from controllers import project_controller as pc


class TestSerializeId:
    def test_returns_none_for_none(self):
        assert pc._serialize_id(None) is None

    def test_stringifies_objectid(self):
        oid = ObjectId()
        assert pc._serialize_id(oid) == str(oid)


class TestSerializeProject:
    def test_converts_id_and_categorias(self):
        oid = ObjectId()
        cat1, cat2 = ObjectId(), ObjectId()
        proj = {"_id": oid, "titulo": "P", "categorias": [cat1, cat2]}
        out = pc._serialize_project(proj)
        assert out["_id"] == str(oid)
        assert out["categorias"] == [str(cat1), str(cat2)]

    def test_handles_missing_categorias(self):
        out = pc._serialize_project({"_id": ObjectId(), "titulo": "P"})
        assert "categorias" not in out or out.get("categorias") in (None, [])


class TestSerializeGoal:
    def test_converts_id_and_project_id(self):
        gid, pid = ObjectId(), ObjectId()
        out = pc._serialize_goal({"_id": gid, "project_id": pid, "titulo": "G"})
        assert out["_id"] == str(gid)
        assert out["project_id"] == str(pid)


class TestSerializeDocument:
    def test_converts_doc_ids(self):
        did, pid, gid, fid = ObjectId(), ObjectId(), ObjectId(), ObjectId()
        doc = {"_id": did, "project_id": pid, "goal_id": gid, "folder_id": fid, "filename": "x.pdf"}
        out = pc._serialize_document(doc)
        assert out["_id"] == str(did)
        assert out["project_id"] == str(pid)
        assert out["goal_id"] == str(gid)
        assert out["folder_id"] == str(fid)


class TestSerializeFolder:
    def test_converts_folder_ids(self):
        fid, pid = ObjectId(), ObjectId()
        out = pc._serialize_folder({"_id": fid, "project_id": pid, "name": "Docs"})
        assert out["_id"] == str(fid)
        assert out["project_id"] == str(pid)


class TestFormatSize:
    def test_zero_bytes(self):
        assert pc._format_size(None) == "0 B"

    def test_bytes_displayed_as_int(self):
        assert pc._format_size(500) == "500 B"

    def test_kilobytes(self):
        assert pc._format_size(2048) == "2.0 KB"

    def test_megabytes(self):
        assert pc._format_size(5 * 1024 * 1024) == "5.0 MB"

    def test_gigabytes(self):
        assert pc._format_size(3 * 1024**3) == "3.0 GB"


class TestParseImportance:
    def test_default_when_none_or_empty(self):
        assert pc._parse_importance(None, default=5) == 5
        assert pc._parse_importance("", default=5) == 5

    def test_clamps_above_ten(self):
        assert pc._parse_importance(99) == 10

    def test_clamps_below_zero(self):
        assert pc._parse_importance(-5) == 0

    def test_parses_valid_int(self):
        assert pc._parse_importance(7) == 7

    def test_parses_string_int(self):
        assert pc._parse_importance("3") == 3

    def test_invalid_returns_default(self):
        assert pc._parse_importance("muy importante", default=4) == 4


class TestImportanceValue:
    def test_default_zero_for_missing(self):
        assert pc._importance_value({}) == 0

    def test_returns_clamped_value(self):
        assert pc._importance_value({"importancia": 99}) == 10
        assert pc._importance_value({"importancia": -1}) == 0


class TestDetectPreviewMode:
    def test_pdf_via_mimetype(self):
        assert pc._detect_preview_mode({"original_name": "x"}, "application/pdf") == "pdf"

    def test_pdf_via_extension(self):
        assert pc._detect_preview_mode({"filename": "doc.pdf"}, "application/octet-stream") == "pdf"

    def test_image_mimetype(self):
        assert pc._detect_preview_mode({"filename": "x"}, "image/png") == "image"
        assert pc._detect_preview_mode({"filename": "x"}, "image/jpeg") == "image"

    def test_text_mimetype(self):
        assert pc._detect_preview_mode({"filename": "x"}, "text/plain") == "text"

    def test_text_extensions(self):
        for filename in ("a.txt", "a.md", "a.csv", "a.json", "a.log"):
            assert pc._detect_preview_mode({"filename": filename}, "application/octet-stream") == "text"

    def test_unsupported(self):
        assert (
            pc._detect_preview_mode({"filename": "x.zip"}, "application/zip") == "unsupported"
        )


class TestResolveDocumentMimetype:
    def test_uses_explicit_content_type(self):
        assert pc._resolve_document_mimetype({"content_type": "image/png", "filename": "x"}) == "image/png"

    def test_falls_back_to_guess_for_octet_stream(self):
        out = pc._resolve_document_mimetype(
            {"content_type": "application/octet-stream", "original_name": "doc.pdf"}
        )
        assert out == "application/pdf"

    def test_returns_octet_stream_when_unknown(self):
        out = pc._resolve_document_mimetype({"content_type": "", "filename": "weird"})
        assert out == "application/octet-stream"


class TestDocumentName:
    def test_prefers_original_name(self):
        assert pc._document_name({"original_name": "a.pdf", "filename": "b.pdf"}) == "a.pdf"

    def test_falls_back_to_filename(self):
        assert pc._document_name({"filename": "b.pdf"}) == "b.pdf"

    def test_default_when_missing(self):
        assert pc._document_name({}) == "documento"


class TestStreamSize:
    def test_returns_zero_when_stream_unsupported(self):
        class Bad:
            def tell(self):
                raise OSError

            def seek(self, *args, **kw):
                raise OSError

        assert pc._stream_size(Bad()) == 0

    def test_measures_bytesio(self):
        from io import BytesIO

        bio = BytesIO(b"abc123")
        assert pc._stream_size(bio) == 6
