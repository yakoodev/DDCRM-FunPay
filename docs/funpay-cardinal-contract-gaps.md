# FunPay Cardinal Contract Gaps

## Цель
Фиксация несовпадений между DDCRM worker v2 контрактом и текущим surface API `FunPayCardinal`.

## Текущий статус

1. `conversations.list` pagination:
   - DDCRM требует cursor-based paging.
   - Cardinal не предоставляет нативный курсор в формате DDCRM.
   - Статус: `deferred` (используется адаптерный synthetic cursor).

2. `conversations.*` timestamp / unread semantics:
   - DDCRM DTO предполагает корректные `lastMessageAt` и `createdAt` из первичного источника.
   - В адаптере v1 используются synthetic timestamps (`now`) и boolean->count mapping для unread (`0/1`).
   - Статус: `partial` (функционально работает, но точность временных меток и unread-count ограничена).

3. `products.*` canonical status/quantity semantics:
   - DDCRM ожидает унифицированные `status/version/attributes`.
   - Cardinal оперирует полями лотов и категориями с platform-specific полями.
   - Статус: `partial` (маппинг через adapter layer).

3.1 `products.create/products.update`:
   - DDCRM контракт допускает универсальное создание/патч продукта.
   - Cardinal требует platform-specific набор `LotFields`; V1.1 использует `attributes.templateLotId` как шаблон для клонирования/редактирования.
   - Статус: `partial` (`create/update` поддержаны, но требуют template-based flow и platform fields в schema).

4. `message attachments` в `conversations.messages.send`:
   - DDCRM контракт допускает массив `attachments`.
   - Cardinal поддерживает image upload отдельным методом, универсальный формат вложений отсутствует.
   - Статус: `deferred` (v1 ограничен текстом, image только extension-path).

5. `marketplaceAuth` scheme coverage:
   - V1 production path: `scheme=golden_key`.
   - `cookies/tokens/login_password` добавлены в унифицированный контракт как forward-compatible, но не активированы в Cardinal adapter по умолчанию.
   - Статус: `deferred`.

6. Account metadata completeness:
   - DDCRM `account.raw` допускает произвольный объект; Cardinal API возвращает частично разные структуры в зависимости от состояния сессии.
   - Статус: `partial`.

7. Worker account binding model:
   - Текущий API worker (`/internal/v2/worker/account|conversations|products`) не передаёт `accountId` в запросе.
   - Адаптер v1 опирается на single-tenant модель воркера (один контейнер на один DDCRM account) и читает auth-секреты строго по bound account scope.
   - Binding фиксируется через env (`FUNPAY_WORKER_ACCOUNT_ID`/`DDCRM_WORKER_ACCOUNT_ID`) или на первом `ext.account.*.apply`; попытка применить другой `accountId` возвращает `WORKER_RUNTIME_CONFLICT`.
   - Для multi-tenant режима потребуются дополнительные contract-field/action-конвенции для явного account-scope на read-операциях.
   - Статус: `partial` (single-tenant закрыт в v1, multi-tenant read-scope остаётся deferred).

8. Preflight валидация авторизации/прокси:
   - В worker API нет отдельного канонического preflight action для явной проверки `golden_key` + proxy до запуска рабочих операций.
   - Практически валидность определяется косвенно через `account.info`/`conversations.*`.
   - Статус: `deferred` (можно закрыть отдельным extension action, если потребуется UX-fast-fail).
