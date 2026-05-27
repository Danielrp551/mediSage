# ADR-001: Multi-environment deployment via branch-driven workflows

## Status

Accepted

## Date

2026-05-27

## Context

El proyecto necesita al menos **QA** y **Production** como entornos
desplegados, además de **dev local**. Las decisiones que tomar:

1. **Cuántos entornos** y cuántos proyectos GCP.
2. **Cómo se mapea código → entorno** (branches, tags, manual dispatch).
3. **Dónde viven los secrets** y cómo se gatean para que un colaborador
   junior no pueda romper producción por accidente.
4. **Cuántas instancias de Cloud SQL** y cómo se nombra cada DB.
5. **Cómo se setea Vercel** para el frontend.

Constraints conocidos del contexto:

- Equipo pequeño (~3–8 personas), no hay SRE dedicado.
- Presupuesto GCP acotado — minimizar instancias paralelas pesa más que
  isolation perfecto entre envs.
- KAM Digital ya estableció una convención que el equipo reconoce (3
  ramas `develop / qa / prod`).
- Hay deploys frecuentes a QA (varios por día durante features) y poco
  frecuentes a prod (~semanal). El gate principal debe estar entre QA
  y prod, no entre develop y qa.

## Decision

Adoptamos **branch-driven multi-environment deploys** con la estructura:

```
develop  → CI sólo (tests + lint). Sin deploy.
qa       → CI + deploy automático a Cloud Run `medisage-api-qa`.
prod     → CI + deploy a Cloud Run `medisage-api`, gated con required reviewer.
```

**Infra layout:**

- **1 proyecto GCP**, compartido entre todos los envs (`proyecto-ifc-497317`).
- **1 instancia Cloud SQL** (`medisage-db`) con 2 databases: `medisage_qa`,
  `medisage` (esta última es prod — heredada del primer deploy). Dev usa
  Postgres local vía docker-compose por default.
- **2 Cloud Run services**: `medisage-api-qa` y `medisage-api` (prod). Sin
  service para dev.
- **2 service accounts** distintos (least-privilege por env):
  `medisage-sa-qa` y `medisage-sa` (prod).

**Secrets:**

- **GitHub Environments** (`qa`, `prod`) con sus propios secrets — no a
  nivel repo. Un colaborador con acceso de PR a `qa` no puede leer
  secrets de `prod`.
- **GCP Secret Manager** para datos sensibles (`SECRET_KEY`,
  `DB_PASSWORD`, etc.), con sufijo de env en el nombre del secret
  (`medisage-secret-key-qa`, `...-prod`). El workflow los monta vía
  `--set-secrets`.
- **GitHub Environment secrets** para config no-sensible que cambia
  por env (`CORS_ORIGINS`, `CLOUD_RUN_SERVICE` name, `DEPLOY_SA`).

**JWT issuer/audience distintos por env** (`medisage-qa` vs
`medisage-prod`) — un token leaked en QA no se valida en prod
aunque se filtre `SECRET_KEY`.

**Frontend (Vercel):** un único proyecto Vercel conectado al repo,
con env vars **scopeadas por branch** en la UI de Vercel:
- `prod` → Production env vars
- `qa` → Preview env vars con override específico para esta branch

## Alternatives Considered

### Mirror exacto de KAM Digital (secrets a nivel repo)

KAM guarda `SECRET_KEY_QA` y `SECRET_KEY_PROD` directo en GitHub
Secrets del repo, sin usar Environments.

- Pros: familiar para el equipo; un solo lugar para administrar
  secrets.
- Cons: no hay audit log por env; cualquier maintainer puede leer
  prod desde Settings → Secrets; no hay gate de review para prod;
  un workflow con bug puede usar secrets del env incorrecto.
- **Rechazado** porque el costo de upgrade es marginal (configurar 2
  Environments en GitHub) y el upside (review gate, audit) es alto.

### Un proyecto GCP por entorno (qa-project, prod-project)

- Pros: isolation máximo — billing, IAM, quotas y blast radius
  separados.
- Cons: 3× overhead administrativo; cuotas iniciales pequeñas por
  proyecto pueden molestar; cambio de costo significativo para equipos
  pequeños.
- **Rechazado** porque KAM Digital opera bien con un solo proyecto
  durante 1+ año, y la complejidad extra no se justifica para este
  tamaño de equipo.

### Tag-driven deploys (push `v1.2.3` para deploy a prod)

- Pros: versionado explícito; deploys desacoplados del branching.
- Cons: fricción operacional (push de tag por cada release); raro en
  equipos chicos; KAM no lo usa así que rompe la convención.
- **Rechazado** por consistencia con KAM y simplicidad.

### Workflow `workflow_dispatch` con input `environment`

- Pros: lo más simple de configurar; sin asumir branching.
- Cons: cada deploy requiere clic manual; sin trazabilidad de "qué
  commit está en qué env" sin convención adicional.
- **Rechazado** como modo principal, pero **conservado como fallback**
  (`workflow_dispatch:` en ambos workflows) para re-deploys manuales
  cuando se necesite.

### Dos proyectos Vercel separados (mirror KAM)

KAM tiene `qa-frontend-kam-digital-bold.vercel.app` y
`frontend-kam-digital-bold.vercel.app` como **proyectos distintos** en
Vercel.

- Pros: isolation total; Vercel project settings (analytics, domains,
  team) independientes.
- Cons: el doble de clicks para mantener; env vars hay que actualizar
  en 2 lugares; PR previews requieren decidir contra qué proyecto se
  buildea.
- **Rechazado** para la plantilla. El upgrade a 2 proyectos siempre
  está disponible; bajar de 2 a 1 es más doloroso.

### Migraciones como Cloud Run Job (en vez de CMD del container)

Documentado en [HARDENING.md #3](../HARDENING.md). No se aplica en
este ADR para evitar scope creep; se aplicará cuando haya una
migración que pase los 30 s.

## Consequences

**Operacionales:**

- Cada PR a `qa` o `prod` requiere CI verde antes del merge (branch
  protection configurable).
- Deploys a `qa` corren en ~3–5 min sin intervención. Deploys a `prod`
  esperan aprobación de un reviewer del Environment `prod`.
- Hotfix workflow: rama desde `prod` → PR a `prod`. Después del deploy,
  cherry-pick a `qa` y `develop`.
- El `develop` branch sirve como "staging interno" — el equipo puede
  hacer PRs ahí libremente sin riesgo de afectar QA todavía.

**Seguridad:**

- Required reviewer en `prod` bloquea deploys accidentales. Combinado
  con `concurrency: cancel-in-progress: false` evita que un push
  posterior aborte un deploy en marcha.
- JWT `iss`/`aud` por env: un access token leaked en QA da 401 si se
  presenta a prod (el `decode_token` valida ambos claims —
  [security.py](../../backend/app/core/security.py)).
- Service accounts distintos por env limitan el blast radius de un
  potencial compromiso del SA de qa.

**Costos:**

- Mismo número de Cloud SQL instances que single-env (una).
- 1 Cloud Run service adicional con `min-instances=0` para qa
  → ~$0 cuando QA está idle; pico controlado por `max-instances`.
- Sin costo extra de proyectos GCP.

**Mantenimiento:**

- Hay que mantener 3 ramas vivas (mismo costo que KAM Digital).
- Cada env tiene secrets que rotar — documentado en
  [DEPLOYMENT.md](../DEPLOYMENT.md) cómo hacerlo.
- Cambios en deploy config requieren modificar 2 workflows (qa + prod)
  o el step compartido. Aceptable por la claridad explícita que da.

**Riesgo conocido:**

- Si alguien hace `git push origin --force` a `prod`, el workflow
  corre con la nueva HEAD. Branch protection con "no force push" es
  obligatorio. Documentado en [BRANCHING.md](../BRANCHING.md).
- Las migraciones siguen en el container `CMD`. Si una migración se
  pasa de 4 min, el deploy a prod falla y bloquea releases. Mitigación
  en [HARDENING.md #3](../HARDENING.md) cuando aplique.

**Nota de naming heredado del primer deploy:**

El servicio prod se llama `medisage-api` (sin sufijo `-prod`) porque
fue el primer deploy del proyecto, antes de adoptar esta política
multi-env. La SA prod (`medisage-sa`) sigue el mismo patrón. Mantener
esos nombres es preferible a hacer un rename forzoso (Cloud Run y SA
no se pueden renombrar — habría que crear desde cero, mover tráfico,
y eliminar el viejo, con riesgo para datos en BD que apuntan al SA).
La inconsistencia se documenta acá y vive con nosotros.
