# Manual Técnico de medisage (Plataforma de Chatbots)

> Manual técnico consolidado del proyecto. Reúne, de forma integrada, la arquitectura,
> la guía de instalación, la operación del pipeline de Integración y Despliegue Continuo,
> la guía de despliegue a Google Cloud y los procedimientos de respaldo y restauración.
>
> Este documento es el manual técnico al que hace referencia el Anexo G.9 de la tesis.
> Está escrito para una persona con perfil técnico (desarrollador o responsable de
> operación) que necesite instalar, desplegar, operar o reconstruir la plataforma.
>
> Convención de nombres: el repositorio se llama `saya-template-stack` por legado, pero el
> producto es **medisage**. En la tesis el sistema se denomina genéricamente "Plataforma de
> chatbots". El proyecto de Google Cloud es `proyecto-ifc-497317` y la región es `us-central1`.

## Índice

1. [Visión general del sistema](#1-vision-general-del-sistema)
2. [Arquitectura](#2-arquitectura)
3. [Guía de instalación y entorno local](#3-guia-de-instalacion-y-entorno-local)
4. [Datos y migraciones](#4-datos-y-migraciones)
5. [Operación del pipeline de CI/CD](#5-operacion-del-pipeline-de-cicd)
6. [Despliegue a Google Cloud](#6-despliegue-a-google-cloud)
7. [Respaldo y restauración](#7-respaldo-y-restauracion)
8. [Operación y resolución de problemas](#8-operacion-y-resolucion-de-problemas)
9. [Hardening de preproducción](#9-hardening-de-preproduccion)
10. [Referencias](#10-referencias)

Documentos de detalle que complementan este manual (en el mismo repositorio):
`docs/ARCHITECTURE.md`, `docs/SETUP.md`, `docs/DEPLOYMENT.md`, `docs/BRANCHING.md`,
`docs/HARDENING.md`, `docs/PERMISSIONS.md`, los diagramas en `docs/diagrams/` y las
decisiones de arquitectura en `docs/decisions/` (ADR-001 a ADR-015).

---

## 1. Visión general del sistema

medisage es una plataforma web que permite a clínicas especializadas ambulatorias crear y
operar chatbots conversacionales sobre WhatsApp para atender pacientes y gestionar reservas
de citas, con un panel administrativo y tableros de resultados.

| Capa | Tecnología | Despliegue |
|---|---|---|
| Frontend | Next.js 16 (App Router) y React 19, TypeScript, Fluent UI 9 | Vercel |
| Backend | FastAPI y SQLAlchemy 2.0 async (Python 3.11) | Cloud Run |
| Base de datos relacional | PostgreSQL 16 | Cloud SQL (conexión por unix socket) |
| Mensajería en tiempo real | Firestore (read-model CQRS) | Firestore (bases nombradas) |
| Despacho asíncrono del bot | Cloud Tasks | Cloud Tasks |
| Refresco de tableros | Cloud Scheduler | Cloud Scheduler |
| Secretos | Secret Manager | Secret Manager |
| Imágenes de contenedor | Artifact Registry | Artifact Registry |
| Autenticación | JWT en cookies httpOnly y RBAC | (transversal) |

El backend se organiza en **once módulos** (diez de dominio mas `admin`): `admin`, `catalog`,
`clinic`, `staff`, `crm`, `conversations`, `bots`, `scheduling`, `marketing`, `calendar`,
`dashboards`. El modelo de datos tiene **56 tablas** (47 entidades ORM mas 9 tablas de
asociación). La API expone alrededor de **213 operaciones en 11 dominios** bajo el prefijo
`/api/v1` (216 visibles en Swagger contando los webhooks y la sonda de salud).

Hay dos entornos: **qa** y **prod**. Por nomenclatura heredada, el servicio y la cuenta de
servicio de producción van **sin** sufijo (`medisage-api`, `medisage-sa`), mientras que los
de QA llevan `-qa`.

---

## 2. Arquitectura

Vista narrativa. Para el detalle por pieza, ver `docs/ARCHITECTURE.md`, los diagramas de
`docs/diagrams/` y los ADR de `docs/decisions/`.

### 2.1 Frontera entre capas

```
Navegador  --HTTPS y cookie httpOnly-->  Next.js (Vercel)  --Bearer JWT (solo servidor)-->  FastAPI (Cloud Run)  --unix socket-->  Cloud SQL
```

Reglas que rigen la frontera:

- El **navegador nunca habla directo con FastAPI**. Toda llamada al backend nace en el
  servidor de Next.js, que inyecta el token. Así `BACKEND_URL` y el JWT viven solo del lado
  servidor (`services/backend.client.ts` declara `import "server-only"`).
- El **JWT vive en una cookie httpOnly**, no en `localStorage`. El JavaScript de cliente no
  puede leerlo.
- El **backend es la fuente de verdad de los permisos**. El frontend solo prefiltra la
  interfaz. El backend rechaza con 403 sin importar lo que el front haya ocultado.
- Los **permisos viajan en el access token** como claim `permissions[]`. No se consulta la
  base de datos por request.

### 2.2 Backend en cinco capas

Cada módulo de dominio (`backend/app/modules/<dominio>/`) se organiza en cinco capas:

```
models/         ORM de SQLAlchemy, una entidad por archivo mas associations.py para M:N
schemas/        Pydantic v2: Create, Update, Item, Detail, Option
repositories/   CRUD async; extienden BaseRepository[Model]; definen ALLOWED_FIELDS (whitelist de filtro/orden)
services/       Lógica de negocio (funciones, no clases); validan, orquestan, lanzan excepciones de dominio
routers/        Endpoints FastAPI; validan tipos y delegan al service
```

Lo transversal vive en `backend/app/core/` (config, db, security, dependencies, seed,
exceptions, rate_limit, logging, firestore, cloud_tasks, secrets) y `backend/app/shared/`
(mixins, `BaseRepository`, esquemas base, query_builder).

Reglas inviolables por capa:

- Los **routers** reciben el usuario autenticado, la sesión y el payload Pydantic, y delegan.
  No importan SQLAlchemy ni arman respuestas a mano.
- Los **services** lanzan excepciones de dominio (`NotFoundException`, `AlreadyExistsException`,
  `BadRequestException`, `UnauthorizedException`, `ForbiddenException`), nunca `HTTPException`.
  No hacen commit (lo hace `get_db`). Un handler global traduce la excepción al envoltorio
  `{success: false, detail, code?, errors?}`.
- Los **repositories** encapsulan el SQL y respetan `ALLOWED_FIELDS` como whitelist de
  columnas filtrables y ordenables (evita filtrar por columnas privadas).
- Los **modelos** heredan `Base` mas los mixins `PrimaryKeyMixin`, `ActiveMixin`,
  `SoftDeleteMixin`, `TimestampMixin`.

`backend/app/main.py` crea la aplicación, configura el logging, registra el middleware de
contexto de request (`X-Request-ID`), el CORS, el rate limiting (slowapi), los handlers de
excepción, y monta los routers de los once módulos mas el router de webhooks, todos bajo el
prefijo `/api/v1`. Expone una sonda de salud en `GET /health`. Swagger UI (`/docs`) y ReDoc
(`/redoc`) solo se publican cuando `DEBUG=True`.

### 2.3 Frontend con App Router

El frontend (Next.js 16, App Router) usa Server Components para las páginas (precargan datos
con permiso verificado), Server Actions para las mutaciones (con Zod compartido y
`revalidateTag`), y Client Components para formularios y tablas. El estado de paginación,
filtros y orden vive en la URL (con `nuqs`) y se cachea con TanStack Query. El middleware de
borde (`middleware.ts`) protege las rutas y refresca el token de forma proactiva.

### 2.4 Persistencia dual

medisage usa dos almacenes con responsabilidades distintas (ADR-005, ADR-011):

- **Cloud SQL (PostgreSQL 16)** es el plano de control y la fuente de verdad de todos los
  datos operativos. La conexión usa el driver async `asyncpg`. La URL se arma en
  `backend/app/core/config.py` y conmuta sola: unix socket en Cloud Run
  (`postgresql+asyncpg://USER:PASS@/DB?host=/cloudsql/INSTANCIA`) o TCP en local. El pool
  (`backend/app/core/database.py`) usa `pool_size=5`, `max_overflow=5`, `pool_recycle=300`
  segundos y `pool_pre_ping=True`.
- **Firestore** sostiene el read-model en tiempo real del módulo `conversations` (el hilo de
  mensajes del inbox). Es un patrón CQRS: el backend escribe el control plane en Postgres y,
  mediante una tabla `message_outbox`, proyecta de forma síncrona el mensaje a Firestore con
  el Admin SDK. El navegador solo **lee** ese stream con un Custom Token de Firebase minteado
  por el backend. Las reglas de seguridad (`firestore.rules`) prohíben toda escritura desde el
  cliente (solo el Admin SDK escribe, que las bypassa). Firestore usa **bases nombradas**:
  `medisage` en prod y `medisage-qa` en QA, en un proyecto compartido con otro sistema legado
  (por eso nunca se toca la base `(default)`).

> Implicancia de respaldo, importante: el **contenido de los mensajes vive solo en Firestore**.
> Postgres guarda `message_outbox` y datos denormalizados, pero si esas filas se purgan,
> Firestore deja de ser totalmente reconstruible desde Postgres. Ver la sección 7.

### 2.5 Integraciones de Google Cloud en runtime

- **Cloud Tasks (ADR-012)** despacha el turno del bot de forma asíncrona. Cuando entra un
  mensaje por el webhook de WhatsApp y la conversación está asignada al bot, el backend encola
  una tarea en la cola `medisage-bot-turns-<entorno>`. La tarea hace
  `POST {SERVICE_BASE_URL}/api/v1/bots/engine/dispatch`. El endpoint no tiene RBAC: se protege
  con un secreto compartido en el header `X-Bot-Dispatch-Secret` (variable `BOT_DISPATCH_SECRET`),
  comparado en tiempo constante. Si la cola no está configurada (o en `dev`), el despacho es un
  no-op silencioso. La deduplicación usa un nombre de tarea determinista por conversación y
  mensaje de entrada.
- **Cloud Scheduler (ADR-015)** dispara el refresco del rollup de tableros cada 10 minutos:
  `POST /api/v1/dashboards/internal/refresh`, protegido por el secreto compartido en el header
  `X-Dashboard-Refresh-Secret` (variable `DASHBOARD_REFRESH_SECRET`). El refresco recomputa una
  ventana móvil de 90 días sobre la tabla materializada `dashboard_daily_metric`. El plano de
  lectura solo suma sobre ese rollup, lo que sostiene el tiempo de respuesta del panel (RNF-05).
- **Secret Manager (ADR-010)** se usa de dos formas. En tiempo de despliegue, `gcloud run deploy
  --set-secrets` monta secretos como variables de entorno (las nueve de la sección 6). En
  tiempo de ejecución, el SDK resuelve credenciales por cuenta que deben agregarse sin
  redesplegar (por ejemplo, las credenciales de WhatsApp de cada `ChannelAccount`), con una
  cache en memoria de 600 segundos.
- **Cloud Storage** no se usa todavía en runtime (no hay dependencia ni bucket). Está previsto
  para adjuntos de WhatsApp, fotos o firmas de doctores y reportes pesados, todo diferido a una
  fase posterior.

### 2.6 Seguridad

- **Autenticación**: el access token (15 minutos) lleva los claims `roles[]` y `permissions[]`,
  lo que permite autorizar en O(1) sin consultar la base. El refresh token (7 días) lleva una
  `family` (UUID). Cada refresco rota ambos tokens y mantiene la familia. El logout o la
  detección de reuso revoca la familia (tabla `revoked_token_family`) y el siguiente refresco
  devuelve 401. `JWT_ISSUER` y `JWT_AUDIENCE` son distintos por entorno (`medisage-qa` y
  `medisage-prod`), de modo que un token de QA no valida contra prod.
- **Autorización**: RBAC con `RequirePermission("CODE")` como dependencia en cada endpoint que
  lo requiere. Los permisos se siembran en el arranque (ver sección 4).
- **Secretos**: todos en Secret Manager en la nube; el contenedor los recibe como variables de
  entorno o los resuelve por SDK. Validadores de arranque rechazan un `SECRET_KEY` débil
  (menor a 32 caracteres) o por defecto, un `CORS_ORIGINS` con comodín junto a cookies, y
  exigen los secretos compartidos de bot y de tableros fuera de `dev`.
- **Cabeceras de seguridad HTTP**: se aplican en el frontend (Vercel, `vercel.json`):
  `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`,
  `Strict-Transport-Security`, `Permissions-Policy` y una Content-Security-Policy que habilita
  `connect-src` hacia Firebase y Firestore para el tiempo real.
- **Logging**: JSON estructurado con `X-Request-ID` por request. Prohibido `print()`.

### 2.7 Decisiones de arquitectura (ADR)

Las decisiones técnicas no obvias están en `docs/decisions/` (ADR-001 a ADR-015). Las más
relevantes para operación: ADR-001 (despliegue multi-entorno por ramas), ADR-005 (persistencia
híbrida Cloud SQL mas Firestore), ADR-010 (resolución de secretos en runtime), ADR-011 (stream
de mensajes en Firestore con CQRS), ADR-012 (despacho del bot por Cloud Tasks), ADR-015
(tableros con agregación materializada).

---

## 3. Guía de instalación y entorno local

Detalle por sistema operativo en `docs/SETUP.md`.

### 3.1 Prerrequisitos

- Docker Desktop (para Postgres y el backend).
- Node.js 20 o superior y npm (para el frontend).
- Python 3.11 (solo si se corre el backend fuera de Docker; el rango soportado es 3.11 a 3.12).

### 3.2 Opción A: todo con Docker (recomendada)

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local

docker compose up -d        # levanta Postgres y el backend
cd frontend && npm install && npm run dev
```

`docker-compose.yml` define dos servicios: `db` (postgres:16-alpine, usuario y contraseña
`postgres`, base `bold_template`, puerto 5432, con healthcheck) y `backend` (construido desde
`backend/Dockerfile`, puerto 8080, con hot reload y variables de desarrollo ya inyectadas). El
contenedor del backend corre, al arrancar, `alembic upgrade head` mas el seed mas uvicorn con
reload. El frontend no está dockerizado: corre aparte con `npm run dev` (Turbopack).

Resultado:

- API en `http://localhost:8080` (Swagger en `/docs`, ReDoc en `/redoc`, disponibles porque en
  local `DEBUG=True`).
- Aplicación en `http://localhost:3000`.
- Credenciales iniciales: `admin@example.com` / `ChangeMe123!` (configurables con
  `SEED_ADMIN_EMAIL` y `SEED_ADMIN_PASSWORD` en `backend/.env` antes del primer arranque).

### 3.3 Opción B: backend nativo (sin Docker)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate           # PowerShell en Windows
pip install -e ".[dev]"
cp .env.example .env

# Postgres debe estar corriendo (Cloud SQL Proxy, instalación local, docker run, etc.)
alembic upgrade head
python -m app.core.seed
fastapi dev                       # uvicorn con reload
```

### 3.4 Variables de entorno

Toda la configuración pasa por la clase `Settings` de `backend/app/core/config.py` (no hay
lecturas de entorno dispersas). En `dev` los validadores no exigen secretos, así que el mínimo
efectivo es la conexión a Postgres, un `SECRET_KEY` cualquiera y `CORS_ORIGINS`. En QA y prod
todo lo sensible llega desde Secret Manager (ver sección 6).

Variables principales (lista completa y valores por defecto en `backend/.env.example` y en
`config.py`):

| Variable | Para qué sirve | Secreto |
|---|---|---|
| `ENV_NAME` | Entorno (`dev`, `qa`, `prod`); activa los validadores estrictos | No |
| `DEBUG` | Publica `/docs` y `/redoc` | No |
| `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_HOST`, `DB_PORT` | Conexión a PostgreSQL | La contraseña sí |
| `USE_UNIX_SOCKET`, `CLOUD_SQL_INSTANCE` | Conmutan a unix socket de Cloud SQL en Cloud Run | No |
| `SECRET_KEY` | Firma de los JWT (mínimo 32 caracteres fuera de `dev`) | Sí |
| `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS` | Vida de los tokens | No |
| `JWT_ISSUER`, `JWT_AUDIENCE` | Claims `iss` y `aud`, distintos por entorno | No |
| `CORS_ORIGINS` | Orígenes permitidos (el comodín está prohibido con cookies) | No |
| `LOGIN_RATE_LIMIT`, `AUTH_BURST_RATE_LIMIT`, `RATE_LIMIT_TRUST_FORWARDED` | Rate limiting | No |
| `SEED_ADMIN_EMAIL`, `SEED_ADMIN_PASSWORD` | Usuario administrador inicial | La contraseña sí |
| `GCP_PROJECT_ID`, `FIRESTORE_DATABASE` | Firestore y Secret Manager (read-model de conversaciones) | No |
| `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_APP_SECRET`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_GRAPH_API_VERSION` | Integración con WhatsApp (en prod por cuenta vía Secret Manager) | Sí (token y app secret) |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `BOT_DEFAULT_MODEL` | Proveedores de modelo del bot (por defecto `gpt-4.1-mini`) | Las claves sí |
| `BOT_TIMEZONE`, `MAX_TOOL_ITERATIONS_PER_TURN` | Zona horaria de negocio y tope de iteraciones de herramientas por turno | No |
| `CLOUD_TASKS_QUEUE`, `CLOUD_TASKS_LOCATION`, `SERVICE_BASE_URL`, `BOT_DISPATCH_SECRET` | Despacho asíncrono del bot por Cloud Tasks | El secreto de despacho sí |
| `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `MICROSOFT_OAUTH_*`, `CALENDAR_OAUTH_REDIRECT_BASE` | Integración de calendario externo (OAuth) | Los secretos sí |
| `DASHBOARD_REFRESH_ENABLED`, `DASHBOARD_REFRESH_SECRET`, `DASHBOARD_REFRESH_INTERVAL_MINUTES`, `DASHBOARD_REFRESH_WINDOW_DAYS` | Refresco del rollup de tableros por Cloud Scheduler | El secreto sí |

En el frontend, la variable clave es `BACKEND_URL` (solo servidor, sin prefijo
`NEXT_PUBLIC_`): la URL de Cloud Run que el servidor de Next usa para llamar a FastAPI. Otras:
`NEXT_PUBLIC_APP_URL`, `AUTH_COOKIE_SECURE`, `AUTH_COOKIE_DOMAIN` y la configuración pública
`NEXT_PUBLIC_FIREBASE_*` (no son secretos).

### 3.5 Siembra inicial (seed)

`python -m app.core.seed` es idempotente y corre dentro de una transacción. Crea: los permisos
canónicos de todos los módulos, cuatro roles (`ADMIN` con todos los permisos, `DOCTOR`,
`ASESOR`, `SYSTEM` sin permisos), el usuario administrador inicial (`SEED_ADMIN_EMAIL`), un
usuario técnico `SYSTEM` no autenticable (actor de las operaciones automáticas), los catálogos
de estado (lead, cliente, cita) con sus matrices de transición, y el catálogo de herramientas
del bot. El seed se ejecuta en cada arranque del contenedor (ver sección 4).

---

## 4. Datos y migraciones

### 4.1 Modelo de datos

El modelo tiene 56 tablas (47 entidades ORM y 9 tablas de asociación) repartidas en los once
módulos. Los diagramas entidad-relación y de clases por módulo están en `docs/diagrams/`
(archivos `er-<modulo>.puml` y `class-backend-<modulo>.puml`, renderizables con
`java -jar tools/plantuml.jar -tsvg -o out docs/diagrams/*.puml`).

Convenciones de datos: las fechas se guardan como `timestamptz` (UTC en disco) y viajan en ISO
8601 con offset. La eliminación lógica usa `deleted_at` (filtrada por defecto en todas las
lecturas). El campo `active` es un toggle de negocio distinto de la eliminación lógica.

### 4.2 Migraciones (Alembic)

La cadena de migraciones es lineal, de `0001_initial_admin` a `0026_dashboard_metric`
(**26 migraciones**), en `backend/alembic/versions/`. La URL de conexión no está en
`alembic.ini` (queda vacía a propósito): `backend/alembic/env.py` la inyecta desde `Settings`,
importando antes `app.modules` para registrar todos los modelos.

Comandos:

```bash
alembic revision --autogenerate -m "describir el cambio"   # crear (revisar SIEMPRE el script)
alembic upgrade head                                        # aplicar todas
alembic downgrade -1                                        # revertir una
alembic history                                             # historial
```

El autogenerado no detecta cambios de tipo de columna ni renombrados (los ve como
eliminar mas crear), por lo que el script generado se revisa siempre antes de aplicarlo.

**Las migraciones y el seed corren en el arranque del contenedor.** El `CMD` del Dockerfile es:

```
alembic upgrade head && python -m app.core.seed && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1
```

No hay un paso de migración separado en el pipeline de CI/CD: cuando Cloud Run arranca la nueva
revisión, esta corre la migración antes de empezar a servir. Si la migración falla, Cloud Run
descarta la revisión nueva y mantiene la anterior sirviendo (sin caída, pero el despliegue
queda en rojo). Para migraciones que tarden más de 30 segundos, ver el ítem 3 de la sección 9.

---

## 5. Operación del pipeline de CI/CD

Detalle del flujo de ramas en `docs/BRANCHING.md`. Hay cuatro workflows en
`.github/workflows/`. Las acciones de terceros están fijadas a un SHA completo (defensa de
cadena de suministro) y Dependabot las mantiene al día.

### 5.1 Estrategia de ramas

```
feature/* ──PR──> develop ──PR──> qa ──PR (con aprobación)──> prod
```

| Rama | Rol | Despliegue del backend | Frontend (Vercel) |
|---|---|---|---|
| `develop` | Integración continua | Ninguno (solo CI) | Preview (entorno de desarrollo) |
| `qa` | Preproducción | Automático a `medisage-api-qa` | Preview (entorno QA) |
| `prod` | Producción | Manual con aprobación a `medisage-api` | Production |

Las ramas de feature nunca disparan despliegues. La promoción es por Pull Request entre ramas,
con protección de rama que prohíbe el push directo y el force-push a `qa` y `prod`. Para un
hotfix, se ramifica desde `prod`, se hace PR directo a `prod`, y luego se hace cherry-pick
hacia `qa` y `develop` para que no diverjan.

### 5.2 Workflows

- **`backend-ci.yml`**: en push y pull_request a `develop`, `qa`, `prod` (solo si cambia
  `backend/**`). Corre `ruff check .` y luego
  `pytest --cov=app --cov-report=term-missing --cov-fail-under=80 -q`. El gate de cobertura es
  80 por ciento (la cobertura real ronda el 93 por ciento). No usa ningún secreto.
- **`frontend-ci.yml`**: en push y pull_request a las mismas ramas (solo si cambia
  `frontend/**`). Corre `npm ci`, `npm run lint`, `npm run typecheck` (tsc) y `npm run build`.
  No usa secretos.
- **`deploy-backend-qa.yml`**: en push a `qa` (o ejecución manual). Autentica a Google Cloud
  con Workload Identity Federation (sin llaves), construye y publica la imagen, y despliega a
  Cloud Run QA. Usa el GitHub Environment `qa`.
- **`deploy-backend-prod.yml`**: en push a `prod` (o ejecución manual). Igual que el de QA pero
  con el GitHub Environment `prod`, que debe tener **revisores requeridos** para que el
  despliegue espere aprobación manual.

El despliegue del frontend no pasa por GitHub Actions: lo maneja la integración de git de
Vercel.

### 5.3 Secretos de GitHub

Los workflows de CI no usan secretos. Los de despliegue consumen ocho secretos, guardados **por
GitHub Environment** (`qa` y `prod`), no a nivel de repositorio:

`WIF_PROVIDER`, `DEPLOY_SA`, `GCP_REGION`, `GCP_PROJECT_ID`, `CLOUD_RUN_SERVICE`,
`CLOUD_SQL_INSTANCE`, `CORS_ORIGINS`, `SERVICE_BASE_URL`.

Los compartidos (`GCP_PROJECT_ID`, `GCP_REGION`, `WIF_PROVIDER`, `CLOUD_SQL_INSTANCE`) hay que
duplicarlos en cada Environment porque GitHub no permite herencia. Los valores reales de los
secretos no están en el repositorio (es lo correcto).

---

## 6. Despliegue a Google Cloud

Guía operacional completa en `docs/DEPLOYMENT.md`. Aquí va el resumen consolidado y la mecánica
real de los workflows.

### 6.1 Topología y recursos

Todo vive en el proyecto `proyecto-ifc-497317` (número `87449178744`), región `us-central1`:

- **Cloud Run**: `medisage-api` (prod) y `medisage-api-qa` (qa).
- **Cloud SQL**: una instancia `medisage-db` (PostgreSQL 16) con dos bases, `medisage` (prod) y
  `medisage_qa`, y un usuario de aplicación por entorno.
- **Firestore**: dos bases nombradas, `medisage` y `medisage-qa`.
- **Cloud Tasks**: colas `medisage-bot-turns-qa` y `medisage-bot-turns-prod`.
- **Cloud Scheduler**: un job por entorno que refresca el rollup de tableros.
- **Secret Manager**: los secretos por entorno (sufijo `-qa` o `-prod`).
- **Artifact Registry**: repositorio docker `medisage`.
- **Cuentas de servicio**: `medisage-sa` (prod) y `medisage-sa-qa` (qa), con los roles
  `cloudsql.client`, `secretmanager.secretAccessor` y `cloudtasks.enqueuer`.
- **Workload Identity Federation**: para que GitHub Actions impersone la cuenta de servicio sin
  llaves.

### 6.2 Setup inicial (una sola vez)

El aprovisionamiento es imperativo con `gcloud` (no hay infraestructura como código). La
secuencia completa, lista para copiar, está en `docs/DEPLOYMENT.md` sección 2: habilitar APIs,
crear la instancia y las bases de Cloud SQL, crear el repositorio de Artifact Registry, crear
las cuentas de servicio y sus roles, crear los secretos en Secret Manager, configurar Workload
Identity Federation y crear las colas de Cloud Tasks con su secreto de despacho.

> Pendiente conocido de la documentación de despliegue: el comando para crear el job de
> **Cloud Scheduler** que refresca los tableros no está en `docs/DEPLOYMENT.md`. Conviene
> agregarlo (un `gcloud scheduler jobs create http` que invoque
> `/api/v1/dashboards/internal/refresh` con el header `X-Dashboard-Refresh-Secret`).

### 6.3 Construcción y despliegue del backend

Cada push a `qa` o `prod` (que toque `backend/**`) dispara el workflow de despliegue, que:

1. Autentica con Workload Identity Federation (paso `auth` con `WIF_PROVIDER` y `DEPLOY_SA`).
2. Construye la imagen y la publica en Artifact Registry, etiquetada con el SHA del commit:
   `us-central1-docker.pkg.dev/proyecto-ifc-497317/medisage/<servicio>:<SHA>`.
3. Despliega a Cloud Run con `gcloud run deploy`. Flags comunes a ambos entornos:
   `--platform managed`, `--service-account <DEPLOY_SA>`, `--execution-environment gen2`,
   `--no-cpu-throttling`, `--ingress all`, `--add-cloudsql-instances <instancia>`,
   `--cpu-boost`, `--timeout 60s`, mas el bloque `--set-env-vars` y el bloque `--set-secrets`.

Diferencias entre QA y prod:

| Aspecto | QA | Prod |
|---|---|---|
| Servicio Cloud Run | `medisage-api-qa` | `medisage-api` |
| Cuenta de servicio | `medisage-sa-qa@...` | `medisage-sa@...` |
| Base y usuario | `medisage_qa` / `medisage_app_qa` | `medisage` / `medisage_app` |
| Memoria | 512 MiB | 1 GiB |
| Instancias mínimas y máximas | 0 a 3 | 1 a 10 |
| Cola de Cloud Tasks | `medisage-bot-turns-qa` | `medisage-bot-turns-prod` |
| `JWT_ISSUER` y `JWT_AUDIENCE` | `medisage-qa` | `medisage-prod` |

La instancia de Cloud SQL es la misma para ambos entornos; lo que cambia es la base y el
usuario, que llegan por secreto.

Secretos montados desde Secret Manager con `--set-secrets` (todos con sufijo de entorno y
versión `:latest`): `SECRET_KEY`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`, `BOT_DISPATCH_SECRET`, `GOOGLE_OAUTH_CLIENT_SECRET`,
`DASHBOARD_REFRESH_SECRET`.

### 6.4 Frontend en Vercel

Un solo proyecto de Vercel conectado al repositorio, con Root Directory `frontend` y rama de
producción `prod`. Vercel autodespliega en cada push: la rama `prod` va a Production, `qa` a un
Preview con variables de QA, y el resto a Preview de desarrollo. La variable clave por scope es
`BACKEND_URL`, que apunta al Cloud Run del entorno correspondiente. El backend permite el
origen de Vercel mediante el secreto `CORS_ORIGINS`.

### 6.5 Reglas de Firestore

Las reglas de seguridad (`firestore.rules`) se despliegan con la CLI de Firebase, apuntando el
mismo archivo a las dos bases nombradas:

```bash
firebase deploy --only firestore:rules --project proyecto-ifc-497317
```

`firebase.json` mapea `firestore.rules` a las bases `medisage` y `medisage-qa` (nunca a la
`(default)`).

---

## 7. Respaldo y restauración

Esta sección es el procedimiento de continuidad de datos de medisage. Documenta lo que hay
configurado hoy, lo que se recomienda habilitar, y los pasos de restauración por componente.

> Estado actual resumido: lo único configurado hoy es el **backup automático diario de Cloud
> SQL** (a las 04:00, por el flag `--backup-start-time=04:00` al crear la instancia). No hay
> recuperación a un instante (PITR), ni export de Firestore, ni respaldo de Secret Manager, ni
> infraestructura como código. Los procedimientos de PITR, export y restauración de esta
> sección se deben habilitar y ejecutar por el responsable de operación.

### 7.1 Inventario de datos y criticidad

| Componente | Qué contiene | Reconstruible desde otro lado | Criticidad |
|---|---|---|---|
| Cloud SQL (`medisage`, `medisage_qa`) | Todos los datos operativos (clínicas, citas, leads, bots, campañas, tableros) | No. Es la fuente de verdad | Alta |
| Firestore (`medisage`, `medisage-qa`) | Contenido de los mensajes del inbox (read-model) | Parcial. Solo mientras existan las filas de `message_outbox` en Postgres | Alta |
| Secret Manager | Claves y credenciales por entorno | No (hay que regenerarlas) | Alta |
| Artifact Registry | Imágenes de contenedor por commit | Sí (se reconstruyen desde el código) | Media |
| Cloud Storage | Adjuntos y media (aún no implementado) | No aplica hoy | (futura) |

### 7.2 Cloud SQL: backups, recuperación a un instante, export y restauración

**Backups automáticos (ya configurados).** La instancia se creó con `--backup-start-time=04:00`,
lo que activa el backup automático diario administrado. Conviene fijar explícitamente la
retención:

```bash
gcloud sql instances patch medisage-db \
  --backup-start-time=04:00 \
  --retained-backups-count=14 \
  --project=proyecto-ifc-497317
```

**Recuperación a un instante (PITR), recomendado habilitar.** Hoy no está activa. Habilitarla
permite restaurar a cualquier segundo dentro de la ventana de logs:

```bash
gcloud sql instances patch medisage-db \
  --enable-point-in-time-recovery \
  --retained-transaction-log-days=7 \
  --project=proyecto-ifc-497317
```

**Backup bajo demanda (antes de una migración riesgosa o un release mayor).**

```bash
gcloud sql backups create --instance=medisage-db \
  --description="pre-release vX.Y.Z" --project=proyecto-ifc-497317
```

**Export lógico fuera de la instancia (respaldo off-instance a Cloud Storage).** Útil para
retención larga e independiente de la instancia. Requiere un bucket y dar a la cuenta de
servicio de Cloud SQL permiso de escritura sobre él:

```bash
gcloud sql export sql medisage-db gs://medisage-backups/sql/medisage-$(date +%F).sql.gz \
  --database=medisage --offload --project=proyecto-ifc-497317
```

**Restauración.** Tres modos según el caso:

```bash
# 1) Listar backups disponibles
gcloud sql backups list --instance=medisage-db --project=proyecto-ifc-497317

# 2) Restaurar un backup sobre la MISMA instancia (sobrescribe; coordinar ventana de mantenimiento)
gcloud sql backups restore <BACKUP_ID> \
  --restore-instance=medisage-db --project=proyecto-ifc-497317

# 3) Recuperación a un instante a una instancia NUEVA (no destructivo; recomendado para inspeccionar)
gcloud sql instances clone medisage-db medisage-db-recovery \
  --point-in-time="2026-06-26T03:30:00.000Z" --project=proyecto-ifc-497317

# 4) Restaurar un export lógico
gcloud sql import sql medisage-db gs://medisage-backups/sql/medisage-2026-06-26.sql.gz \
  --database=medisage --project=proyecto-ifc-497317
```

Tras restaurar, la aplicación arranca y vuelve a correr `alembic upgrade head` (idempotente
sobre un esquema ya migrado) y el seed (idempotente). No hace falta ningún paso manual de
esquema.

### 7.3 Firestore: export e import administrados

El contenido de los mensajes vive solo en Firestore, así que su respaldo es tan crítico como el
de Cloud SQL. Se usa el export administrado, por base nombrada, a un bucket de Cloud Storage:

```bash
# Export (programar a diario; una carpeta por fecha)
gcloud firestore export gs://medisage-backups/firestore/prod/$(date +%F) \
  --database=medisage --project=proyecto-ifc-497317

gcloud firestore export gs://medisage-backups/firestore/qa/$(date +%F) \
  --database=medisage-qa --project=proyecto-ifc-497317

# Import (restauración)
gcloud firestore import gs://medisage-backups/firestore/prod/2026-06-26 \
  --database=medisage --project=proyecto-ifc-497317
```

Se recomienda automatizar el export diario con un job de Cloud Scheduler y aplicar una política
de ciclo de vida al bucket para la retención. Como el read-model es reconstruible desde Postgres
mientras exista el `message_outbox`, una estrategia alternativa o complementaria es **conservar
las filas del outbox** el tiempo suficiente para poder reproyectar a Firestore ante una
pérdida.

### 7.4 Secret Manager

Secret Manager versiona cada secreto, pero conviene una política explícita: rotación periódica
de `SECRET_KEY` (ver sección 8) y de las claves de proveedor, y un respaldo seguro de los
valores en un gestor de contraseñas fuera de la nube, dado que un secreto perdido no se puede
recuperar (solo regenerar, lo que invalida lo que dependía de él).

### 7.5 Recreación del entorno desde cero

Como no hay infraestructura como código, recrear un entorno significa:

1. Re-ejecutar la secuencia de `gcloud` de `docs/DEPLOYMENT.md` sección 2 (APIs, Cloud SQL,
   Artifact Registry, cuentas de servicio y roles, Secret Manager, Workload Identity
   Federation, Cloud Tasks) mas el job de Cloud Scheduler.
2. Cargar los valores de los secretos en Secret Manager.
3. Vincular Firebase al proyecto y desplegar `firestore.rules`
   (`firebase deploy --only firestore:rules`).
4. Restaurar los datos: Cloud SQL (sección 7.2) y Firestore (sección 7.3).
5. Hacer un push a la rama del entorno (o `gh workflow run`) para construir y desplegar el
   backend, y conectar Vercel para el frontend.

Se recomienda, como mejora futura, migrar el aprovisionamiento a Terraform para que la
recreación sea declarativa y reproducible.

### 7.6 Objetivos de recuperación recomendados

Valores sugeridos para acordar con el responsable del servicio (hoy no hay política formal):

| Componente | RPO (pérdida máxima) recomendado | RTO (tiempo de recuperación) recomendado | Mecanismo |
|---|---|---|---|
| Cloud SQL | 5 minutos (con PITR) o 24 horas (solo backup diario) | 1 a 2 horas | PITR mas backup diario mas export lógico |
| Firestore | 24 horas | 1 a 2 horas | Export diario administrado |
| Secret Manager | 0 (versionado) | Minutos | Versionado mas copia en gestor externo |
| Aplicación (Cloud Run) | 0 (sin estado) | Minutos | Revisiones e imágenes por commit |

---

## 8. Operación y resolución de problemas

Recetario completo en `docs/DEPLOYMENT.md` secciones 6 y 7.

### 8.1 Operaciones comunes

- **Rotar `SECRET_KEY`** (desloguea a todos los usuarios):
  ```bash
  NEW=$(openssl rand -base64 48 | tr -d '\n')
  echo -n "$NEW" | gcloud secrets versions add medisage-secret-key-prod --data-file=-
  gcloud run services update medisage-api --region=us-central1 \
    --update-secrets="SECRET_KEY=medisage-secret-key-prod:latest"
  ```
- **Forzar logout de todos** sin rotar la llave: `UPDATE token_family SET revoked_at = NOW(), reason = 'mass_logout';`.
- **Rollback de un despliegue** (Cloud Run conserva revisiones):
  ```bash
  gcloud run revisions list --service=medisage-api --region=us-central1
  gcloud run services update-traffic medisage-api --region=us-central1 \
    --to-revisions=medisage-api-00042-xyz=100
  ```
- **Re-despliegue manual**: `gh workflow run deploy-backend-qa.yml --ref qa` (prod requiere
  aprobación).

### 8.2 Observabilidad

Los logs son JSON estructurado con `X-Request-ID` por request. Para seguirlos en vivo o filtrar
por request:

```bash
gcloud run services logs tail medisage-api-qa --region=us-central1
gcloud logging read 'resource.type=cloud_run_revision AND jsonPayload.request_id="abc123"' --limit 50
```

La sonda de salud (`GET /health`) devuelve el estado y el entorno. El pool de base de datos
registra una advertencia cuando hay presión de conexiones.

### 8.3 Problemas frecuentes

- **Falla la conexión a Cloud SQL en Cloud Run**: verificar `USE_UNIX_SOCKET=True`, el flag
  `--add-cloudsql-instances` en el despliegue, y que la cuenta de servicio tenga
  `roles/cloudsql.client`.
- **El bot no responde solo**: la cola de Cloud Tasks debe existir y `BOT_DISPATCH_SECRET` debe
  estar configurado; si la cola no está, el despacho es un no-op silencioso (el webhook
  responde 200 pero el bot no contesta).
- **La migración falla y la revisión no arranca**: Cloud Run mantiene la revisión anterior
  sirviendo. Revisar los logs de la revisión nueva.
- **El despliegue a prod queda en "Waiting for review"**: espera a un revisor del GitHub
  Environment `prod` (correcto en producción).

---

## 9. Hardening de preproducción

`docs/HARDENING.md` lista cinco puntos que la plataforma base no resuelve sola. Estado real
verificado contra el código:

1. **Rate limit distribuido**: hoy slowapi es en memoria por instancia. Con varias instancias el
   límite efectivo se multiplica. Si `max-instances` es mayor que 3, mover el almacenamiento a
   Redis (Memorystore o Upstash). Pendiente.
2. **Pool de base de datos frente a la concurrencia de Cloud Run**: el pool es de 10 conexiones
   por instancia y la concurrencia por instancia es 80. Ajustar antes de la primera prueba de
   carga (subir `pool_size`, bajar `--concurrency` o usar PgBouncer). Pendiente.
3. **Migraciones como Cloud Run Job**: hoy corren en el arranque del contenedor. Si una
   migración tarda más de 30 segundos o hay `min-instances` mayor que 1, moverla a un Cloud Run
   Job separado del arranque. Pendiente.
4. **Flags de seguridad de Cloud Run**: `--service-account`, `--execution-environment gen2` e
   `--ingress all` **ya están aplicados** en ambos workflows de despliegue (este punto del
   checklist ya está resuelto). El servicio queda con `--ingress all` (público) de forma
   intencional, porque debe recibir el webhook de WhatsApp y las llamadas del servidor de Vercel.
5. **Argon2id en vez de bcrypt**: si las credenciales se consideran de alto valor, cambiar el
   esquema de hash. Pendiente, decisión de negocio.

---

## 10. Referencias

Documentos del repositorio:

- `docs/ARCHITECTURE.md`: vista narrativa de capas, módulos y contratos.
- `docs/SETUP.md`: instalación local detallada.
- `docs/DEPLOYMENT.md`: despliegue a Google Cloud, secretos y CI/CD (guía operacional completa).
- `docs/BRANCHING.md`: estrategia de ramas y protecciones.
- `docs/HARDENING.md`: checklist de preproducción.
- `docs/PERMISSIONS.md`: modelo RBAC y cómo agregar permisos.
- `docs/diagrams/`: diagramas entidad-relación y de clases por módulo (PlantUML).
- `docs/decisions/`: registros de decisión de arquitectura (ADR-001 a ADR-015).
- `README.md`, `CLAUDE.md`, `backend/CLAUDE.md`, `frontend/CLAUDE.md`: convenciones del código.

Recursos de Google Cloud y operación:

- Proyecto: `proyecto-ifc-497317` (número `87449178744`), región `us-central1`.
- Backend (Cloud Run): `medisage-api` (prod), `medisage-api-qa` (qa).
- Base de datos (Cloud SQL): instancia `medisage-db`, bases `medisage` y `medisage_qa`.
- Frontend (Vercel): un proyecto, rama de producción `prod`.
