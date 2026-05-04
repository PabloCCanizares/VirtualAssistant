"""Tests para los helpers puros de controllers.calendar_controller."""

from __future__ import annotations

from datetime import datetime, timezone

from controllers import calendar_controller as cc


class TestParseIso:
    def test_returns_none_for_falsy(self):
        assert cc._parse_iso(None) is None
        assert cc._parse_iso("") is None

    def test_parses_zulu_timestamp(self):
        dt = cc._parse_iso("2024-05-04T15:30:00Z")
        assert dt == datetime(2024, 5, 4, 15, 30, tzinfo=timezone.utc)

    def test_parses_with_offset(self):
        dt = cc._parse_iso("2024-05-04T17:30:00+02:00")
        assert dt == datetime(2024, 5, 4, 15, 30, tzinfo=timezone.utc)

    def test_naive_string_treated_as_utc(self):
        dt = cc._parse_iso("2024-05-04T10:00:00")
        assert dt.tzinfo == timezone.utc
        assert dt.hour == 10

    def test_invalid_returns_none(self):
        assert cc._parse_iso("not a date") is None
        assert cc._parse_iso("2024-13-40") is None


class TestIsoUtc:
    def test_returns_none_for_non_datetime(self):
        assert cc._iso_utc(None) is None
        assert cc._iso_utc("string") is None  # type: ignore[arg-type]

    def test_serializes_aware_datetime_in_utc(self):
        dt = datetime(2024, 5, 4, 10, 0, tzinfo=timezone.utc)
        assert cc._iso_utc(dt) == "2024-05-04T10:00:00+00:00"

    def test_naive_datetime_treated_as_utc(self):
        dt = datetime(2024, 5, 4, 10, 0)
        assert cc._iso_utc(dt) == "2024-05-04T10:00:00+00:00"

    def test_offset_normalized_to_utc(self):
        from datetime import timedelta
        dt = datetime(2024, 5, 4, 12, 0, tzinfo=timezone(timedelta(hours=2)))
        assert cc._iso_utc(dt) == "2024-05-04T10:00:00+00:00"


class TestValidateRequired:
    def test_no_missing_returns_none(self):
        payload = {"a": "x", "b": 1}
        assert cc._validate_required(payload, ["a", "b"]) is None

    def test_lists_missing_fields_in_message(self):
        msg = cc._validate_required({"a": "x"}, ["a", "b", "c"])
        assert msg is not None
        assert "b" in msg and "c" in msg
        assert "Faltan campos" in msg

    def test_treats_empty_string_and_list_as_missing(self):
        msg = cc._validate_required({"a": "", "b": [], "c": None, "d": "ok"}, ["a", "b", "c", "d"])
        assert "a" in msg and "b" in msg and "c" in msg
        assert "d" not in msg
