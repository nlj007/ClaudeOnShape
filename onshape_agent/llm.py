"""LLM abstraction — Chat protocol + adapters.

Adapters translate neutral tool schemas and message lists to provider-specific
formats. This lets us swap Anthropic for Ollama/Gemma later without touching
agent code.
"""
from dataclasses import dataclass
from typing import Protocol, Any
import os


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class TextBlock:
    text: str


@dataclass
class ChatResponse:
    """Unified response. `blocks` preserves order for multi-tool-call turns."""
    blocks: list  # list of TextBlock | ToolCall
    stop_reason: str  # 'end_turn' | 'tool_use'
    raw_assistant_content: Any  # opaque; pass back in next messages call


class Chat(Protocol):
    def complete(self, system: str, messages: list, tools: list) -> ChatResponse: ...
    def format_tool_result(self, tool_use_id: str, content: str) -> Any: ...
    def format_assistant_turn(self, response: ChatResponse) -> Any: ...


class AnthropicChat:
    """Adapter for the Anthropic Messages API with tool use."""

    def __init__(self, model: str = "claude-sonnet-4-6", max_tokens: int = 4096):
        import anthropic
        # The shell may export an empty ANTHROPIC_API_KEY (common in zsh
        # profiles) which blocks dotenv from loading the real value. Force an
        # override from the project .env if the in-process value is missing.
        api_key = os.environ.get("ANTHROPIC_API_KEY") or ""
        if not api_key:
            from dotenv import dotenv_values
            from pathlib import Path
            # Walk up from this file looking for .env (project root).
            here = Path(__file__).resolve()
            for parent in [here.parent, *here.parents]:
                env_path = parent / ".env"
                if env_path.exists():
                    api_key = dotenv_values(env_path).get("ANTHROPIC_API_KEY") or ""
                    break
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set (checked env + .env)")
        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def complete(self, system: str, messages: list, tools: list) -> ChatResponse:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            tools=tools,
            messages=messages,
        )
        blocks = []
        for b in resp.content:
            if getattr(b, "type", None) == "tool_use":
                blocks.append(ToolCall(id=b.id, name=b.name, input=b.input))
            elif hasattr(b, "text"):
                blocks.append(TextBlock(text=b.text))
        return ChatResponse(
            blocks=blocks,
            stop_reason=resp.stop_reason,
            raw_assistant_content=resp.content,
        )

    def format_tool_result(self, tool_use_id: str, content: str) -> dict:
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": content,
        }

    def format_assistant_turn(self, response: ChatResponse) -> dict:
        return {"role": "assistant", "content": response.raw_assistant_content}
