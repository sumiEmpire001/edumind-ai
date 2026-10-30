from dataclasses import dataclass, field
from typing import Literal, Protocol


@dataclass(frozen=True)
class MediaPart:
    mime: str
    data: bytes = field(repr=False)


@dataclass(frozen=True)
class Turn:
    role: Literal["user", "assistant"]
    content: str
    media: tuple[MediaPart, ...] = ()


class AcademicError(Exception):
    def __init__(self, code: str = "provider_failure"):
        self.code = (
            code
            if code
            in {"unavailable", "timeout", "empty_response", "rate_limited", "provider_failure"}
            else "provider_failure"
        )
        super().__init__(self.code)


class AcademicProvider(Protocol):
    available: bool
    mode: str

    async def generate(self, context: list[Turn]) -> str:
        """Honor cancellation. No side effects/tools; context is untrusted user/assistant text."""
        ...


class UnconfiguredProvider:
    available = False
    mode = "unconfigured"

    async def generate(self, context: list[Turn]) -> str:
        raise AcademicError("unavailable")
