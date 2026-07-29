"""Process-safe JSONL logging for language-model requests and responses."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from config.app import PROJECT_PATH

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None


_THREAD_LOCK = Lock()


def _enabled():
    return os.getenv("LLM_LOG_ENABLED", "true").strip().casefold() in {
        "1", "true", "yes", "on",
    }


def _log_path():
    configured = os.getenv("LLM_LOG_PATH", "logs/llm_io.jsonl").strip()
    path = Path(configured).expanduser()
    return path if path.is_absolute() else PROJECT_PATH / path


def write_llm_log(event):
    """Append one complete request event without allowing logging to break the app."""

    if not _enabled():
        return
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
        **event,
    }
    try:
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        with _THREAD_LOCK, path.open("a", encoding="utf-8") as stream:
            if fcntl is not None:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                stream.write(line)
                stream.flush()
            finally:
                if fcntl is not None:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


class LoggedLLMClient:
    """Provider-neutral decorator that records complete model I/O."""

    def __init__(self, client):
        self.client = client

    def __getattr__(self, name):
        return getattr(self.client, name)

    def chat(
        self,
        prompt,
        system_prompt=None,
        history=None,
        max_output_tokens=None,
        use_grounding=None,
    ):
        from time import perf_counter
        from uuid import uuid4

        request_id = uuid4().hex
        provider = type(self.client).__name__
        model = getattr(self.client, "model", None)
        started_at = perf_counter()
        request = {
            "request_id": request_id,
            "event": "llm_request",
            "provider": provider,
            "model": model,
            "system_prompt": system_prompt,
            "prompt": prompt,
            "history": history or [],
            "max_output_tokens": max_output_tokens,
            "use_grounding": use_grounding,
        }
        write_llm_log(request)
        try:
            response = self.client.chat(
                prompt,
                system_prompt=system_prompt,
                history=history,
                max_output_tokens=max_output_tokens,
                use_grounding=use_grounding,
            )
        except Exception as error:
            write_llm_log({
                "request_id": request_id,
                "event": "llm_error",
                "provider": provider,
                "model": model,
                "elapsed_seconds": perf_counter() - started_at,
                "error_type": type(error).__name__,
                "error": str(error),
            })
            raise
        write_llm_log({
            "request_id": request_id,
            "event": "llm_response",
            "provider": provider,
            "model": model,
            "elapsed_seconds": perf_counter() - started_at,
            "response": response,
            "response_metadata": getattr(
                self.client, "last_response_metadata", None
            ),
        })
        return response
