# DDCRM-FunPay Worker

Python/FastAPI реализация worker runtime для DDCRM (`/internal/v2/worker/*`) c адаптером под `FunPayCardinal`.

## Структура

- `vendor/FunPayCardinal` — upstream submodule.
- `ddcrm_funpay_worker/` — runtime API слой, idempotency, service-auth, storage.
- `docs/funpay-cardinal-contract-gaps.md` — зафиксированные contract-gap точки между DDCRM worker API и Cardinal.

## Что реализовано в V1

- Контрактные endpoint-ы:
  - `GET /internal/v2/worker/health`
  - `GET /internal/v2/worker/capabilities`
  - `GET /internal/v2/worker/account`
  - `GET /internal/v2/worker/conversations`
  - `GET/POST /internal/v2/worker/conversations/{conversationId}/messages`
  - `GET/POST/PATCH/DELETE /internal/v2/worker/products*`
  - `GET /internal/v2/worker/schemas/products`
  - `POST /internal/v2/worker/actions/{action}`
- Security:
  - `X-Service-Token` middleware;
  - запрет reuse токенов internal-контура (`INTERNAL_API_SERVICE_AUTH_ACCEPTED_TOKENS`).
- Idempotency:
  - `Idempotency-Key` обязателен для mutating endpoint-ов;
  - replay хранится в `worker-state` storage.
- Secret storage:
  - `ext.account.proxy-credentials.apply/reveal`;
  - `ext.account.marketplace-auth.apply`;
  - шифрование в SQLite storage (`AES-GCM`).
- Account scope:
  - worker работает в single-tenant режиме (один runtime account на контейнер);
  - binding фиксируется при первом `ext.account.*.apply` или через env `FUNPAY_WORKER_ACCOUNT_ID` / `DDCRM_WORKER_ACCOUNT_ID`;
  - read-операции (`account/conversations/products`) требуют установленный account binding.

## Запуск локально

1. Создайте `.env` на основе `.env.example`.
2. Установите зависимости:
   - `python -m pip install -e .`
3. Запустите API:
   - `python -m ddcrm_funpay_worker.main`

По умолчанию сервис слушает `0.0.0.0:8080`, path-prefix задаётся в Accounts Manager runtime template (`/internal/v2/worker`).

## Тесты

- Запуск:
  - `python -m pip install -e .[dev]`
  - `pytest -q`

## Обновление FunPayCardinal submodule

1. Обновить upstream refs:
   - `git submodule update --init --remote vendor/FunPayCardinal`
2. Зафиксировать новый pin-коммит submodule в этом репозитории.
3. Сверить `docs/funpay-cardinal-contract-gaps.md` (закрытые/новые gap).
