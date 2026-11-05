# SolarDoctor auth API

Axalon's opaque session-token auth, exposed in the shape the cloned SolarPulseAI frontend uses.
All paths work with and without the `/api/v1` prefix; the canonical form is `/api/v1/auth/...`.
Active only when `SOLARDOCTOR_AUTH_MODE=users` (in `off`/`apikey` modes every endpoint below except
`/auth/mode`, `/auth/me` and `/auth/logout` answers 404; behaviour of those modes is unchanged).

Tokens are 256-bit random strings; only their SHA-256 is stored (`user_sessions`). Refresh tokens live in the
same table under a domain-separated hash (`sha256("refresh:" + token)`), so no schema change was needed and a
refresh token can never authenticate a request. Send the access token as `Authorization: Bearer <token>`.

## Endpoints

| Method + path | Auth | Request | Success |
|---|---|---|---|
| `GET /auth/mode` | public | - | `{"mode": "off"\|"apikey"\|"users"}` |
| `POST /auth/register` | public | JSON `{email, password, username?, full_name?}` (`username`/`full_name` accepted, ignored) | 201 user object (role always `viewer`, no project access) |
| `POST /auth/login` | public | JSON `{email, password}` | 200 token body |
| `POST /auth/token` | public | `application/x-www-form-urlencoded` `username` (= email), `password` (what the SolarPulse `LoginForm` posts) | 200 token body |
| `POST /auth/refresh` | public | JSON `{refresh_token}` | 200 token body (rotated) |
| `POST /auth/logout` | public, idempotent | optional JSON `{refresh_token}`; optional Bearer | 204 |
| `GET /auth/me` | Bearer | - | `{mode, kind, role, project_ids, user}` |

Token body (login, token, refresh):

```json
{
  "token": "...", "access_token": "...", "refresh_token": "...", "token_type": "bearer",
  "expires_at": "2026-11-05T12:00:00", "expires_in": 43200, "refresh_expires_at": "2026-11-12T00:00:00",
  "user": {"id": 1, "email": "a@b.c", "role": "operator", "disabled": false, "project_ids": [], "created_at": "..."}
}
```

`token`/`expires_at`/`user` are the original Axalon keys; `access_token`/`refresh_token`/`token_type` are what
the SolarPulse client reads.

Errors: 400 validation (email format, password 10-256 chars), 401 bad credentials / bad or used refresh token,
403 registration disabled, 404 not in users mode, 409 duplicate email, 429 rate limited (`Retry-After`).
Error bodies are `{"detail": "..."}`.

## Behaviour

- **Refresh rotation:** a refresh token is single use; `/auth/refresh` deletes it and issues a new access +
  refresh pair. Replaying a used token gives 401. Expired tokens and tokens of disabled users give 401.
- **Logout:** revokes the Bearer session and, if `refresh_token` is in the body, that refresh token. The access
  session and its refresh token are not linked server-side, so clients **must send `refresh_token` on logout**;
  otherwise the refresh token stays valid until it expires. Disabling a user, changing their password or
  deleting them revokes everything.
- **Rate limits (in-memory, per process):** login/token: 5 failures per email and 20 per IP per 15 min;
  register: 10 attempts per IP per 15 min.
- **Password:** minimum 10 characters (SolarPulse's client-side minimum of 8 must be raised to 10).

## Env vars

| Var | Default | Meaning |
|---|---|---|
| `SOLARDOCTOR_AUTH_MODE` | `off` (or `apikey` if `SOLARDOCTOR_API_KEY` set) | `off`, `apikey`, `users` |
| `SOLARDOCTOR_SESSION_TTL_HOURS` | 12 | access token lifetime (0.25 - 720) |
| `SOLARDOCTOR_REFRESH_TTL_DAYS` | 7 | refresh token lifetime (1 - 90) |
| `SOLARDOCTOR_ALLOW_REGISTRATION` | 1 | set `0` to close self-service signup |
| `SOLARDOCTOR_BOOTSTRAP_ADMIN_EMAIL` / `_PASSWORD` | unset | first admin when the users table is empty |

## Roles

Rank: `viewer` < `technician` < `operator` < `admin`.

| Role | Can do |
|---|---|
| admin | everything, incl. `/users` management; no project restriction |
| operator | read + write project data inside assigned projects |
| technician | read like a viewer inside assigned projects (HTTP writes are 403); `GET /parks/{id}/work-orders` is narrowed to faults whose `assignee` equals the technician's email (case-insensitive; the `assignee` query filter cannot widen it) |
| viewer | read-only inside assigned projects (self-registered users have none, so they see nothing until an admin assigns projects) |

Admins create technicians via `POST /users` with `"role": "technician"` and set `assignee` on faults to the
technician's email.
