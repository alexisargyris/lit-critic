"""
Anthropic (Claude) implementation of the LLM client interface.

Wraps the ``anthropic.AsyncAnthropic`` SDK, translating between the
provider-agnostic ``LLMClient`` interface and Anthropic's messages API.
"""

import logging
from typing import AsyncIterator, Optional

from anthropic import AsyncAnthropic

from .base import LLMClient, LLMResponse, LLMToolResponse

logger = logging.getLogger(__name__)


class AnthropicClient(LLMClient):
    """LLMClient backed by the Anthropic messages API."""

    def __init__(self, api_key: str):
        self._client = AsyncAnthropic(api_key=api_key)

    # ------------------------------------------------------------------
    # Plain text completion
    # ------------------------------------------------------------------

    async def create_message(
        self,
        model: str,
        max_tokens: int,
        messages: list[dict],
        system: Optional[str] = None,
    ) -> LLMResponse:
        kwargs: dict = dict(
            model=model,
            max_tokens=max_tokens,
            messages=messages,
        )
        if system is not None:
            kwargs["system"] = system

        response = await self._client.messages.create(**kwargs)

        text = response.content[0].text if response.content else ""
        truncated = getattr(response, "stop_reason", None) == "max_tokens"

        return LLMResponse(text=text, truncated=truncated)

    # ------------------------------------------------------------------
    # Structured output via tool use
    # ------------------------------------------------------------------

    async def create_message_with_tool(
        self,
        model: str,
        max_tokens: int,
        messages: list[dict],
        tool_schema: dict,
        tool_name: str,
        system: Optional[str] = None,
    ) -> LLMToolResponse:
        """Call the Anthropic API with forced tool use.

        ``tool_schema`` is already in Anthropic's native format so no
        translation is needed.
        """
        kwargs: dict = dict(
            model=model,
            max_tokens=max_tokens,
            messages=messages,
            tools=[tool_schema],
            tool_choice={"type": "tool", "name": tool_name},
        )
        if system is not None:
            kwargs["system"] = system

        response = await self._client.messages.create(**kwargs)

        truncated = getattr(response, "stop_reason", None) == "max_tokens"

        # Extract tool_use block
        tool_input: dict = {}
        raw_texts: list[str] = []

        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                tool_input = block.input
            elif block.type == "text":
                raw_texts.append(block.text)

        return LLMToolResponse(
            tool_input=tool_input,
            truncated=truncated,
            raw_text="\n".join(raw_texts),
        )

    # ------------------------------------------------------------------
    # Streaming text completion
    # ------------------------------------------------------------------

    async def stream_message(
        self,
        model: str,
        max_tokens: int,
        messages: list[dict],
        system: Optional[str] = None,
    ) -> AsyncIterator[str | LLMResponse]:
        kwargs: dict = dict(
            model=model,
            max_tokens=max_tokens,
            messages=messages,
        )
        if system is not None:
            kwargs["system"] = system

        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text

        # After the stream context manager exits we can get the final message.
        final_message = await stream.get_final_message()
        full_text = final_message.content[0].text if final_message.content else ""
        truncated = getattr(final_message, "stop_reason", None) == "max_tokens"

        yield LLMResponse(text=full_text, truncated=truncated)
