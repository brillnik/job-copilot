// /auth/* routes are served by the Auth0 SDK (see src/proxy.ts) and need a
// full-page navigation, not client routing.
export function login(params: Record<string, string> = {}) {
  const search = new URLSearchParams({ returnTo: "/", ...params });
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination
  window.location.assign(`/auth/login?${search}`);
}

export const GOOGLE_CONNECTION = "google-oauth2";
