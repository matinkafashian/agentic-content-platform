from dataclasses import dataclass, field
from typing import Protocol

from app.publishing.models import PostBundle


@dataclass(frozen=True)
class DeliveryResult:
    ok: bool
    external_message_ids: list[str] = field(default_factory=list)
    error_code: str | None = None
    safe_error_message: str | None = None
    retryable: bool = False

    @classmethod
    def success(cls, message_ids: list[str]) -> "DeliveryResult":
        return cls(ok=True, external_message_ids=list(message_ids))

    @classmethod
    def failure(
        cls, *, code: str, message: str, retryable: bool
    ) -> "DeliveryResult":
        return cls(
            ok=False,
            error_code=code,
            safe_error_message=message,
            retryable=retryable,
        )


class PlatformAdapter(Protocol):
    platform: str

    def send(
        self, bundle: PostBundle, destination: str, idempotency_key: str
    ) -> DeliveryResult: ...


class SandboxAdapter:
    """No-network adapter used to prove the full publishing workflow safely."""

    platform = "sandbox"

    def send(
        self, bundle: PostBundle, destination: str, idempotency_key: str
    ) -> DeliveryResult:
        ids = [f"sandbox-{idempotency_key}-post"]
        if bundle.voice_relative_path:
            ids.append(f"sandbox-{idempotency_key}-voice")
        return DeliveryResult.success(ids)
