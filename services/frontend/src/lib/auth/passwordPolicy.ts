/**
 * Minimum length of every new password (signup, reset, change, activation,
 * profile completion). Mirrors MIN_PASSWORD_LENGTH in the API's
 * auth_module/models.py, which enforces it; existing shorter passwords
 * still log in.
 */
export const MIN_PASSWORD_LENGTH = 12
