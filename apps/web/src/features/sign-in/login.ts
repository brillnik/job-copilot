// /auth/* routes are served by the Auth0 SDK (see src/proxy.ts) and need a
// full-page navigation, not client routing.
export function login(params: Record<string, string> = {}) {
  const search = new URLSearchParams({ returnTo: "/", ...params });
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  window.location.assign(`/auth/login?${search}`);
}

export const GOOGLE_CONNECTION = "google-oauth2";

// Auth0 connection used for "Continue with email". When unset the Auth0 login
// page decides (database login or, if enabled, a passwordless email code). Set
// NEXT_PUBLIC_AUTH0_EMAIL_CONNECTION=email to force the Passwordless email
// connection (one-time code), which must be enabled for this app in the tenant.
export const EMAIL_CONNECTION =
  process.env.NEXT_PUBLIC_AUTH0_EMAIL_CONNECTION || undefined;
