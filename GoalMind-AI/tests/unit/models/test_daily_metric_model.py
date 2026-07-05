from model.daily_metric_model import DailyMetricModel
import pytest

pytestmark = pytest.mark.usefixtures("mongo_mock")


USER_ID = "66ffbbbbbbbbbbbbbbbb0100"


class TestDailyMetricModel:
    def test_upsert_sleep_creates_metric(self, mongo_mock):
        metric = DailyMetricModel.upsert_sleep("2026-07-02", 7.5, usuario_id=USER_ID)

        assert metric["date"] == "2026-07-02"
        assert metric["sleep_hours"] == 7.5
        assert metric["sleep_source"] == "manual"
        assert mongo_mock.local_db["DailyMetrics"].count_documents({}) == 1

    def test_upsert_sleep_updates_same_day(self, mongo_mock):
        first = DailyMetricModel.upsert_sleep("2026-07-02", 7, usuario_id=USER_ID)
        second = DailyMetricModel.upsert_sleep("2026-07-02", 8, usuario_id=USER_ID)

        assert first["_id"] == second["_id"]
        assert second["sleep_hours"] == 8
        assert mongo_mock.local_db["DailyMetrics"].count_documents({}) == 1

    def test_upsert_mood_updates_same_day(self, mongo_mock):
        DailyMetricModel.upsert_sleep("2026-07-02", 7, usuario_id=USER_ID)
        metric = DailyMetricModel.upsert_mood("2026-07-02", 4, usuario_id=USER_ID)

        assert metric["sleep_hours"] == 7
        assert metric["mood_score"] == 4
        assert metric["mood_label"] == "bueno"
        assert metric["mood_source"] == "manual"
        assert mongo_mock.local_db["DailyMetrics"].count_documents({}) == 1

    def test_upsert_weather_updates_same_day(self, mongo_mock):
        DailyMetricModel.upsert_sleep("2026-07-02", 7, usuario_id=USER_ID)
        metric = DailyMetricModel.upsert_weather(
            "2026-07-02",
            {
                "weather_code": 61,
                "temperature_2m_mean": 22.4,
                "temperature_2m_max": 28.0,
                "temperature_2m_min": 17.0,
                "precipitation_sum": 3.2,
                "weather_kind": "observed",
                "weather_location_name": "Madrid",
            },
            usuario_id=USER_ID,
        )

        assert metric["sleep_hours"] == 7
        assert metric["weather_code"] == 61
        assert metric["weather_label"] == "lluvia_suave"
        assert metric["weather_temp_mean_c"] == 22.4
        assert metric["weather_temp_max_c"] == 28.0
        assert metric["weather_temp_min_c"] == 17.0
        assert metric["weather_precipitation_mm"] == 3.2
        assert metric["weather_location_name"] == "Madrid"
        assert mongo_mock.local_db["DailyMetrics"].count_documents({}) == 1

    def test_get_range_returns_matching_days(self, mongo_mock):
        DailyMetricModel.upsert_sleep("2026-07-01", 6, usuario_id=USER_ID)
        DailyMetricModel.upsert_sleep("2026-07-03", 8, usuario_id=USER_ID)
        DailyMetricModel.upsert_sleep("2026-07-08", 7, usuario_id=USER_ID)

        metrics = DailyMetricModel.get_range("2026-07-01", "2026-07-07", usuario_id=USER_ID)

        assert [metric["date"] for metric in metrics] == ["2026-07-01", "2026-07-03"]

    def test_invalid_sleep_hours_raise(self, mongo_mock):
        try:
            DailyMetricModel.upsert_sleep("2026-07-02", 25, usuario_id=USER_ID)
        except ValueError as exc:
            assert "0 y 24" in str(exc)
        else:
            raise AssertionError("Expected ValueError")

    def test_invalid_mood_raises(self, mongo_mock):
        with pytest.raises(ValueError, match="1 y 5"):
            DailyMetricModel.upsert_mood("2026-07-02", 6, usuario_id=USER_ID)
