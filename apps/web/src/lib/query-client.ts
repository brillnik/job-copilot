import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { ApiError } from "./api/errors";

function redirectIfUnauthenticated(error: unknown) {
  if (
    error instanceof ApiError &&
    error.status === 401 &&
    // reauth_required (DELETE /me) is a prompt to re-login, not an expired session.
    error.code !== "reauth_required" &&
    typeof window !== "undefined"
  ) {
    // Session expired: back to sign-in (full navigation, tokens are server-side).
    if (!window.location.pathname.startsWith("/sign-in")) {
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      window.location.href = "/sign-in";
    }
  }
}

export function makeQueryClient() {
  return new QueryClient({
    queryCache: new QueryCache({ onError: redirectIfUnauthenticated }),
    mutationCache: new MutationCache({ onError: redirectIfUnauthenticated }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        // Don't retry auth/validation/stale-write errors; do retry flaky ones once.
        retry: (count, error) =>
          count < 1 &&
          !(
            error instanceof ApiError &&
            error.status >= 400 &&
            error.status < 500
          ),
      },
    },
  });
}
