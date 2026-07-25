"""LLM client interface and the default local Ollama implementation."""

import json
import os
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class LLMError(RuntimeError):
    """Raised when the configured language-model provider cannot respond."""


class LLMClient(Protocol):
    """Minimal interface required by the learning and notes backend."""

    def chat(self, prompt, system_prompt=None, history=None):
        """Return a text response for the supplied conversation."""


class OllamaError(LLMError):
    """Raised when Ollama cannot provide a usable response."""


class OllamaListener:
    """Send non-streaming prompts to the local Ollama chat API."""

    def __init__(self, host=None, model=None, timeout=60):
        self.host = (host or os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")).rstrip("/")
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3.2:latest")
        self.timeout = timeout

    def chat(self, prompt, system_prompt=None, history=None):
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        for message in history or []:
            if (
                isinstance(message, dict)
                and message.get("role") in {"user", "assistant"}
                and isinstance(message.get("content"), str)
                and message["content"].strip()
            ):
                messages.append({"role": message["role"], "content": message["content"].strip()})
        messages.append({"role": "user", "content": prompt})
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "stream": False,
            "format": "json",
        }).encode("utf-8")
        request = Request(
            f"{self.host}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise OllamaError(f"Could not reach Ollama at {self.host}: {error}") from error

        content = result.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise OllamaError("Ollama returned an empty response.")
        return content.strip()
