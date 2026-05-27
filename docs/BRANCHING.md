# Branching strategy

Convención para esta plantilla. Decisión completa en
[ADR-001](decisions/ADR-001-multi-env-branching.md).

## Las tres ramas

```
develop   ←──   feature branches
   │
   │   PR (review + CI verde)
   ▼
   qa     ──→   deploy automático a medisage-api-qa.run.app
   │
   │   PR + manual approval (required reviewer en GitHub Environment `prod`)
   ▼
  prod    ──→   deploy a medisage-api.run.app
```

| Rama | Rol | Deploy backend | Frontend (Vercel) |
|---|---|---|---|
| `develop` | Integración continua del trabajo del equipo | — (sólo CI) | Preview con env vars de dev |
| `qa` | Pre-producción para QA / acceptance testing | Auto a Cloud Run `medisage-api-qa` | Preview con env vars de qa |
| `prod` | Producción | Manual (gated) a Cloud Run `medisage-api` | Production |

Feature branches (`feature/...`, `fix/...`, etc.) nunca disparan deploys.
Sus PRs al destino (`develop` típicamente) corren CI.

## Flujo normal

```bash
# 1. Trabajo en una feature branch
git checkout develop
git pull
git checkout -b feature/users-bulk-import
# … commits …
git push -u origin feature/users-bulk-import
# → abrir PR a `develop`. Esperar review + CI verde. Merge.

# 2. Cuando develop está listo para QA
git checkout develop && git pull
gh pr create --base qa --head develop --title "Promote develop → qa"
# → CI corre. Mergeas. El push a qa dispara deploy-backend-qa.yml.

# 3. Cuando QA aprueba la versión
gh pr create --base prod --head qa --title "Release vX.Y.Z to prod"
# → CI corre. Mergeas. El push a prod dispara deploy-backend-prod.yml.
# El workflow se pausa esperando aprobación del Environment `prod`.
# El reviewer aprueba en la UI de Actions → el deploy procede.
```

## Hotfix flow

Si hay un bug crítico en producción:

```bash
# 1. Rama desde prod
git checkout prod && git pull
git checkout -b hotfix/critical-auth-bug
# … fix + tests …
git push -u origin hotfix/critical-auth-bug

# 2. PR directo a prod (sin pasar por develop/qa)
gh pr create --base prod --head hotfix/critical-auth-bug

# 3. Después del merge a prod (y deploy aprobado),
#    cherry-pick hacia atrás para que qa y develop no diverjan:
git checkout qa && git pull
git cherry-pick <commit-sha-del-hotfix>
git push

git checkout develop && git pull
git cherry-pick <commit-sha-del-hotfix>
git push
```

## Branch protection rules

Configurar en GitHub Settings → Branches:

### `prod`
- ✅ Require a pull request before merging
- ✅ Require approvals: 1 (mínimo)
- ✅ Require status checks: `backend-ci`, `frontend-ci`
- ✅ Require branches to be up to date before merging
- ✅ Do not allow bypassing the above settings
- ✅ Restrict who can push to matching branches (sólo maintainers)
- ✅ **Do not allow force pushes**
- ✅ Do not allow deletions

### `qa`
- ✅ Require a pull request before merging
- ✅ Require status checks: `backend-ci`, `frontend-ci`
- ✅ Do not allow force pushes
- ⚠️ Approvals opcional — el equipo decide

### `develop`
- ✅ Require status checks: `backend-ci`, `frontend-ci`
- ✅ Do not allow force pushes
- ⚠️ PR no es obligatorio (algunos equipos permiten push directo
  para iteración rápida)

## Conventional commits (recomendado, no obligatorio)

```
feat(users): add bulk import endpoint
fix(auth): handle expired refresh tokens in middleware
docs: update deployment guide
chore(deps): bump fastapi to 0.118
```

Facilita changelogs automáticos y filtros en `git log`.

## Preguntas frecuentes

**¿Puedo pushear directo a `qa` o `prod` saltándome el PR?**
No. La branch protection lo impide. Si lo conseguís, está rota la
configuración — repórtalo.

**¿Qué pasa si el deploy a `qa` falla?**
El job en Actions queda rojo. Cloud Run mantiene la revisión anterior
sirviendo tráfico (rolling deploy). Investigá el log, fixeás, push
nuevo a `qa`, el siguiente deploy intenta otra vez. No hay rollback
manual necesario.

**¿Cómo veo qué commit está corriendo en cada env?**
GitHub Settings → Environments → `qa` / `prod` muestra el último
deployment con el SHA. También `gcloud run services describe
medisage-api-qa --format='value(spec.template.metadata.labels.commit)'`
si el workflow inyecta esa label (extensión futura).

**¿Cuándo creo `feature/something` vs trabajar en `develop`?**
- Feature branch: cambio de >1 día o que pasa CI con dudas.
- Direct push a `develop`: si tu equipo lo permite (ver branch
  protection), para fixes triviales y typo fixes.

**Frontend ¿también pasa por `develop`/`qa`/`prod`?**
Sí, pero Vercel maneja los deploys automáticamente:
- `prod` branch → Production (URL principal)
- `qa` branch → Preview con env vars de QA
- `develop` branch → Preview con env vars de dev (suele apuntar al
  mismo backend que QA)
- Feature branches → Preview con env vars de dev
