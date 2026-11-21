// The API does not expose the current privacy-policy version (it is server
// config `policy_version`, default "2026-01"), so the web app carries its own.
// Keep NEXT_PUBLIC_POLICY_VERSION equal to the API's POLICY_VERSION.
export const POLICY_VERSION =
  process.env.NEXT_PUBLIC_POLICY_VERSION || "2026-01";

// The sign-in screen requires the consent box before redirecting to Auth0. The
// tick is carried across that redirect in sessionStorage (a policy version
// string, no token and no personal data) so it can be recorded via
// POST /me/consent right after login without asking twice.
const ACK_KEY = "jc-consent-ack";

export function rememberConsentTick() {
  try {
    sessionStorage.setItem(ACK_KEY, POLICY_VERSION);
  } catch {
    /* private mode: the consent step simply asks again */
  }
}
export function hasConsentTick(): boolean {
  try {
    return sessionStorage.getItem(ACK_KEY) === POLICY_VERSION;
  } catch {
    return false;
  }
}
export function clearConsentTick() {
  try {
    sessionStorage.removeItem(ACK_KEY);
  } catch {
    /* ignore */
  }
}
