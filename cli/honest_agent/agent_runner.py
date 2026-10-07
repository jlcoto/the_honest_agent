from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import is_dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .raw import EvalRecorder


def to_jsonable(obj: Any) -> Any:
    """A JSON-safe copy of an SDK object (pydantic models from the Anthropic, OpenAI and
    MCP SDKs), as close to the object as JSON allows: field names as the SDK's wire
    format spells them (`isError`, `inputSchema`), nothing dropped."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json", by_alias=True)
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if is_dataclass(obj) or hasattr(obj, "__dict__"):
        return {k: to_jsonable(v) for k, v in vars(obj).items() if not k.startswith("_")}
    return obj


def plain_content(content: Any) -> Any:
    """Converts Anthropic SDK content blocks (pydantic models, from `response.content`)
    into plain dicts, so the conversation sent back to Claude on the next turn -- and
    recorded in that turn's request -- is JSON-safe."""
    if isinstance(content, list):
        return [plain_content(item) for item in content]
    if hasattr(content, "model_dump"):
        return content.model_dump(mode="json")
    return content


class AgentClient(ABC):
    """Interface any agent backend must implement to be evaluated.

    `run` drives the agent's tool-use loop for one prompt and sends every model and tool
    call through `record` (raw.EvalRecorder), which keeps the raw exchange. It returns
    nothing: the answer, the trace and the scores are all derived from that record
    (derive.py), so a past run can be re-derived without running the agent again.
    """

    @abstractmethod
    async def run(self, prompt: str, record: EvalRecorder) -> None: ...
