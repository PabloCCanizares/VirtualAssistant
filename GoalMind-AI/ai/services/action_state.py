import threading
from typing import Any, Dict, Optional

_pending_actions: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


def get_pending_action(user_id: Optional[str]) -> Optional[Dict[str, Any]]:
    if not user_id:
        return None
    with _lock:
        return _pending_actions.get(str(user_id))


def set_pending_action(user_id: Optional[str], intent: Dict[str, Any]) -> None:
    if not user_id:
        return
    with _lock:
        _pending_actions[str(user_id)] = dict(intent or {})


def clear_pending_action(user_id: Optional[str]) -> None:
    if not user_id:
        return
    with _lock:
        _pending_actions.pop(str(user_id), None)
