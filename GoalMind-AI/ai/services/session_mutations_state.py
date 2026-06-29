import json
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_session_mutations: Dict[str, List[Dict[str, Any]]] = {}
_lock = threading.Lock()


def get_session_mutations(user_id: Optional[str]) -> List[Dict[str, Any]]:
    if not user_id:
        return []
    with _lock:
        return list(_session_mutations.get(str(user_id), []))


def get_session_mutations_json(user_id: Optional[str]) -> str:
    mutations = get_session_mutations(user_id)
    return json.dumps(mutations, default=str)


def append_session_mutation(user_id: Optional[str], mutation: Dict[str, Any]) -> None:
    if not user_id:
        return
    record = {
        "action": mutation.get("action"),
        "type": mutation.get("type"),
        "id": str(mutation.get("id", "")),
        "name": mutation.get("name", ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if "description" in mutation:
        record["description"] = mutation.get("description", "")
    with _lock:
        key = str(user_id)
        if key not in _session_mutations:
            _session_mutations[key] = []
        _session_mutations[key].append(record)


def clear_session_mutations(user_id: Optional[str]) -> None:
    if not user_id:
        return
    with _lock:
        _session_mutations.pop(str(user_id), None)
