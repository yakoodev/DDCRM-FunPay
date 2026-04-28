from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import WorkerConfig
from .errors import ApiError, WorkerErrorCodes, platform_error, runtime_conflict
from .models import WorkerV2AccountInfo, WorkerV2ConversationMessage, WorkerV2ConversationSummary, WorkerV2Product
from .storage import WorkerStateStorage


VENDOR_ROOT = Path(__file__).resolve().parents[1] / "vendor" / "FunPayCardinal"
if str(VENDOR_ROOT) not in sys.path:
    sys.path.insert(0, str(VENDOR_ROOT))

try:
    from FunPayAPI.account import Account
    from FunPayAPI.common import exceptions as fp_exceptions
except Exception:  # pragma: no cover - guarded at runtime
    Account = None  # type: ignore[assignment]
    fp_exceptions = None  # type: ignore[assignment]


@dataclass(frozen=True)
class CardinalCredentials:
    account_id: str
    golden_key: str
    user_agent: str | None
    proxy: dict[str, str] | None
    source_scheme: str


class CardinalAdapter:
    def __init__(self, config: WorkerConfig, storage: WorkerStateStorage) -> None:
        self._config = config
        self._storage = storage

    def list_capabilities(self) -> list[str]:
        return [
            "ext.account.proxy-credentials.apply",
            "ext.account.proxy-credentials.reveal",
            "ext.account.marketplace-auth.apply",
        ]

    def resolve_credentials(self, account_id: str) -> CardinalCredentials:
        normalized_account_id = account_id.strip()
        if not normalized_account_id:
            raise runtime_conflict("Worker account scope не инициализирован (accountId binding отсутствует).")

        auth = self._storage.read_marketplace_auth(normalized_account_id)
        scheme = str(auth["scheme"]).strip().lower() if auth else "golden_key"
        credentials = auth.get("credentials", {}) if auth else {}

        if scheme != "golden_key":
            raise runtime_conflict(
                f"marketplaceAuth.scheme={scheme} пока не поддерживается в Cardinal adapter v1.",
                details={"deferred": True},
            )

        golden_key = str(credentials.get("golden_key", "")).strip()
        user_agent = str(credentials.get("user_agent", "")).strip() or None
        if not golden_key:
            golden_key = self._config.funpay_golden_key or ""
        if not user_agent:
            user_agent = self._config.funpay_user_agent

        if not golden_key:
            raise platform_error(
                "golden_key отсутствует. Примените ext.account.marketplace-auth.apply или задайте FUNPAY_GOLDEN_KEY.",
                details={"scheme": scheme, "accountId": normalized_account_id},
            )

        proxy = None
        proxy_record = self._storage.read_proxy_credentials(normalized_account_id)
        if proxy_record is not None:
            login = proxy_record["login"]
            password = proxy_record["password"]
            host = proxy_record["host"]
            port = proxy_record["port"]
            proxy_url = f"http://{login}:{password}@{host}:{port}"
            proxy = {"http": proxy_url, "https": proxy_url}

        return CardinalCredentials(
            account_id=normalized_account_id,
            golden_key=golden_key,
            user_agent=user_agent,
            proxy=proxy,
            source_scheme=scheme,
        )

    def _create_account_client(self, account_id: str) -> tuple[Account, CardinalCredentials]:
        if Account is None:
            raise ApiError(
                status_code=500,
                error_code=WorkerErrorCodes.INTERNAL_ERROR,
                message="FunPayCardinal не загружен. Проверьте submodule vendor/FunPayCardinal.",
            )
        credentials = self.resolve_credentials(account_id)
        client = Account(
            credentials.golden_key,
            user_agent=credentials.user_agent,
            proxy=credentials.proxy,
        )
        return client, credentials

    def account_info(self, account_id: str) -> WorkerV2AccountInfo:
        client, credentials = self._create_account_client(account_id)
        try:
            client.get()
        except Exception as exc:  # pragma: no cover - network runtime
            self._translate_exception(exc)
        profile = {
            "userAgent": credentials.user_agent,
            "proxyConfigured": credentials.proxy is not None,
            "authScheme": credentials.source_scheme,
        }
        raw = {
            "activeSales": client.active_sales,
            "activePurchases": client.active_purchases,
            "currency": getattr(client.currency, "code", None),
            "balance": client.total_balance,
        }
        return WorkerV2AccountInfo(
            provider=self._config.provider,
            accountId=str(client.id),
            nickname=client.username or "unknown",
            status="connected",
            profile=profile,
            raw=raw,
        )

    def list_conversations(self, account_id: str) -> list[WorkerV2ConversationSummary]:
        client, _ = self._create_account_client(account_id)
        try:
            client.get()
            chats = list(client.get_chats(update=True).values())
        except Exception as exc:  # pragma: no cover - network runtime
            self._translate_exception(exc)

        chats = sorted(chats, key=lambda chat: int(getattr(chat, "node_msg_id", 0)), reverse=True)
        now = datetime.now(UTC)
        return [
            WorkerV2ConversationSummary(
                conversationId=str(chat.id),
                peerId=str(chat.id),
                peerName=chat.name or "unknown",
                unreadCount=1 if bool(chat.unread) else 0,
                lastMessagePreview=chat.last_message_text or "",
                lastMessageAt=now,
            )
            for chat in chats
        ]

    def list_messages(self, account_id: str, conversation_id: str) -> list[WorkerV2ConversationMessage]:
        client, _ = self._create_account_client(account_id)
        try:
            client.get()
            numeric_chat_id = int(conversation_id)
            messages = client.get_chat_history(numeric_chat_id)
        except ValueError as exc:
            raise platform_error("conversationId должен быть числовым идентификатором FunPay.") from exc
        except Exception as exc:  # pragma: no cover - network runtime
            self._translate_exception(exc)

        now = datetime.now(UTC)
        result: list[WorkerV2ConversationMessage] = []
        for message in messages:
            direction = "out" if int(getattr(message, "author_id", 0)) == int(client.id or 0) else "in"
            attachments = None
            if getattr(message, "image_link", None):
                attachments = [{"type": "image", "url": message.image_link}]
            result.append(
                WorkerV2ConversationMessage(
                    messageId=str(message.id),
                    direction=direction,
                    text=message.text or "",
                    attachments=attachments,
                    createdAt=now,
                )
            )

        result.sort(key=lambda item: int(item.messageId), reverse=True)
        return result

    def send_message(self, account_id: str, conversation_id: str, text: str, has_attachments: bool) -> WorkerV2ConversationMessage:
        if has_attachments:
            raise runtime_conflict("В V1 Cardinal adapter поддерживается только текстовая отправка без attachments.")

        client, _ = self._create_account_client(account_id)
        try:
            client.get()
            numeric_chat_id = int(conversation_id)
            message = client.send_message(numeric_chat_id, text=text)
        except ValueError as exc:
            raise platform_error("conversationId должен быть числовым идентификатором FunPay.") from exc
        except Exception as exc:  # pragma: no cover - network runtime
            self._translate_exception(exc)

        direction = "out" if int(getattr(message, "author_id", 0)) == int(client.id or 0) else "in"
        return WorkerV2ConversationMessage(
            messageId=str(message.id),
            direction=direction,
            text=message.text or text,
            createdAt=datetime.now(UTC),
        )

    def list_products(self, account_id: str) -> list[WorkerV2Product]:
        client, _ = self._create_account_client(account_id)
        try:
            client.get()
            profile = client.get_user(int(client.id))
            lots = profile.get_lots()
        except Exception as exc:  # pragma: no cover - network runtime
            self._translate_exception(exc)

        products: list[WorkerV2Product] = []
        for lot in lots:
            currency_code = getattr(getattr(lot, "currency", None), "code", "rub")
            products.append(
                WorkerV2Product(
                    productId=str(lot.id),
                    title=lot.title or f"Lot {lot.id}",
                    description=lot.description,
                    price={"amount": float(lot.price), "currency": currency_code},
                    status="active",
                    quantity=lot.amount if lot.amount is not None else 0,
                    attributes={
                        "subcategoryId": getattr(getattr(lot, "subcategory", None), "id", None),
                        "subcategoryType": str(getattr(getattr(lot, "subcategory", None), "type", "")),
                        "server": lot.server,
                        "side": lot.side,
                        "autoDelivery": bool(getattr(lot, "auto", False)),
                    },
                    version=self._version_from_lot(lot),
                    schemaId="funpay.item.v1",
                )
            )
        products.sort(key=lambda item: item.productId, reverse=True)
        return products

    def create_product_not_supported(self) -> None:
        raise runtime_conflict("products.create в Cardinal adapter v1 пока не поддержан.")

    def update_product_not_supported(self) -> None:
        raise runtime_conflict("products.update в Cardinal adapter v1 пока не поддержан.")

    def delete_product(self, account_id: str, product_id: str) -> str:
        client, _ = self._create_account_client(account_id)
        try:
            numeric_product_id = int(product_id)
            client.get()
            client.delete_lot(numeric_product_id)
        except ValueError as exc:
            raise platform_error("productId должен быть числовым идентификатором FunPay лота.") from exc
        except Exception as exc:  # pragma: no cover - network runtime
            self._translate_exception(exc)
        return f"deleted:{product_id}:{int(datetime.now(UTC).timestamp())}"

    def _version_from_lot(self, lot: Any) -> str:
        payload = {
            "id": str(lot.id),
            "title": lot.title,
            "description": lot.description,
            "price": lot.price,
            "amount": lot.amount,
            "auto": bool(getattr(lot, "auto", False)),
        }
        digest = hashlib.sha1(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
        return digest[:16]

    def _translate_exception(self, exc: Exception) -> None:
        if fp_exceptions is not None and isinstance(exc, fp_exceptions.UnauthorizedError):
            raise ApiError(401, WorkerErrorCodes.AUTH_FAILED, "FunPay авторизация не удалась (golden_key/session).") from exc
        raise ApiError(502, WorkerErrorCodes.UNAVAILABLE, "FunPay/Cardinal временно недоступен.", details={"reason": str(exc)}) from exc
