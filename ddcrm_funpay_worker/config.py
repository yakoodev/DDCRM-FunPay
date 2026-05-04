from __future__ import annotations

import os
from dataclasses import dataclass


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_int(value: str | None, default: int, *, min_value: int, max_value: int) -> int:
    if value is None:
        return default

    try:
        parsed = int(value.strip())
    except (TypeError, ValueError):
        return default

    if parsed < min_value:
        return min_value
    if parsed > max_value:
        return max_value
    return parsed


@dataclass(frozen=True)
class WorkerConfig:
    bind_host: str
    bind_port: int
    provider: str
    storage_path: str
    service_auth_enabled: bool
    accepted_tokens: tuple[str, ...]
    blocked_internal_tokens: tuple[str, ...]
    proxy_encryption_key: str
    marketplace_auth_encryption_key: str
    bound_account_id: str | None
    funpay_golden_key: str | None
    funpay_user_agent: str | None
    funpay_request_timeout_seconds: int
    funpay_http_max_retries: int

    @staticmethod
    def load() -> "WorkerConfig":
        bind_host = os.getenv("WORKER_BIND_HOST", "0.0.0.0").strip() or "0.0.0.0"
        bind_port_raw = os.getenv("WORKER_BIND_PORT", "8080").strip()
        try:
            bind_port = int(bind_port_raw)
        except ValueError as exc:
            raise ValueError("WORKER_BIND_PORT должен быть числом.") from exc
        if bind_port < 1 or bind_port > 65535:
            raise ValueError("WORKER_BIND_PORT должен быть в диапазоне 1..65535.")

        accepted_tokens = tuple(_parse_csv(os.getenv("WORKER_API_SERVICE_AUTH_ACCEPTED_TOKENS")))
        if not accepted_tokens:
            accepted_tokens = ("worker-token-a", "worker-token-b")

        blocked_tokens = tuple(_parse_csv(os.getenv("INTERNAL_API_SERVICE_AUTH_ACCEPTED_TOKENS")))
        bound_account_id = (
            (os.getenv("FUNPAY_WORKER_ACCOUNT_ID") or "").strip()
            or (os.getenv("DDCRM_WORKER_ACCOUNT_ID") or "").strip()
            or None
        )

        return WorkerConfig(
            bind_host=bind_host,
            bind_port=bind_port,
            provider=(os.getenv("WORKER_PROVIDER", "funpay").strip() or "funpay").lower(),
            storage_path=os.getenv("WORKER_STORAGE_PATH", "./data/worker-state.sqlite3").strip(),
            service_auth_enabled=_parse_bool(os.getenv("WORKER_API_SERVICE_AUTH_ENABLED"), True),
            accepted_tokens=accepted_tokens,
            blocked_internal_tokens=blocked_tokens,
            proxy_encryption_key=os.getenv(
                "WORKER_PROXY_CREDENTIALS_ENCRYPTION_KEY",
                "ddcrm-local-worker-proxy-credentials-key",
            ).strip(),
            marketplace_auth_encryption_key=os.getenv(
                "WORKER_MARKETPLACE_AUTH_ENCRYPTION_KEY",
                "ddcrm-local-worker-marketplace-auth-key",
            ).strip(),
            bound_account_id=bound_account_id,
            funpay_golden_key=(os.getenv("FUNPAY_GOLDEN_KEY") or "").strip() or None,
            funpay_user_agent=(os.getenv("FUNPAY_USER_AGENT") or "").strip() or None,
            funpay_request_timeout_seconds=_parse_int(
                os.getenv("FUNPAY_REQUEST_TIMEOUT_SECONDS") or os.getenv("FUNPAY_REQUEST_TIMEOUT"),
                default=8,
                min_value=3,
                max_value=60,
            ),
            funpay_http_max_retries=_parse_int(
                os.getenv("FUNPAY_HTTP_MAX_RETRIES") or os.getenv("FUNPAY_MAX_RETRIES"),
                default=1,
                min_value=0,
                max_value=6,
            ),
        )
