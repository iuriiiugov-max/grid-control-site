# CRYPTO CONTROL

Single-repository architecture for the CRYPTO project.

## Repository zones

- `public/` — public web/OAuth-facing files only.
- `backend/` — internal application code.
- `config/` — non-secret machine configuration.
- `schemas/` — manifest/runtime schemas.
- `migrations/` — database migrations.
- `tests/` — automated validation.
- `deploy/` — deployment definitions.
- `ops/` — operational runbooks and health/reconciliation tooling.
- `docs/` — human-readable technical documentation.

## Safety baseline

- READ_ONLY
- AUTO_EXECUTION_OFF
- No seed phrases or wallet private keys.
- No exchange trade/withdraw/transfer credentials.
- No secrets committed to Git.
- Existing working CRYPTO contour remains active during shadow migration.
