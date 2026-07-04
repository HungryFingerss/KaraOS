# karaos-dashboard/ — the local web dashboard

A Next.js 14 dashboard for operating KaraOS: see who's enrolled, live status, enroll/delete people, audit the face gallery, factory-reset. It reads the same `faces/` data the pipeline writes (via `lib/db.ts`) and talks to the pipeline through `faces/state.json`.

## Run
```bash
cd karaos-dashboard
npm install
npm run dev     # http://localhost:3000  (production: npm run build && npm start)
```
Both scripts go through `scripts/launch.js`, which **binds 127.0.0.1 by default**. Binding to a LAN/all-interfaces address requires BOTH `DASHBOARD_BIND` and the explicit second opt-in `DASHBOARD_BIND_ALLOW_ANY=1` (argv-injection-checked) — a deliberate double gate, tripwire-tested.

## Auth (how you get in)
The pipeline mints a random token at boot (`faces/.dashboard_token`, chmod/ACL-restricted) and prints a one-time auth URL. Visiting `/api/auth?token=...` sets the `karaos_session` cookie (httpOnly, SameSite=strict, timing-safe compare). **Every other `/api/*` route requires that cookie** via `lib/requireAuth.ts` (Node-runtime helper called at the top of each handler — a CI test asserts every route is guarded), plus a post-auth rate limit (60 req/min sliding window). Factory reset preserves the token by design (no re-auth after reset).

## API routes (`app/api/`)
`status` · `people` + `people/[id]` (list/delete) · `photo` · `enroll` · `gallery-audit` + `gallery-audit/[id]` (outlier embedding audit) · `shadow-persons` · `best-friend` · `factory-reset` · `auth` (the only ungated route — it mints the cookie).

## Pages (`app/`)
`/` (live status), `/people`, `/enroll`.

Known limitation: browser enrollment via `/enroll` conflicts with the pipeline holding the camera — enroll while the pipeline is stopped, or use `python enroll.py`. The Python-side auth/bind/token invariants are tested across the `tests/test_dashboard_*.py` files.
