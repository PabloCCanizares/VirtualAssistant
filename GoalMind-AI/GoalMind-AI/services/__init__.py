from typing import Any


def run_chat(*args: Any, **kwargs: Any):
    from .chat_service import run_chat as _run_chat

    return _run_chat(*args, **kwargs)


__all__ = ["run_chat"]
