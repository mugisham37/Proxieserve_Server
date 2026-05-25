"""Authentication module constants."""

ACCESS_COOKIE_NAME = "proxiserve_access"
REFRESH_COOKIE_NAME = "proxiserve_refresh"
PRE_2FA_REDIS_PREFIX = "auth:pre2fa"
OTP_REDIS_PREFIX = "auth:otp"
LOCKOUT_REDIS_PREFIX = "auth:lockout"
RESEND_REDIS_PREFIX = "auth:otp:resend"
REFRESH_REDIS_PREFIX = "auth:refresh"
DEVICE_TRUST_REDIS_PREFIX = "auth:device"

CLIENT_ROLE = "client"
STAFF_AGENT_ROLE = "staff:agent"
STAFF_ADMIN_ROLE = "staff:admin"
