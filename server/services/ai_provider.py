"""AI provider abstraction — Protocol + OllamaProvider stub."""

import json
import httpx
from typing import Protocol, runtime_checkable

_TIMEOUT = 300.0


@runtime_checkable
class AIProvider(Protocol):
    """Protocol for AI provider implementations.

    All AI access goes through this abstraction so providers are swappable.
    """

    async def generate(self, prompt: str, *, system: str = "", temperature: float = 0.7) -> str:
        """Generate a text completion."""
        ...

    async def generate_json(self, prompt: str, *, system: str = "", temperature: float = 0.3) -> dict:
        """Generate a structured JSON response."""
        ...

    async def generate_with_history(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        json_mode: bool = False,
    ) -> str:
        """Generate a response continuing a multi-turn conversation."""
        ...


class OllamaProvider:
    """Ollama-based AI provider (local inference)."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "mistral-nemo") -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def generate(self, prompt: str, *, system: str = "", temperature: float = 0.7) -> str:
        """Generate a text completion via Ollama API.

        Args:
            prompt: The user prompt to send to the model.
            system: Optional system message to set model behaviour.
            temperature: Sampling temperature (0.0–1.0).

        Returns:
            The model's generated text.
        """
        body: dict = {
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "temperature": temperature,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(f"{self.base_url}/api/generate", json=body)
            response.raise_for_status()
        return response.json()["response"]

    async def generate_json(self, prompt: str, *, system: str = "", temperature: float = 0.3) -> dict:
        """Generate a structured JSON response via Ollama API.

        Args:
            prompt: The user prompt to send to the model.
            system: Optional system message to set model behaviour.
            temperature: Sampling temperature (0.0–1.0). Defaults to 0.3 for
                more deterministic structured output.

        Returns:
            Parsed JSON dict from the model's response.
        """
        body: dict = {
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "temperature": temperature,
            "stream": False,
            "format": "json",
        }
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(f"{self.base_url}/api/generate", json=body)
            response.raise_for_status()
        return json.loads(response.json()["response"])

    async def generate_with_history(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> str:
        """Generate a response continuing a multi-turn conversation.

        Args:
            messages: List of message dicts with "role" and "content" keys.
                Roles must be "system", "user", or "assistant".
            temperature: Sampling temperature (0.0–1.0).
            json_mode: When True, instructs Ollama to return valid JSON.
            max_tokens: Maximum tokens to generate (Ollama num_predict).

        Returns:
            The assistant's response text.
        """
        # Ollama's mistral-nemo hangs when system messages are passed in the
        # messages array.  Work around by extracting them into the top-level
        # "system" parameter and keeping only user/assistant messages.
        system_parts: list[str] = []
        chat_messages: list[dict] = []
        for msg in messages:
            if msg["role"] == "system":
                system_parts.append(msg["content"])
            else:
                chat_messages.append(msg)

        # If there are no user/assistant messages, there's nothing for the
        # chat API to respond to — caller should use generate() instead.
        if not chat_messages:
            chat_messages.append({"role": "user", "content": "Continue."})

        body: dict = {
            "model": self.model,
            "messages": chat_messages,
            "stream": False,
        }
        if system_parts:
            body["system"] = "\n\n".join(system_parts)
        if json_mode:
            body["format"] = "json"
        if max_tokens is not None:
            body["options"] = {"num_predict": max_tokens}

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=body)
            response.raise_for_status()
        return response.json()["message"]["content"]
