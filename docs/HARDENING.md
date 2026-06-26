# Hardening checklist

La plantilla viene **safe-by-default** para desarrollo y staging. Los cinco
puntos de abajo son optimizaciones que **dependen de infra real** (Redis,
Cloud Run Jobs, métricas del workload) o de decisiones específicas del
producto que la plantilla no puede anticipar. Revísalos antes del primer
deploy productivo.

| # | Tema | Esfuerzo | Cuándo importa |
|---|---|---|---|
| 1 | Rate limiting distribuido (Redis) | 1–2 h | `max-instances > 1` y el rate-limit es defensa real (no UX) |
| 2 | Pool de DB + concurrency de Cloud Run | 30 min + medir | Antes del primer load test productivo |
| 3 | Migraciones como Cloud Run Job | 2 h | Cuando una migración pueda durar > 30 s o haya > 1 instancia activa |
| 4 | Cloud Run deploy flags (SA, execution-env, ingress) | Resuelto | Ya aplicado en `deploy-backend-{qa,prod}.yml` |
| 5 | Argon2id en lugar de bcrypt | 30 min | Credenciales de alto valor (financial/health) |

---

## 1. Rate limiting distribuido con Redis

### Estado actual

`slowapi` está configurado con storage en memoria (default). Cada
instancia de Cloud Run tiene su propio bucket — los límites no se
comparten entre instancias.

Ver: [`app/core/rate_limit.py`](../backend/app/core/rate_limit.py),
[`routers/auth.py`](../backend/app/modules/admin/routers/auth.py).

### Por qué importa

Con `--max-instances=10` (prod) y `LOGIN_RATE_LIMIT="5/minute"`, el techo real
contra credential-stuffing es `5 × 10 = 50 intentos/minuto` por IP
(si las requests caen en instancias distintas, lo cual es lo normal con
un LB round-robin). Para un atacante con botnet, el rate limit deja de
ser defensa y pasa a ser teatro.

Con Redis compartido, las 10 instancias comparten un bucket único → el
limit es realmente `5/minute` global por IP.

### Cómo aplicarlo

**Paso 1.** Provisionar Redis. Opciones:

- **Upstash Redis** (recomendado para empezar) — HTTP/REST API, sin
  VPC connector, free tier generoso. URL es del estilo
  `rediss://default:<token>@<region>.upstash.io:6379`.
- **Memorystore for Redis** — mismo VPC que Cloud Run (más latencia
  baja pero requiere VPC Connector, ~$25/mes extra).

**Paso 2.** Agregar setting:

```python
# backend/app/core/config.py
class Settings(BaseSettings):
    ...
    REDIS_URL: str = ""  # vacío → fallback in-memory
```

**Paso 3.** Pasar el storage a slowapi:

```python
# backend/app/core/rate_limit.py
from app.core.config import get_settings

settings = get_settings()

limiter = Limiter(
    key_func=_client_ip,
    storage_uri=settings.REDIS_URL or "memory://",
)
```

**Paso 4.** En `deploy-backend-prod.yml`, montar el secret:

```yaml
--set-secrets "...,REDIS_URL=redis-url:latest"
```

**Paso 5.** Validar — un script con `httpx` que hace 10 requests
concurrentes a `/auth/login` desde la misma IP debe recibir 5×200 +
5×429 incluso si Cloud Run los reparte entre instancias.

### Costo / cuándo postergar

- **Upstash:** ~$0 para tráfico bajo, $0.20 por 100k commands más allá
  del free tier.
- **Memorystore:** mínimo $25/mes + VPC Connector ~$10/mes.
- **Postergable cuando:** tienes `min-instances=max-instances=1`
  (entonces el bucket en memoria es global porque hay una sola instancia).

---

## 2. Pool de DB + concurrency de Cloud Run

### Estado actual

```python
# backend/app/core/database.py
pool_size=5,
max_overflow=5,         # → pool efectivo 10 conexiones por instancia
pool_timeout=10,
pool_recycle=300,
```

```yaml
# .github/workflows/deploy-backend-prod.yml (qa: min 0 / max 3)
--concurrency 80
--min-instances 1
--max-instances 10
```

### Por qué importa

Dos problemas a la vez:

**a. Mismatch pool vs concurrency:** una instancia puede atender 80
requests concurrentes pero solo tiene 10 conexiones a la BD. El request
81 espera hasta `pool_timeout=10s` y luego revienta con
`TimeoutError: QueuePool limit ... reached`. En FastAPI async + queries
DB, la práctica común es **bajar concurrency** porque cada request casi
siempre ocupa una conexión durante la mayor parte de su vida.

**b. Saturación de Cloud SQL:** Cloud SQL Postgres `db-f1-micro` (tier
de desarrollo, $7/mes) tope ~**25 conexiones totales**. Con
`pool_size + max_overflow = 10` y `max-instances=10` (prod) el peak es
`10 × 10 = 100 conexiones`, 4× el límite. Postgres rechaza los excedentes
y los logs se llenan de `FATAL: remaining connection slots are reserved`.

### Cómo aplicarlo

**Regla de oro:**

```
pool_size × max_instances  ≤  cloud_sql_max_connections × 0.8
```

Reserva 20% para conexiones administrativas / migraciones.

Casos típicos:

| Cloud SQL tier | Max conn | max-instances | pool_size sugerido | concurrency |
|---|---|---|---|---|
| `db-f1-micro` | 25 | 1–3 | 5 | 20 |
| `db-g1-small` | 50 | 5 | 8 | 25 |
| `db-custom-2-7680` | 100 | 10 | 8 | 30 |
| `db-custom-4-15360` | 200 | 20 | 8 | 40 |

**Paso 1.** Pick concurrency y pool según el tier. Para empezar
(workload desconocido) con `db-g1-small`:

```python
# backend/app/core/database.py
engine = create_async_engine(
    settings.database_url,
    ...
    pool_size=8,
    max_overflow=4,    # picos cortos
    pool_timeout=5,    # falla rápido en vez de colgar
    pool_recycle=300,
    pool_pre_ping=True,
)
```

```yaml
# .github/workflows/deploy-backend-prod.yml
--concurrency 25
--max-instances 5
```

**Paso 2.** Medir. Usa `wrk` o `k6` con tráfico realista y observa:

- p95 de latencia de endpoints DB-heavy
- `pool.pressure` warnings en logs (ya está instrumentado en
  [`database.py:_log_pool_pressure`](../backend/app/core/database.py))
- Conexiones activas en Cloud SQL: query `SELECT count(*) FROM pg_stat_activity`

**Paso 3.** Iterar — si ves contención de pool: subir `pool_size` (y
tier de Cloud SQL si toca). Si ves CPU al 100% sin saturar pool: subir
concurrency o `--cpu`.

### Costo / cuándo postergar

- **Postergable hasta:** el primer load test productivo. Con tráfico
  bajo (< 10 req/s sostenidos), los defaults pasan sin problema.
- **No postergar si:** vas a deployar con `max-instances > 5` y un
  `db-f1-micro` — vas a explotar la primera vez que escale.

---

## 3. Migraciones como Cloud Run Job

### Estado actual

El [`Dockerfile`](../backend/Dockerfile) ejecuta migraciones + seed en
el `CMD` antes de arrancar uvicorn:

```dockerfile
CMD ["sh", "-c", "alembic upgrade head && python -m app.core.seed && exec uvicorn ..."]
```

### Por qué importa

Tres problemas que escalan con la app:

1. **Timeout de startup (4 min).** Cloud Run mata el container si no
   bindea `$PORT` en 240 s. Una migración con backfill, índice grande, o
   `ALTER TABLE` pesado puede pasarse — el deploy falla.

2. **Race entre instancias.** Si Cloud Run escala 5 instancias durante
   el deploy, las 5 corren `alembic upgrade head` simultáneamente.
   Alembic usa `alembic_version` para serializar, pero las 4 que
   pierden el race esperan hasta el timeout. UX degradado durante el
   roll-out.

3. **Seed defensivo.** [`seed.py`](../backend/app/core/seed.py) es
   idempotente con `ON CONFLICT DO NOTHING`, pero corre en cada cold
   start — desperdicia ciclos y mete logs ruidosos.

### Cómo aplicarlo

**Paso 1.** Sacar migraciones + seed del `CMD`:

```dockerfile
# backend/Dockerfile
# ANTES: CMD ["sh", "-c", "alembic upgrade head && python -m app.core.seed && exec uvicorn ..."]
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
```

**Paso 2.** Crear un script de entrypoint para el Job:

```bash
# backend/scripts/migrate.sh
#!/usr/bin/env sh
set -e
echo "Running migrations..."
alembic upgrade head
echo "Seeding..."
python -m app.core.seed
echo "Done."
```

**Paso 3.** Cambio en el workflow de deploy:

```yaml
# .github/workflows/deploy-backend-prod.yml
- name: Run migrations job
  run: |
    gcloud run jobs deploy migrate \
      --image "$IMAGE" \
      --region "$REGION" \
      --add-cloudsql-instances "$CLOUD_SQL_INSTANCE" \
      --set-env-vars "USE_UNIX_SOCKET=True,CLOUD_SQL_INSTANCE=$CLOUD_SQL_INSTANCE,ENV_NAME=prod" \
      --set-secrets "SECRET_KEY=app-secret-key:latest,DB_USER=db-user:latest,DB_PASSWORD=db-password:latest,DB_NAME=db-name:latest" \
      --command "sh,/app/scripts/migrate.sh" \
      --max-retries 0 \
      --task-timeout 600s \
      --service-account cloud-run-backend@$PROJECT_ID.iam.gserviceaccount.com

    gcloud run jobs execute migrate --wait --region "$REGION"

- name: Deploy service
  run: |
    gcloud run deploy "$SERVICE" \
      ...
```

`--wait` bloquea hasta que el Job complete; si falla, el step explota y
**el deploy del service no corre**. Bueno: jamás booteas un service
contra un schema inconsistente.

**Paso 4 (opcional).** Para migraciones que deben ejecutarse **antes**
de que la nueva versión del código pueda correr (típico: agregas una
column NOT NULL), combinar con backwards-compatible migrations en dos
pasos (la app vieja debe poder correr con el schema nuevo).

### Costo / cuándo postergar

- **Esfuerzo:** ~2 h la primera vez (script, workflow, validar).
- **Costo runtime:** Cloud Run Jobs cobra por segundo de ejecución; una
  migración típica de < 30 s cuesta fracciones de centavo.
- **Postergable hasta:** la primera migración que tarda > 30 s o el
  primer deploy con `min-instances > 1`. Para una plantilla con admin
  base y un sprint inicial, el `CMD` funciona.

---

## 4. Cloud Run deploy flags (resuelto)

### Estado actual

Ambos workflows de deploy (`deploy-backend-qa.yml` y `deploy-backend-prod.yml`)
ya fijan de forma explícita la cuenta de servicio, el entorno de ejecución y el
ingress. Comando real de producción (resumido):

```yaml
# .github/workflows/deploy-backend-prod.yml
gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --platform managed \
  --service-account "$DEPLOY_SA" \          # medisage-sa (prod) / medisage-sa-qa (qa)
  --execution-environment gen2 \
  --no-cpu-throttling \
  --ingress all \
  --add-cloudsql-instances "$CLOUD_SQL_INSTANCE" \
  --set-env-vars "..." \
  --set-secrets "..." \
  --memory 1Gi \                            # qa: 512Mi
  --cpu 1 \
  --min-instances 1 \                       # qa: 0
  --max-instances 10 \                      # qa: 3
  --concurrency 80 \
  --cpu-boost \
  --timeout 60s
```

### Por qué importa

Tres flags que el deploy fija de forma explícita, porque sus defaults son
variables (Google los cambia sin previo aviso) o inseguros:

**`--service-account`**: sin este flag, el service correría como la
**Compute Engine default service account**, que tiene roles muy amplios sobre
el proyecto (Editor por default). Aquí cada entorno usa su SA dedicada
(`medisage-sa` en prod, `medisage-sa-qa` en qa) con permisos mínimos
(`roles/cloudsql.client`, `roles/secretmanager.secretAccessor`,
`roles/cloudtasks.enqueuer`).

**`--execution-environment gen2`**: fija el sandbox (gVisor de gen2) y evita
cambios sorpresa entre gen1 y gen2.

**`--ingress all`**: el service es público de forma intencional, porque debe
recibir el webhook de WhatsApp y las llamadas del servidor de Vercel. El
endurecimiento real vive en las otras capas: CORS, rate limit, autenticación y
el secreto compartido del dispatch del bot.

### Cómo se configuró

La cuenta de servicio por entorno se creó con permisos mínimos (ver
`docs/DEPLOYMENT.md` sección 2.4):

```bash
gcloud iam service-accounts create medisage-sa \
  --display-name "Medisage Cloud Run SA (prod)"
gcloud iam service-accounts create medisage-sa-qa \
  --display-name "Medisage Cloud Run SA (qa)"

# Roles mínimos por SA (prod como ejemplo)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:medisage-sa@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:medisage-sa@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/cloudsql.client"
```

Los flags ya están en el paso `Deploy to Cloud Run` de ambos workflows; el SA de
cada entorno llega por el secreto de GitHub `DEPLOY_SA`.

### Estado

**Resuelto.** No hay acción pendiente. Mejora opcional a futuro: con una red
privada, fijar `--use-http2`, `--vpc-connector` y `--vpc-egress`.

---

## 5. Argon2id en lugar de bcrypt

### Estado actual

```python
# backend/app/core/security.py
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
```

Dependencia: `passlib[bcrypt]`.

### Por qué importa

**bcrypt sigue siendo seguro criptográficamente** — no hay break
conocido. La diferencia con Argon2id está en la resistencia a ataques
con hardware moderno:

| | bcrypt | Argon2id |
|---|---|---|
| GPU resistance | Media | Alta (memory-hard) |
| ASIC resistance | Baja | Alta |
| Memory cost configurable | No | Sí |
| OWASP 2024 recomendación | Acceptable | **Primary** |
| Side-channel resistance | Baja | Alta (id variant) |
| Maintained | passlib en modo mantenimiento | argon2-cffi activo |

Para una app interna de admin con tráfico bajo, bcrypt aguanta. Para
credenciales de alto valor (financial, health, retail con tarjetas), el
costo de migrar a Argon2id es muy bajo comparado con el upside.

### Cómo aplicarlo (con upgrade transparente, sin invalidar contraseñas existentes)

**Paso 1.** Agregar Argon2id manteniendo bcrypt como fallback:

```python
# backend/pyproject.toml
"passlib[argon2,bcrypt]>=1.7.4",   # antes: "passlib[bcrypt]>=1.7.4"
```

**Paso 2.** Configurar `CryptContext` con ambos schemes:

```python
# backend/app/core/security.py
_pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    deprecated="auto",                     # bcrypt queda marcado como deprecated
    argon2__memory_cost=65536,             # 64 MiB por hash (OWASP 2024)
    argon2__time_cost=3,                    # 3 iteraciones
    argon2__parallelism=4,                  # 4 threads
)
```

Con `deprecated="auto"`: hashes existentes de bcrypt se **verifican
normalmente**, pero `pwd_context.needs_update(hash)` retorna `True`
para ellos.

**Paso 3.** Auto-upgrade en login. Modificar
[`services/auth.py:login`](../backend/app/modules/admin/services/auth.py):

```python
async def login(db: AsyncSession, *, email: str, password: str) -> LoginResponse:
    user = await user_repository.get_by_email(db, email)
    if user is None or not verify_password(password, user.password_hash):
        raise UnauthorizedException("Invalid credentials")
    if not user.active:
        raise UnauthorizedException("User is disabled")

    # Transparent upgrade: re-hash bcrypt → argon2 on first successful login.
    if _pwd_context.needs_update(user.password_hash):
        user.password_hash = hash_password(password)
        await db.flush()

    pair, family_id, jti = _issue_tokens(user)
    ...
```

Habría que exponer `_pwd_context` o agregar un helper
`needs_password_rehash` en `security.py`.

**Paso 4.** Verificar que el costo en memoria es asumible:

- `memory_cost=65536` (64 MiB) × `concurrency=80` ≈ **5 GiB peak** durante
  un login storm. Memory Cloud Run default es 512 MiB → OOM kill.
- Para concurrency=80, baja `memory_cost` a `16384` (16 MiB) o **sube
  `--memory` a 1 GiB**. Recomendado: subir memoria + medir.

### Costo / cuándo postergar

- **Esfuerzo:** 30 min (3 cambios, sin migración de datos — los hashes
  se actualizan sólo cuando el usuario hace login otra vez).
- **Costo runtime:** ~30–100 ms extra por login (intencional). Memoria:
  ajustar `memory_cost` × concurrency vs `--memory`.
- **Postergable cuando:** el perfil de credenciales es bajo-medio
  riesgo (app interna, admin tools) y el sprint inicial no toca auth.
- **No postergar si:** la app guardará credenciales con alto valor de
  reventa (financial / health / tarjetas) o vas a publicar para
  consumidores externos.

---

## Checklist final pre-prod

Recomendación de orden de aplicación cuando tengas la infra:

- [x] **#4 — Deploy flags** (resuelto: ya aplicado en ambos workflows)
- [ ] **#2 — Pool/concurrency** (30 min + medir, si vas a load-testear)
- [ ] **#3 — Migraciones como Job** (2 h, antes de la primera migración pesada)
- [ ] **#1 — Redis para rate limit** (1–2 h, cuando `max-instances > 3` y rate-limit es defensa real)
- [ ] **#5 — Argon2id** (30 min, evaluar contra el perfil de credenciales)

Los items 1, 3, y 5 escalan con el tamaño del producto. El item 2 es
**disciplina de bootstrap** (vale la pena resolverlo antes de la primera demo
seria). El item 4 ya está resuelto.
