# ADR-010: Resolución de secretos por-cuenta vía Secret Manager SDK en runtime (cacheado)

> **Status**: Accepted
> **Date**: 2026-06-02
> **Deciders**: @daniel, @marco
> **Relacionado**: refina [ADR-004](ADR-004-conversation-channel-account.md) (Conversation + ChannelAccount); patrón reusable por cualquier módulo futuro con secretos por-tenant/cuenta (ej. `bots` #6).

## Context

El módulo `conversations` (#5) necesita resolver credenciales **por `ChannelAccount`**: cada número de WhatsApp Business tiene su propio `access_token` y `app_secret` (y opcionalmente `phone_number_id`), porque la clínica puede operar **N números a la vez** (preventa/postventa, una vertical por número, etc. — ver ADR-004). El webhook valida la firma `X-Hub-Signature-256` con el `app_secret` de la cuenta concreta, y el envío outbound usa el `access_token` de esa misma cuenta contra la Graph API de Meta. La credencial es **dato por fila**, no configuración global.

El template **hoy** inyecta secretos **fijos por entorno en deploy-time**: el workflow de deploy corre `gcloud run deploy --set-secrets "SECRET_KEY=medisage-secret-key-{env}:latest,DB_*=..."`, que lee los secretos de GCP Secret Manager y los expone como **variables de entorno** del contenedor; la app los consume vía `Settings` (Pydantic), **sin usar el SDK de Secret Manager**. Ese mecanismo sirve perfectamente para secretos que son uno por deploy (la `SECRET_KEY` de firma de JWT, las credenciales de la BD), pero **no** para credenciales por-`ChannelAccount`:

- Las credenciales por-cuenta deben poder **agregarse sin redeploy** (un operador da de alta un segundo número de WhatsApp y empieza a operar de inmediato).
- El número de cuentas es **dinámico y abierto**; no se puede pre-declarar una env var por número en el workflow de deploy.

Hay que decidir **ahora** cómo resuelve `conversations` esas credenciales, porque F1 introduce `ChannelAccount.secret_name` y `channel_account.get_credentials(ca)`, y F2/F3 ya las consumen (validación de firma del webhook + envío outbound real).

> **Corrección a ADR-004**: ADR-004 (línea "Lo que esto nos obliga a hacer") afirmaba que `get_credentials()` resolvería el secreto contra GCP Secret Manager usando un *"cliente ya configurado en el template para `SECRET_KEY`"*. Esa afirmación es **errónea**: el template no tiene cliente del SDK de Secret Manager; lo que tiene es la inyección `--set-secrets → env var → Settings` descrita arriba (sin SDK). Este ADR la corrige y define el patrón real. ADR-004 queda actualizado ("act. 2026-06-02") apuntando aquí.

## Decision

**Resolver las credenciales por-cuenta con el SDK de GCP Secret Manager en runtime, detrás de un módulo cross-cutting reusable `app/core/secrets.py`, con cache TTL en memoria y fallback a variables de entorno para local/test.**

- Se agrega la dependencia **`google-cloud-secret-manager`** (pin en `pyproject.toml`).
- Módulo nuevo **`app/core/secrets.py`** (cross-cutting, **reusable** por el template — no vive dentro de `conversations`):
  - `async def resolve(secret_name: str) -> dict` — accede a la versión `latest` del secreto vía SDK, lo **parsea como JSON** (`{access_token, app_secret, phone_number_id?, ...}`) y lo devuelve.
  - **Cache TTL (~10 min)** en memoria (`dict` + reloj `monotonic`) keyed por `secret_name`, para no golpear Secret Manager en cada webhook inbound.
  - Cliente del SDK **lazy** (se construye en la primera llamada, **no al import**) para no romper el boot del proceso cuando no hay GCP disponible (local/smoke).
  - Si la versión instalada del SDK expone cliente **async**, se usa ese; si no, la llamada sync corre en threadpool.
- `conversations.services.channel_account.get_credentials(ca) -> dict` orquesta:
  - Si `ca.secret_name` está poblado **y** no estamos en modo local → `await secrets.resolve(ca.secret_name)`.
  - Si `ca.secret_name` es `NULL`, o `ENV_NAME=dev`, o `USE_LOCAL_SECRETS` está activo → **fallback a env** vía `Settings` (`GCP_PROJECT_ID`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_PHONE_NUMBER_ID`; defaults vacíos).
  - Si no resuelve nada (ni secreto ni fallback) → excepción de dominio `CHANNEL_CREDENTIALS_MISSING` (`BadRequestException` → HTTP 400 — mala configuración del operador).
- El **valor** del secreto **nunca** viaja a un schema ni a la UI: los schemas exponen solo `secret_name` + un flag derivado `credentials_configured: bool`. `get_credentials` es **server-only**.
- La Service Account de Cloud Run **ya tiene** `roles/secretmanager.secretAccessor`; los secretos por entorno (`medisage-whatsapp-*-{qa,prod}`) se crean al desplegar F1/F2.

## Alternatives Considered

### Opción A — Inyección por env (lo que hace hoy el template)
- **Pros**: cero dependencia nueva; ya probado en prod para `SECRET_KEY`/DB-creds; el secreto nunca toca el código de la app (lo monta Cloud Run).
- **Cons**: el set de env vars se fija **en deploy-time**. Soporta **un único número por deploy**; agregar un segundo número de WhatsApp obliga a redeployar con nuevas env vars (`WHATSAPP_ACCESS_TOKEN_2`, …) — y la cantidad de cuentas es dinámica, no se puede pre-declarar.
- **Rechazada porque**: no soporta multi-cuenta sin redeploy, que es el requisito central de ADR-004 (preventa/postventa y verticales en números separados). Se conserva, eso sí, **como fallback** para local/test (`USE_LOCAL_SECRETS`) y para una cuenta única en dev.

### Opción B — Columna cifrada en la BD (Fernet con `SECRET_KEY`)
- **Pros**: una sola fuente (la fila de `ChannelAccount` lleva su credencial cifrada); sin dependencia de Secret Manager en el hot path; agregar un número es un INSERT.
- **Cons**: el secreto (aunque cifrado) **vive en los backups de la BD** y en cualquier dump/replica → mayor superficie de exposición; la rotación implica reescribir filas; mezcla la gestión de credenciales sensibles con datos de negocio; y `SECRET_KEY` pasaría a ser una llave de descifrado de credenciales de terceros (eleva su criticidad).
- **Rechazada porque**: Secret Manager es el almacén de secretos canónico del stack (GCP), con su propio control de acceso (IAM), versionado y rotación; meter el secreto en la BD amplía la superficie sin ganar nada que el SDK no dé.

### Opción C — SDK de Secret Manager en runtime, cacheado (Aceptada)
- Ver Decision. El secreto vive en Secret Manager (un secreto por cuenta), la app lo resuelve por `secret_name` en runtime con cache TTL, y agregar un número no requiere redeploy.

## Consequences

### Positivas
- **Multi-cuenta sin redeploy**: dar de alta un número nuevo = crear su secreto + un `ChannelAccount` con su `secret_name`; opera de inmediato.
- **Patrón reusable**: `app/core/secrets.py` es cross-cutting (no vive en `conversations`) → lo consumirán otros módulos con secretos por-tenant/cuenta (ej. `bots` #6 si necesita credenciales propias de un proveedor).
- **Rotación sin tocar la BD**: rotar una credencial es publicar una nueva versión del secreto en Secret Manager; no hay datos sensibles en filas ni en backups.
- **Superficie mínima**: el valor del secreto nunca sale del servidor (los schemas exponen solo `secret_name` + `credentials_configured`); el control de acceso lo lleva IAM (la SA con `secretAccessor`).
- **Conserva el camino local**: el fallback a env + el cliente lazy mantienen el smoke (sqlite) y el dev sin GCP funcionando sin cambios de flujo.

### Negativas / Trade-offs
- **Dependencia nueva** (`google-cloud-secret-manager`) en el runtime de la app, con su footprint y su superficie de mantenimiento.
- **El smoke/local NO debe golpear Secret Manager**: se mitiga con el **fallback a env** + **cliente lazy** (no al import) + **mock** del resolver en los tests. Un error de configuración que deje colar una llamada real al SDK en el smoke rompería el aislamiento del test.
- **Latencia de propagación de la rotación**: con cache TTL ~10 min, una credencial recién rotada tarda **hasta ~10 min** en propagarse a todas las instancias. Aceptable para el caso (las rotaciones son raras y planificadas); si se necesitara propagación inmediata, habría que invalidar la cache explícitamente.
- **Dependencia de GCP en el hot path del cloud**: en qa/prod, resolver una cuenta con `secret_name` requiere que Secret Manager esté disponible (mitigado por la cache: el primer hit por cuenta paga la latencia, el resto del TTL no).

### Lo que esto nos obliga a hacer
- Crear `app/core/secrets.py` (resolve + cache TTL + cliente lazy) y `conversations.services.channel_account.get_credentials(ca)` (secreto → fallback env → `CHANNEL_CREDENTIALS_MISSING`) en **F1**.
- Agregar `google-cloud-secret-manager` a `pyproject.toml` (F1) y los `Settings` del fallback con defaults vacíos: `GCP_PROJECT_ID`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_PHONE_NUMBER_ID`.
- **Mockear** el resolver en los smoke tests (sqlite, single-thread) — nunca tocar Secret Manager en local/test.
- **Crear los secretos por entorno** (`medisage-whatsapp-*-{qa,prod}`) en Secret Manager al desplegar F1/F2 (la SA de Cloud Run ya tiene `roles/secretmanager.secretAccessor`).
- Mantener `secret_name` como la **única** referencia visible en schemas/UI; jamás exponer el valor (solo el flag `credentials_configured`).

## Referencias

- [ADR-004](ADR-004-conversation-channel-account.md) — `ChannelAccount` + `Conversation` (actualizado 2026-06-02: corrige la afirmación sobre el "cliente ya configurado" y apunta aquí).
- [ADR-009](ADR-009-forward-fk-deferred-cross-module.md) — patrón forward que también aplica en `conversations` (FKs a `bots`/`marketing`).
- Fichas del módulo: [`conversations/README.md`](../modules/conversations/README.md) (sección "Secret resolver"), [`conversations/backend.md`](../modules/conversations/backend.md) (`app/core/secrets.py`, `channel_account.get_credentials`).
- Código futuro: `backend/app/core/secrets.py`, `backend/app/modules/conversations/services/channel_account.py`.
- Workflow de deploy actual (inyección por env): `gcloud run deploy --set-secrets "SECRET_KEY=medisage-secret-key-{env}:latest,DB_*=..."`.
- Docs externos: SDK <https://cloud.google.com/secret-manager/docs/reference/libraries> · firma de webhook Meta <https://developers.facebook.com/docs/graph-api/webhooks/getting-started#validating-payloads>.
