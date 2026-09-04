# Phase 4 — Admin Token Setup Check

Env var name confirmed **exact and consistent** across all 4 places it's referenced:

- `render.yaml:24` — `key: RIDEBASE_ADMIN_TOKEN`, `sync: false` (must be set manually in Render dashboard, not templated into the blueprint)
- `backend/app/config.py:72` — `RIDEBASE_ADMIN_TOKEN: str = os.environ.get("RIDEBASE_ADMIN_TOKEN", "")`
- `backend/app/routes.py:45-46` — fail-closed: empty/unset token means `_require_admin_token` always rejects (`secrets.compare_digest` against an empty string never matches)
- `backend/.env.example:24` — documented for local dev (`RIDEBASE_ADMIN_TOKEN=`, blank)

No `render` CLI and no `RENDER_API_KEY`/`RENDER_*` env var available in this
environment — cannot set the Render env var programmatically. Per the
mission's rules, a token was **not** generated, printed, or committed here.

## Manual action required

```
Render Dashboard
→ ridebase-inference-api
→ Environment
→ Add Environment Variable
    Key:   RIDEBASE_ADMIN_TOKEN
    Value: <a strong random secret, e.g. `openssl rand -hex 32`>
→ Save
```

Until this is set, `POST /admin/reload` stays fail-closed (401) even with a
correctly-formed `Authorization: Bearer <token>` header — which is the safe
default, not a bug.
