"""LLM client interface and provider implementations."""

import json
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from llm_config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    GEMINI_TIMEOUT_SECONDS,
    GEMINI_USE_GOOGLE_SEARCH,
    LLM_PROVIDER,
    OLLAMA_HOST,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT_SECONDS,
)


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
        self.host = (host or OLLAMA_HOST).rstrip("/")
        self.model = model or OLLAMA_MODEL
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


class GeminiError(LLMError):
    """Raised when Gemini cannot provide a usable response."""


class GeminiListener:
    """Use Gemini with its managed Google Search grounding tool when enabled."""

    def __init__(
        self,
        api_key=None,
        model=None,
        timeout=None,
        enable_google_search=None,
        client=None,
    ):
        self.api_key = api_key if api_key is not None else GEMINI_API_KEY
        self.model = model or GEMINI_MODEL
        self.timeout = GEMINI_TIMEOUT_SECONDS if timeout is None else timeout
        self.enable_google_search = (
            GEMINI_USE_GOOGLE_SEARCH if enable_google_search is None else enable_google_search
        )
        self._client = client

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not self.api_key:
            raise GeminiError(
                "Gemini requires GEMINI_API_KEY. Set it in your environment before "
                "choosing the gemini provider."
            )
        try:
            from google import genai
        except ImportError as error:
            raise GeminiError(
                "Gemini support needs the google-genai package. Run: pip install -r requirements.txt"
            ) from error
        self._client = genai.Client(
            api_key=self.api_key,
            http_options={"timeout": self.timeout * 1000},
        )
        return self._client

    @staticmethod
    def _conversation_input(prompt, system_prompt, history):
        sections = []
        if isinstance(system_prompt, str) and system_prompt.strip():
            sections.append(f"System instructions:\n{system_prompt.strip()}")
        history_lines = []
        for message in history or []:
            if not isinstance(message, dict):
                continue
            role = message.get("role")
            content = message.get("content")
            if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
                speaker = "Learner" if role == "user" else "Assistant"
                history_lines.append(f"{speaker}: {content.strip()}")
        if history_lines:
            sections.append("Conversation history:\n" + "\n".join(history_lines))
        sections.append(f"Current task:\n{prompt}")
        return "\n\n".join(sections)

    @staticmethod
    def _field(value, name, default=None):
        if isinstance(value, dict):
            return value.get(name, default)
        return getattr(value, name, default)

    @classmethod
    def _response_text(cls, result):
        direct_text = cls._field(result, "output_text")
        if isinstance(direct_text, str) and direct_text.strip():
            return direct_text.strip()

        fragments = []
        for output in cls._field(result, "output", []) or []:
            for content in cls._field(output, "content", []) or []:
                text = cls._field(content, "text")
                if isinstance(text, str) and text.strip():
                    fragments.append(text.strip())
        if fragments:
            return "\n".join(fragments)
        raise GeminiError("Gemini returned an empty response.")

    def chat(self, prompt, system_prompt=None, history=None):
        tools = [{"type": "google_search"}] if self.enable_google_search else None
        request = {
            "model": self.model,
            "input": self._conversation_input(prompt, system_prompt, history),
            # The application expects a JSON response from every provider.
            "response_format": {"type": "text", "mime_type": "application/json"},
        }
        if tools:
            request["tools"] = tools

        try:
            result = self._get_client().interactions.create(**request)
        except GeminiError:
            raise
        except Exception as error:
            raise GeminiError(f"Gemini could not complete the request: {error}") from error
        return self._response_text(result)


def create_llm_client(provider=None):
    """Create the configured provider without exposing it to backend features."""

    selected_provider = (provider or LLM_PROVIDER).strip().casefold()
    if selected_provider == "ollama":
        return OllamaListener(
            host=OLLAMA_HOST,
            model=OLLAMA_MODEL,
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
    if selected_provider == "gemini":
        return GeminiListener(
            api_key=GEMINI_API_KEY,
            model=GEMINI_MODEL,
            timeout=GEMINI_TIMEOUT_SECONDS,
            enable_google_search=GEMINI_USE_GOOGLE_SEARCH,
        )
    raise LLMError("EDUCATOR_LLM_PROVIDER must be either 'ollama' or 'gemini'.")
