# Deployment

Guía operacional para configurar y mantener los entornos **QA** y **Production**.
Decisión arquitectónica en [ADR-001](decisions/ADR-001-multi-env-branching.md).
Branching workflow en [BRANCHING.md](BRANCHING.md).

## Tabla de contenidos

1. [Topología](#1-topología)
2. [Setup inicial GCP (una sola vez)](#2-setup-inicial-gcp-una-sola-vez)
3. [Setup GitHub (Environments + Secrets)](#3-setup-github-environments--secrets)
4. [Setup Vercel (frontend)](#4-setup-vercel-frontend)
5. [Deploy normal](#5-deploy-normal)
6. [Operaciones comunes](#6-operaciones-comunes)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. Topología

```
                    ┌──────────────────────────────────────┐
                    │   GCP project: proyecto-ifc-497317   │
                    │                                       │
   develop ────────►│  Cloud SQL: medisage-db              │
   (CI only)        │  ├─ medisage_qa                      │
                    │  └─ medisage         (prod)          │
   qa ─────────────►│                                       │
   (auto deploy)    │  Cloud Run: medisage-api-qa          │
                    │  Cloud Run: medisage-api  (prod)     │
   prod ───────────►│                                       │
   (gated deploy)   │  Secret Manager:                     │
                    │  ├─ medisage-secret-key-qa           │
                    │  ├─ medisage-secret-key-prod         │
                    │  ├─ medisage-db-password-qa          │
                    │  ├─ medisage-db-password-prod        │
                    │  └─ ... (4 secrets × 2 envs = 8)     │
                    └──────────────────────────────────────┘

Vercel (1 project)
├─ Production env vars  ← branch `prod`
├─ Preview env vars     ← otras ramas (override específico para `qa`)
└─ git integration → auto-deploy en cada push
```

**Naming heredado:** el service prod se llama `medisage-api` (no `medisage-api-prod`)
y la SA prod `medisage-sa` (no `medisage-sa-prod`) porque fueron creados antes de
adoptar la política multi-env. Documentado en [ADR-001](decisions/ADR-001-multi-env-branching.md#consequences).

---

## 2. Setup inicial GCP (una sola vez)

> Si vas a reproducir todo desde cero. El proyecto medisage actual ya está
> setupeado parcialmente — los pasos que aún faltan están listados al final.

### 2.1 Enable APIs

```bash
export PROJECT_ID=proyecto-ifc-497317
export REGION=us-central1

gcloud config set project $PROJECT_ID

gcloud services enable \
  sqladmin.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  sts.googleapis.com \
  cloudbuild.googleapis.com \
  --quiet
```

### 2.2 Cloud SQL — una instancia, dos databases

```bash
gcloud sql instances create medisage-db \
  --database-version=POSTGRES_16 \
  --region=$REGION \
  --tier=db-f1-micro \
  --edition=ENTERPRISE \
  --storage-size=10GB \
  --storage-type=SSD \
  --backup-start-time=04:00 \
  --quiet

# Databases por env
gcloud sql databases create medisage    --instance=medisage-db --quiet   # prod
gcloud sql databases create medisage_qa --instance=medisage-db --quiet

# Usuarios por env (cada uno conecta sólo con su password)
for ENV_SUFFIX in "" "_qa"; do
  PASS=$(openssl rand -base64 32)
  USER="medisage_app${ENV_SUFFIX}"
  gcloud sql users create "$USER" \
    --instance=medisage-db --password="$PASS" --quiet
  echo "$USER password: $PASS  (guardar en password manager)"
done
```

### 2.3 Artifact Registry para las imágenes Docker

```bash
gcloud artifacts repositories create medisage \
  --repository-format=docker \
  --location=$REGION \
  --description="Medisage backend images" \
  --quiet
```

### 2.4 Service accounts (uno por env)

Principio de least-privilege — cada SA accede sólo a su Cloud Run +
secrets de ese env.

```bash
# Prod (sin sufijo, naming heredado)
gcloud iam service-accounts create medisage-sa \
  --display-name "Medisage Cloud Run SA (prod)" --quiet

# QA
gcloud iam service-accounts create medisage-sa-qa \
  --display-name "Medisage Cloud Run SA (qa)" --quiet

for SA in "medisage-sa" "medisage-sa-qa"; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/cloudsql.client" --quiet

  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor" --quiet
done
```

### 2.5 Secret Manager — secrets por env

```bash
for ENV in qa prod; do
  # SECRET_KEY del JWT (rotar cada N meses)
  openssl rand -base64 48 | tr -d '\n' | \
    gcloud secrets create "medisage-secret-key-${ENV}" --data-file=- --quiet

  # DB user (medisage_app o medisage_app_qa)
  USER_VALUE="medisage_app"
  [ "$ENV" = "qa" ] && USER_VALUE="medisage_app_qa"
  echo -n "$USER_VALUE" | \
    gcloud secrets create "medisage-db-user-${ENV}" --data-file=- --quiet

  # DB password — usá la password que generaste en 2.2 para ese usuario
  read -sp "Password de ${USER_VALUE} (de paso 2.2): " DB_PASS
  echo
  echo -n "$DB_PASS" | \
    gcloud secrets create "medisage-db-password-${ENV}" --data-file=- --quiet

  # DB name (medisage o medisage_qa)
  DB_NAME="medisage"
  [ "$ENV" = "qa" ] && DB_NAME="medisage_qa"
  echo -n "$DB_NAME" | \
    gcloud secrets create "medisage-db-name-${ENV}" --data-file=- --quiet
done
```

### 2.6 Workload Identity Federation (para GitHub Actions sin keys)

```bash
gcloud iam workload-identity-pools create github \
  --location=global --display-name="GitHub" --quiet

POOL_ID=$(gcloud iam workload-identity-pools describe github \
  --location=global --format="value(name)")

gcloud iam workload-identity-pools providers create-oidc github \
  --workload-identity-pool=github --location=global \
  --display-name="GitHub OIDC" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
  --attribute-condition="assertion.repository == 'TU-ORG/medisage'" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --quiet

# Permitir a cada SA ser impersonado desde el repo de GitHub
for SA in "medisage-sa" "medisage-sa-qa"; do
  gcloud iam service-accounts add-iam-policy-binding \
    "${SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/iam.workloadIdentityUser" \
    --member="principalSet://iam.googleapis.com/${POOL_ID}/attribute.repository/TU-ORG/medisage" \
    --quiet
done

PROVIDER=$(gcloud iam workload-identity-pools providers describe github \
  --workload-identity-pool=github --location=global \
  --format="value(name)")
echo "WIF_PROVIDER (a guardar en GitHub secrets):"
echo "  $PROVIDER"
```

### 2.7 Cloud Tasks — auto-dispatch del bot (módulo `bots`, ADR-012)

El módulo `bots` despacha el turno del LLM de forma asíncrona vía **Cloud Tasks**: el webhook de
WhatsApp encola una task que hace `POST /api/v1/bots/engine/dispatch`. Si NO se configura, el auto-path
hace **NO-OP silencioso** (el webhook responde 200 pero el bot no contesta) — por eso los 4 valores de
runtime + la cola + el IAM son obligatorios para que el bot responda solo. Provisionar **antes** del
deploy que active la cola.

```bash
# 1) Cola por env (reintentos generosos para absorber la carrera commit→dispatch).
for ENV in qa prod; do
  gcloud tasks queues create "medisage-bot-turns-${ENV}" \
    --location="$REGION" --project="$PROJECT_ID" \
    --max-attempts=10 --max-concurrent-dispatches=10 \
    --max-dispatches-per-second=5 --min-backoff=5s --max-backoff=300s
done

# 2) Secret del dispatch por env (256-bit; el endpoint lo compara en tiempo constante).
for ENV in qa prod; do
  printf %s "$(python -c 'import secrets;print(secrets.token_urlsafe(48))')" \
    | gcloud secrets create "medisage-bot-dispatch-secret-${ENV}" --data-file=- --project="$PROJECT_ID"
done

# 3) La SA runtime de cada servicio debe poder ENCOLAR (roles/cloudtasks.enqueuer).
#    (Opción shared-secret: NO se necesita actAs/serviceAccountUser ni run.invoker — eso sería OIDC.)
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:medisage-sa-qa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/cloudtasks.enqueuer"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:medisage-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/cloudtasks.enqueuer"
```

Los workflows de deploy ya inyectan (ver `deploy-backend-{qa,prod}.yml`):
`--set-env-vars` += `CLOUD_TASKS_QUEUE=medisage-bot-turns-${ENV_NAME}`, `CLOUD_TASKS_LOCATION` (= región),
`SERVICE_BASE_URL`; `--set-secrets` += `BOT_DISPATCH_SECRET=medisage-bot-dispatch-secret-${ENV_NAME}:latest`.
`SERVICE_BASE_URL` se guarda como **GitHub Environment secret** por env (la URL pública del Cloud Run,
**sin** trailing slash — usar `gcloud run services describe <svc> --format='value(status.url)'`).

⚠ Orden crítico: crear el secret **antes** del deploy. Con `CLOUD_TASKS_QUEUE` seteado, el boot-validator
exige un `BOT_DISPATCH_SECRET` real (≥32 chars) o el contenedor no arranca.

---

## 3. Setup GitHub (Environments + Secrets)

### 3.1 Crear los Environments

GitHub → Settings → Environments → **New environment**:

1. **`qa`** — sin protection rules. Cualquier push a `qa` deploya solo.
2. **`prod`** — agregar **Required reviewers** (Settings del Environment):
   - Marcar "Required reviewers" → agregar al equipo de leads.
   - Marcar "Deployment branches" → only protected branches (=`prod`).

### 3.2 Secrets por Environment

Para **cada Environment** (`qa` y `prod`), agregar estos secrets:

| Secret name | Valor en `qa` | Valor en `prod` |
|---|---|---|
| `GCP_PROJECT_ID` | `proyecto-ifc-497317` | `proyecto-ifc-497317` |
| `GCP_REGION` | `us-central1` | `us-central1` |
| `WIF_PROVIDER` | `projects/87449178744/locations/global/workloadIdentityPools/github/providers/github` | (igual) |
| `DEPLOY_SA` | `medisage-sa-qa@proyecto-ifc-497317.iam.gserviceaccount.com` | `medisage-sa@proyecto-ifc-497317.iam.gserviceaccount.com` |
| `CLOUD_RUN_SERVICE` | `medisage-api-qa` | `medisage-api` |
| `CLOUD_SQL_INSTANCE` | `proyecto-ifc-497317:us-central1:medisage-db` | (igual) |
| `CORS_ORIGINS` | `https://medisage-git-qa-tuorg.vercel.app` | `https://medisage.vercel.app` (o el dominio prod) |
| `SERVICE_BASE_URL` | `https://medisage-api-qa-87449178744.us-central1.run.app` | `https://medisage-api-87449178744.us-central1.run.app` |

> **Nota:** los secrets compartidos (`GCP_PROJECT_ID`, `GCP_REGION`, `WIF_PROVIDER`,
> `CLOUD_SQL_INSTANCE`) hay que duplicarlos en cada Environment porque GitHub
> Environments no permite herencia.

---

## 4. Setup Vercel (frontend)

**Una sola Vercel project**, conectada al repo de GitHub.

### 4.1 Importar el proyecto

1. https://vercel.com/new → **Import Git Repository** → seleccionar el repo.
2. **Configure project:**
   - Root Directory: `frontend`
   - Framework Preset: Next.js (auto-detecta)
   - Build/Output: defaults (lee `vercel.json`)
3. **Production Branch:** `prod` (Settings → Git → Production Branch).

### 4.2 Environment Variables

Settings → Environment Variables → New. Vercel maneja 3 scopes:
**Production**, **Preview**, **Development**.

| Variable | Production scope (branch `prod`) | Preview scope (default) | Preview scope (branch=`qa` override) |
|---|---|---|---|
| `BACKEND_URL` | `https://medisage-api-87449178744.us-central1.run.app` | `https://medisage-api-qa-87449178744.us-central1.run.app` | `https://medisage-api-qa-87449178744.us-central1.run.app` |
| `NEXT_PUBLIC_APP_URL` | dominio prod | *(vacío — Vercel autogenera)* | *(idem)* |
| `AUTH_COOKIE_SECURE` | `true` | `true` | `true` |
| `AUTH_COOKIE_DOMAIN` | `.medisage.com` *(opcional)* | *(vacío)* | *(vacío)* |

Para el **branch-specific override**: en cada env var, hacé clic en "Edit",
desplegá **"Apply to specific Git branches"**, y agregá `qa`.

Resultado:
- Push a `prod` → Vercel Production env vars → URL principal.
- Push a `qa` → Preview con override de `qa` → URL `medisage-git-qa-tuorg.vercel.app`.
- Push a `develop` o feature → Preview default (apunta al backend de QA).

### 4.3 CORS en el backend

El backend de cada env permite el origin del Vercel correspondiente vía el
secret `CORS_ORIGINS` (paso 3.2). Asegurate que apunte a:

- env `qa`: `https://medisage-git-qa-tuorg.vercel.app` (o tu dominio QA custom)
- env `prod`: dominio principal (e.g. `https://medisage.com`)

---

## 5. Deploy normal

```bash
# Trabajar en develop (deploys frontend a preview, sin backend deploy)
git checkout -b feature/x develop
# … trabajo …
gh pr create --base develop --head feature/x

# Promover a QA
gh pr create --base qa --head develop
# Después del merge: backend deploy automático a medisage-api-qa + Vercel preview qa

# Release a prod
gh pr create --base prod --head qa
# Después del merge:
#   - GitHub Actions queda en "Waiting for review" en el job de prod
#   - Un reviewer del Environment prod aprueba → deploy procede
#   - Vercel deploya frontend a Production
```

Ver [BRANCHING.md](BRANCHING.md) para el flujo detallado.

---

## 6. Operaciones comunes

### Rotar `SECRET_KEY` (JWT signing key)

```bash
NEW_SECRET=$(openssl rand -base64 48 | tr -d '\n')

echo -n "$NEW_SECRET" | gcloud secrets versions add \
  "medisage-secret-key-prod" --data-file=-

gcloud run services update medisage-api --region=$REGION \
  --update-secrets="SECRET_KEY=medisage-secret-key-prod:latest"
```

⚠️ Todos los usuarios serán deslogueados (sus tokens dejan de validar).
Documentar la ventana de mantenimiento si es prod.

### Forzar logout de todos los usuarios (sin rotar SECRET_KEY)

```sql
-- Conectarse a la DB de prod y revocar todas las families
UPDATE token_family SET revoked_at = NOW(), reason = 'mass_logout';
```

### Re-deploy manual sin cambios de código

```bash
gh workflow run deploy-backend-qa.yml --ref qa
gh workflow run deploy-backend-prod.yml --ref prod   # requiere aprobación
```

### Rollback de un deploy

Cloud Run mantiene revisiones. Para volver a la anterior:

```bash
gcloud run revisions list --service=medisage-api --region=$REGION
gcloud run services update-traffic medisage-api \
  --region=$REGION \
  --to-revisions=medisage-api-00042-xyz=100
```

### Ver logs en vivo

```bash
gcloud run services logs tail medisage-api-qa --region=$REGION
# Filtros por request_id (gracias al middleware):
gcloud logging read 'resource.type=cloud_run_revision AND jsonPayload.request_id="abc123"' --limit 50
```

---

## 7. Troubleshooting

### "PERMISSION_DENIED: ... iam.serviceAccounts.getAccessToken"

WIF mal configurado. Verificá:

```bash
gcloud iam service-accounts get-iam-policy "$SA" --format=json
# Debe tener el principalSet del WIF pool con role workloadIdentityUser.
```

### "Cloud SQL connection failed" en Cloud Run

- `USE_UNIX_SOCKET=True` debe estar en env vars.
- `--add-cloudsql-instances` debe estar en el deploy command.
- El SA del Cloud Run debe tener `roles/cloudsql.client`.

### Deploy "Waiting for review" no se aprueba solo

Está esperando un reviewer humano (correcto en prod). Si nadie del
equipo aparece como reviewer disponible, revisar Settings → Environments
→ prod → Required reviewers.

### Migración falla y el container no arranca

El `CMD` corre `alembic upgrade head && seed && uvicorn`. Si la migración
falla, Cloud Run mata la nueva revisión y deja la anterior sirviendo —
no hay downtime pero el deploy queda rojo. Para investigar:

```bash
gcloud run revisions logs read medisage-api-qa-00050-xyz --region=$REGION
```

Cuando una migración tarde más de 30s, ver [HARDENING.md #3](HARDENING.md)
para mover migraciones a Cloud Run Jobs.

### Token leaked en QA sigue funcionando contra prod

No debería — `JWT_AUDIENCE` y `JWT_ISSUER` son distintos por env
(`medisage-qa` vs `medisage-prod`) y se validan en `decode_token`. Si
no falla, verificá que las env vars estén bien seteadas:

```bash
gcloud run services describe medisage-api --region=$REGION \
  --format='value(spec.template.spec.containers[0].env[].name,spec.template.spec.containers[0].env[].value)' \
  | grep JWT_
```
