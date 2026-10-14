from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langchain_core.tools import BaseTool


@dataclass
class AgentProfile:
    """Everything that makes one assistant persona: its prompt, tools and UI state."""

    name: str
    instructions: str
    tools: list[BaseTool]
    # Called after every tool run; the result is pushed to the browser UI (e.g. the cart).
    state_snapshot: Callable[[], Any] | None = None
