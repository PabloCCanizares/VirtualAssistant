from services.user_context import current_user_context, current_user_id


def test_current_user_id_tracks_app_user_nickname(monkeypatch):
    monkeypatch.setenv("APP_USER_NICKNAME", "alice")
    first = current_user_id()

    monkeypatch.setenv("APP_USER_NICKNAME", "bob")
    second = current_user_id()

    assert first != second
    assert len(first) == 24
    assert len(second) == 24


def test_current_user_context_wraps_current_id(monkeypatch):
    monkeypatch.setenv("APP_USER_NICKNAME", "alice")
    context = current_user_context()

    assert context.user_id == current_user_id()
