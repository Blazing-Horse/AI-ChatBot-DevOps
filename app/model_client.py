"""Talks to the AI model.

Two implementations share one interface:
- FoundryModelClient: the real one, calls the model deployed in Microsoft Foundry.
- FakeModelClient: answers without calling Azure, used by tests and local runs.
"""

import re
from dataclasses import dataclass
from typing import Protocol

SYSTEM_PROMPT = (
    "You are a friendly, concise assistant. "
    "Use the earlier messages in this conversation to remember what the user told you."
)


class ModelUnavailableError(Exception):
    """The model did not answer (timeout, network or server error)."""


class ModelBusyError(Exception):
    """The model refused because of rate limits (HTTP 429)."""


class ContentBlockedError(Exception):
    """The Foundry content filter blocked the request or the reply."""


@dataclass
class ModelReply:
    text: str
    total_tokens: int


class ModelClient(Protocol):
    def reply(self, history: list[dict], message: str) -> ModelReply: ...


class FakeModelClient:
    """Pretends to be the model. It can 'remember' a name from the history."""

    def reply(self, history: list[dict], message: str) -> ModelReply:
        if "what is my name" in message.lower():
            for item in reversed(history):
                match = re.search(r"my name is (\w+)", item["content"], re.IGNORECASE)
                if item["role"] == "user" and match:
                    return ModelReply(f"Your name is {match.group(1)}.", 0)
            return ModelReply("I don't know your name yet.", 0)
        return ModelReply(f"(fake model) You said: {message}", 0)


class FoundryModelClient:
    def __init__(self, base_url: str, deployment: str) -> None:
        import openai
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider

        token_provider = get_bearer_token_provider(
            DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
        )
        # timeout=30 seconds, max_retries=1: matches the design (retry once).
        self._client = openai.OpenAI(
            base_url=base_url, api_key=token_provider, timeout=30, max_retries=1
        )
        self._openai = openai
        self._deployment = deployment

    def reply(self, history: list[dict], message: str) -> ModelReply:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages += history
        messages.append({"role": "user", "content": message})
        try:
            response = self._client.chat.completions.create(
                model=self._deployment,
                messages=messages,
                # gpt-5-nano is a reasoning model: it uses max_completion_tokens
                # (not max_tokens) and "minimal" keeps answers fast and cheap.
                max_completion_tokens=2000,
                reasoning_effort="minimal",
            )
        except self._openai.RateLimitError as err:
            raise ModelBusyError() from err
        except self._openai.BadRequestError as err:
            if getattr(err, "code", None) == "content_filter":
                raise ContentBlockedError() from err
            raise ModelUnavailableError() from err
        except (
            self._openai.APITimeoutError,
            self._openai.APIConnectionError,
            self._openai.APIStatusError,
        ) as err:
            raise ModelUnavailableError() from err

        choice = response.choices[0]
        if choice.finish_reason == "content_filter":
            raise ContentBlockedError()
        tokens = response.usage.total_tokens if response.usage else 0
        return ModelReply(choice.message.content or "", tokens)
