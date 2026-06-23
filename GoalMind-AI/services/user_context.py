from dataclasses import dataclass

from database.mongo_conn import get_app_user_id


@dataclass(frozen=True)
class UserContext:
    user_id: str


def current_user_id() -> str:
    """Return the active app user at call time.

    The app is still single-user locally, but resolving this lazily lets config
    changes update the active user without restarting imported controllers.
    """
    return str(get_app_user_id())


def current_user_context() -> UserContext:
    return UserContext(user_id=current_user_id())
