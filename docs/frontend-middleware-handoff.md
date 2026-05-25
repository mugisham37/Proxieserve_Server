# Frontend Middleware Handoff

This document describes the `web/` middleware behavior the frontend team should add later. It is documentation only; `web/` remains untouched in this backend build.

## Goal
Move protected-route enforcement from client-side checks in `DashboardShell` to server-verified middleware backed by the secure cookies issued by `server/`.

## Expected Cookies
- `proxiserve_access`
- `proxiserve_refresh`

Both are issued as HTTP-only cookies by the backend auth router.

## Proposed `web/middleware.ts` Behavior

### Protected paths
Treat these routes as protected:
- `/dashboard`
- `/dashboard/:path*`

### Public auth paths
Allow unauthenticated access to:
- `/login`
- `/signup`
- `/verify`
- `/forgot-password`
- `/reset-password`
- `/claim`
- `/staff/login`
- `/staff/2fa`

### Middleware algorithm
1. Intercept requests to `/dashboard` and `/dashboard/:path*`.
2. Read the auth cookies from the request.
3. If there is no `proxiserve_access` cookie, redirect to `/login?next=<current-path>`.
4. If there is an access cookie, call `GET /api/auth/session` with credentials included.
5. If the session endpoint returns success:
   - allow the request through
   - let the browser accept any refreshed cookies returned by the backend
6. If the session endpoint returns unauthorized:
   - redirect to `/login?next=<current-path>`

## Why the Session Endpoint Matters
`GET /api/auth/session` already handles:
- validating the current access token
- silent refresh when the access token is near expiry and a valid refresh token exists
- returning the frontend-compatible `AuthSession` payload plus `expiresAt`

That lets middleware stay thin and keeps refresh logic centralized in the backend.

## Suggested Redirect Rules
- unauthenticated dashboard access -> `/login?next=/dashboard`
- expired/invalid dashboard access -> `/login?next=<requested-path>`
- optionally redirect authenticated users away from `/login` and `/signup` to `/dashboard`

## Frontend Follow-Up
When the frontend is ready to use the server session fully, it should also:
- stop treating `localStorage` as the primary security source
- use `/api/auth/session` as the source of truth for protected pages
- keep `localStorage` only as a temporary compatibility layer or remove it entirely
