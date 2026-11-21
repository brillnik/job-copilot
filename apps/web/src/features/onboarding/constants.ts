// Mirrors of server configuration that no endpoint exposes. Keep in sync with
// apps/api/app/core/config.py until the API publishes them.

/** `max_resume_bytes` (5 MB). */
export const MAX_RESUME_BYTES = 5 * 1024 * 1024;

/** `allowed_cities`: PUT /settings rejects any other city with a 422. */
export const ALLOWED_CITIES = [
  "Remote",
  "Bengaluru",
  "Hyderabad",
  "Pune",
  "Mumbai",
  "Delhi NCR",
  "Chennai",
  "Kolkata",
  "Ahmedabad",
  "Kochi",
  "Jaipur",
  "Chandigarh",
] as const;

/** Where each setup step lives. */
export const ONBOARDING_PATHS = {
  consent: "/onboarding/consent",
  upload: "/onboarding/upload",
  review: "/onboarding/review",
  preferences: "/onboarding/preferences",
} as const;
