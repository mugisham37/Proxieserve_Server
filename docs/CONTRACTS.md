# ProxiServe Frontend Auth Contracts

This document captures the authentication contracts implemented in `web/` and should be treated as the backend-facing source of truth for the initial `server/` build.

## Source Order
1. Live frontend code in `web/`
2. Frontend auth analysis provided with the project brief
3. Backend master build prompt

## Canonical Frontend Files
- `web/lib/auth-types.ts`
- `web/lib/auth-context.tsx`
- `web/lib/auth-schema.ts`
- `web/components/organisms/ClientLoginForm.tsx`
- `web/components/organisms/ClientSignupForm.tsx`
- `web/components/organisms/VerifyOTPForm.tsx`
- `web/components/organisms/ForgotPasswordForm.tsx`
- `web/components/organisms/ResetPasswordForm.tsx`
- `web/components/organisms/ClaimByCodeForm.tsx`
- `web/components/organisms/StaffLoginForm.tsx`
- `web/components/organisms/TwoFAChallengeForm.tsx`
- `web/components/organisms/DashboardShell.tsx`

## Route Surface

### Auth pages
- `/login`
- `/signup`
- `/verify`
- `/forgot-password`
- `/reset-password`
- `/claim`
- `/staff/login`
- `/staff/2fa`

### Protected dashboard pages
- `/dashboard`
- `/dashboard/applications`
- `/dashboard/applications/[code]`
- `/dashboard/documents`
- `/dashboard/messages`
- `/dashboard/settings`

### Route protection
- `web/app/(auth)/layout.tsx` and `web/app/(dashboard)/layout.tsx` only mount `AuthProvider`.
- Real protection is currently client-side in `web/components/organisms/DashboardShell.tsx`.
- There is no `web/middleware.ts` yet.

## Query Parameters Used by the Frontend
- `/verify?next=...&email=...`
  - `next` drives the success redirect after OTP verification.
  - `email` is display-only and is a masked string.
- `/verify?device=new`
  - toggles the device warning card.
  - no current frontend code sets this param.
- `/reset-password?token=...`
  - token is read outside the reset form schema.
- `/login?reset=success`
  - shows the reset success banner.
- `/login?claimed=1`
  - shows the claim success banner.
- `/claim?code=PRX-YYYY-NNNNN`
  - pre-fills the claim form.

## Canonical Types

### AuthRole
```ts
"client" | "staff:agent" | "staff:admin"
```

### AuthLanguage
```ts
"en" | "rw" | "fr"
```

### AuthErrorType
```ts
"invalid-credentials"
| "account-locked"
| "account-exists"
| "otp-wrong"
| "otp-expired"
| "new-device"
| "reset-expired"
| "reset-sent"
| "claim-not-found"
| null
```

### AuthSession
```ts
interface AuthSession {
  userId: string;
  name: string;
  email: string;
  phone?: string;
  role: "client" | "staff:agent" | "staff:admin";
  isEmailVerified: boolean;
  language: "en" | "rw" | "fr";
  createdAt: string;
}
```

### AuthUiState
```ts
interface AuthUiState {
  isLoading: boolean;
  submitError: string | null;
  errorType: AuthErrorType;
  lockoutUntil: string | null;
  lockoutAttempts: number;
  otpAttemptsRemaining: number;
  otpExpired: boolean;
  resetLinkSent: boolean;
  emailSent: string | null;
  showEmailVerifyBanner: boolean;
  claimFoundService: string | null;
}
```

## Reducer and Storage Contracts

### Auth actions
- `SET_SESSION`
- `CLEAR_SESSION`
- `SET_EMAIL_VERIFIED`
- `SET_UI`
- `RESET_UI`

### localStorage keys
- `proxi:auth:session`
- `proxi:auth:verified`
- `proxi:auth:lockout`
- `proxi:auth:resetToken`
- `proxi:auth:trustedDevices`

### sessionStorage keys
- `proxi:staff:pending`

## Request DTOs Mirrored from Zod

### Client login
```ts
{
  identifierType: "email" | "phone";
  identifier: string;
  password: string;
  rememberMe?: boolean;
}
```

### Client signup
```ts
{
  name: string;
  identifierType: "email" | "phone";
  identifier: string;
  password: string;
  language: "en" | "rw" | "fr";
  code?: string | "";
  terms: boolean;
}
```

### Staff login
```ts
{
  email: string;
  password: string;
  role: "agent" | "admin";
}
```

### Forgot password
```ts
{
  identifierType: "email" | "phone";
  identifier: string;
}
```

### Reset password
```ts
{
  password: string;
  confirmPassword: string;
}
```

### OTP verification
```ts
{
  code: string; // exactly 6 digits
}
```

### Claim by code
```ts
{
  code: string; // PRX-YYYY-NNNNN
  phone: string;
}
```

## Validation Rules Present in the Frontend
- Signup password minimum: 8 characters.
- Staff email: valid email format.
- Claim code: `^PRX-\\d{4}-\\d{5}$`.
- Claim phone: minimum 9 characters and `^[\\d\\s\\-\\+\\(\\)]+$`.
- Login, signup, and forgot-password identifiers are currently only required, not strongly validated by Zod.

## Flow Expectations the Backend Must Serve

### Client login
- Success returns a session compatible with `AuthSession`.
- Frontend redirects to `/verify?next=/dashboard&email=<masked>`.
- Failures map to `invalid-credentials` or `account-locked`.

### Client signup
- Success returns a session with `isEmailVerified: false`.
- Frontend redirects to `/verify?next=/&email=<masked>`.
- Duplicate account maps to `account-exists`.

### Client OTP verification
- Success should allow the frontend to set `proxi:auth:verified` to `"true"`.
- Wrong OTP maps to `otp-wrong`.
- Expired OTP maps to `otp-expired`.

### Forgot password
- Frontend always transitions to a success confirmation state.
- Backend must remain enumeration-safe.

### Reset password
- Success returns a response that allows redirect to `/login?reset=success`.
- Expired or invalid token maps to `reset-expired`.

### Claim by PRX code
- Lookup supports `GET /api/applications/lookup?code=...`.
- Claim supports `POST /api/applications/claim`.
- Missing application maps to `claim-not-found`.

### Staff auth
- `POST /api/auth/staff/login` returns a partial session plus a short-lived pre-2FA token.
- `POST /api/auth/staff/2fa` completes authentication after TOTP, SMS, or backup-code verification.

### Session refresh
- Frontend dashboard polling expects session validation and an `expiresAt` value in practice.

## Backend Reconciliation Decisions
- The backend will return an `AuthSession`-compatible object plus `expiresAt` in session-oriented responses to support the dashboard runtime behavior.
- The backend will validate email and Rwanda phone identifiers more strictly than the current frontend schemas.
- The backend will expose a masked identifier field where flows need display-safe confirmation text.
- The backend will implement secure HTTP-only cookies in parallel with JSON session responses so the current frontend keeps working while server-verified auth becomes available.
- The backend will treat `proxi:staff:pending` as a frontend transport detail, not a security boundary. The real boundary is the short-lived pre-2FA token.

## Known Frontend Drift
- `DashboardShell` reads `expiresAt` at runtime, but `AuthSession` does not declare it.
- `ResetData` in Zod does not include `token`; token is pulled from query or storage by the component.
- `device=new` is consumed but not currently produced by frontend code.
- Claim lookup UI currently renders only `serviceName`; the richer contract should still be implemented server-side.
- Client login, signup, and forgot-password use looser identifier validation than the written analysis document.
- Several `AuthUiState` fields exist canonically but are not the actual runtime source of truth in the current components.

## Initial Response Envelope Standard
The backend will normalize all API responses into this shape:

```json
{
  "success": true,
  "errorType": null,
  "message": "Human-readable message",
  "data": {}
}
```

For failures, `success` becomes `false` and `errorType` must be one of the exact literals above.
# ProxiServe Auth Contracts

## Purpose
This document captures the live authentication contract expected by `web/` as of May 2026 and translates it into backend-facing requirements for `server/`.

`web/` is the runtime source of truth. The authored frontend analysis in `web/docs/auth-frontend-analysis.md` is valuable and mostly aligned, but where prose and code differ, the live frontend code wins.

## Canonical frontend sources
- `web/lib/auth-types.ts`
- `web/lib/auth-schema.ts`
- `web/lib/auth-context.tsx`
- `web/components/organisms/ClientLoginForm.tsx`
- `web/components/organisms/ClientSignupForm.tsx`
- `web/components/organisms/VerifyOTPForm.tsx`
- `web/components/organisms/ForgotPasswordForm.tsx`
- `web/components/organisms/ResetPasswordForm.tsx`
- `web/components/organisms/ClaimByCodeForm.tsx`
- `web/components/organisms/StaffLoginForm.tsx`
- `web/components/organisms/TwoFAChallengeForm.tsx`
- `web/components/organisms/DashboardShell.tsx`

## Roles
- `client`
- `staff:agent`
- `staff:admin`

## Session contract
Frontend runtime type from `web/lib/auth-types.ts`:

```ts
interface AuthSession {
  userId: string;
  name: string;
  email: string;
  phone?: string;
  role: "client" | "staff:agent" | "staff:admin";
  isEmailVerified: boolean;
  language: "en" | "rw" | "fr";
  createdAt: string;
}
```

### Backend extension
The dashboard shell also reads an undeclared `expiresAt` property.

Resolution for backend:
- include `expiresAt` in server responses.
- use an ISO 8601 timestamp in the API contract and cookie claims.
- note that `web/components/organisms/DashboardShell.tsx` currently treats it as a numeric epoch via a cast, so frontend integration work will need to normalize this before relying on expiry checks.

## Auth UI state literals
Frontend `AuthErrorType` literals:
- `invalid-credentials`
- `account-locked`
- `account-exists`
- `otp-wrong`
- `otp-expired`
- `new-device`
- `reset-expired`
- `reset-sent`
- `claim-not-found`

Backend rule:
- never invent alternate machine-readable auth codes.
- every auth-related error envelope must use one of the literals above.

## Storage contract
### localStorage
- `proxi:auth:session`: serialized `AuthSession`
- `proxi:auth:verified`: string literal `"true"`
- `proxi:auth:lockout`: JSON like `{ "until": "<ISO timestamp>" }`
- `proxi:auth:resetToken`: reset token string
- `proxi:auth:trustedDevices`: declared in frontend types, not yet actively used by current mock flows

### sessionStorage
- `proxi:staff:pending`: serialized pending staff `AuthSession` before 2FA completion

## Auth context behavior
Reducer actions from `web/lib/auth-context.tsx`:
- `SET_SESSION`
- `CLEAR_SESSION`
- `SET_EMAIL_VERIFIED`
- `SET_UI`
- `RESET_UI`

Backend implication:
- successful login/signup/staff-2FA responses must provide enough data for the frontend to dispatch `SET_SESSION`.
- OTP verification success must support `SET_EMAIL_VERIFIED`.

## Request payload contracts
These are the field names the backend must accept.

### Client login
```json
{
  "identifierType": "email | phone",
  "identifier": "string",
  "password": "string",
  "rememberMe": true
}
```

### Client signup
```json
{
  "name": "string",
  "identifierType": "email | phone",
  "identifier": "string",
  "password": "string",
  "language": "en | rw | fr",
  "code": "optional PRX-YYYY-NNNNN",
  "terms": true
}
```

### Staff login
```json
{
  "email": "string",
  "password": "string",
  "role": "agent | admin"
}
```

### Forgot password
```json
{
  "identifierType": "email | phone",
  "identifier": "string"
}
```

### Reset password
```json
{
  "token": "string",
  "password": "string",
  "confirmPassword": "string"
}
```

### Verify OTP
```json
{
  "code": "6 numeric digits"
}
```

### Claim application
```json
{
  "code": "PRX-YYYY-NNNNN",
  "phone": "string"
}
```

### Staff 2FA
Current frontend runtime shape is inferred from `TwoFAChallengeForm`:
```json
{
  "code": "string",
  "method": "totp | sms | backup",
  "trustDevice": true
}
```

The backend will also require a pre-2FA token via secure cookie or request context.

## Validation requirements from frontend
### Email / phone
- phone input allows digits plus formatting characters.
- minimum client-side phone validation is permissive.
- backend must be stricter: parse Rwanda numbers and normalize to E.164.

### PRX code
- strict format: `^PRX-\\d{4}-\\d{5}$`
- frontend auto-formats user input with hyphens as they type.

### Password
- hard minimum is 8 characters.
- strength meter scoring in frontend:
  - +1 if length >= 8
  - +1 if mixed case
  - +1 if contains digit
  - +1 if special char or length >= 12

### Terms
- signup requires `terms === true`.

### Language
- only `en`, `rw`, `fr`.

## Route and query param contract
### Auth pages
- `/login`
- `/signup`
- `/verify`
- `/forgot-password`
- `/reset-password`
- `/claim`
- `/staff/login`
- `/staff/2fa`

### Auth query params used by frontend
- `/verify?next=<path>&email=<masked>&device=new`
- `/reset-password?token=<token>`
- `/login?reset=success`
- `/login?claimed=1`
- `/claim?code=PRX-YYYY-NNNNN`

Backend implication:
- auth responses should provide enough data for the frontend to assemble those redirects.
- password reset delivery must embed the reset token into the reset-password URL.

## Current frontend flow behavior
### Client login
- on success, frontend stores an `AuthSession`.
- then redirects to `/verify?next=/dashboard&email=<masked>`.
- lockout UI reads `proxi:auth:lockout`.

### Client signup
- on success, frontend stores an `AuthSession` with `isEmailVerified: false`.
- then redirects to `/verify?next=/&email=<masked>`.

### Verify OTP
- auto-submits on 6 digits.
- writes `proxi:auth:verified = "true"` on success.
- redirects to `next`.
- current mock starts with 3 attempts and a 5-minute timer.

### Forgot password
- always transitions to success UI after submit.
- current mock writes `proxi:auth:resetToken`.
- confirmation card displays a masked identifier.

### Reset password
- accepts token from query param or `proxi:auth:resetToken`.
- on success, clears `proxi:auth:resetToken`.
- redirects to `/login?reset=success`.

### Claim application
- supports prefilling the code from query params.
- does a debounced lookup after the code reaches full length.
- on submit success, redirects to `/login?claimed=1`.

### Staff login
- on success, stores a pending staff session in `sessionStorage`.
- then redirects to `/staff/2fa`.

### Staff 2FA
- supports methods `totp`, `sms`, `backup`.
- auto-submits on 6 digits.
- on success, loads `proxi:staff:pending`, commits it as the main session, clears the pending session, then redirects to `/`.

## Dashboard protection contract
Current protection is client-side only in `DashboardShell`:
- waits for auth hydration.
- redirects unauthenticated users to `/login?next=/dashboard`.
- shows `EmailVerifyBanner` when `session.isEmailVerified === false`.
- checks session expiry every 60 seconds using `expiresAt`.
- uses `BroadcastChannel` to detect multiple open dashboard tabs.

Backend implication:
- production security must come from cookies and server-side validation, not from this client-only shell.
- server will expose `GET /api/auth/session` and route-protection guidance for a later frontend integration pass.

## Planned response envelope
The frontend mock does not yet consume a real envelope, so the backend will standardize one early:

```json
{
  "success": true,
  "message": "Human-readable summary",
  "errorType": null,
  "data": {}
}
```
or
```json
{
  "success": false,
  "message": "Human-readable summary",
  "errorType": "invalid-credentials",
  "data": {}
}
```

Response bodies for auth success paths should include typed payloads in `data`, while also setting secure auth cookies.

## Endpoint contract to build in `server/`
### Client auth
- `POST /api/auth/login`
- `POST /api/auth/signup`
- `POST /api/auth/verify-otp`
- `POST /api/auth/resend-otp`
- `POST /api/auth/forgot-password`
- `POST /api/auth/reset-password`
- `POST /api/auth/sign-out`

### Staff auth
- `POST /api/auth/staff/login`
- `POST /api/auth/staff/2fa`

### Applications seam
- `GET /api/applications/lookup?code=<PRX>`
- `POST /api/applications/claim`

### Session
- `GET /api/auth/session`
- `DELETE /api/auth/session`

## Known discrepancies between prose spec and live frontend
1. `expiresAt`
   - prose spec: ISO string optional field.
   - live frontend type: not declared.
   - live dashboard shell: reads it as a numeric epoch via cast.

2. HTTP integration
   - prose spec assumes a full backend integration surface.
   - live frontend contains no auth `fetch` calls yet.
   - backend should still be built to the final contract, but frontend wiring remains a separate future step.

3. Claim lookup richness
   - prose spec expects `serviceName`, `submittedDate`, `status`.
   - current claim flow only requires `serviceName` to render meaningful UI, though the card supports the other two values.

4. New-device behavior
   - prose spec frames this as a backend-driven signal.
   - live frontend only checks the `device=new` query param and displays static device info defaults unless richer props are wired later.

## Backend implementation decisions locked by this doc
- `server/` will return exact frontend auth error literals.
- success responses will return JSON payloads compatible with existing `AuthSession` expectations and future server-auth integration.
- secure cookies will carry the real auth state; frontend localStorage remains a compatibility layer during rollout.
- PRX lookup and claim will be implemented behind a stable applications module seam, even if the initial implementation is a stub.
