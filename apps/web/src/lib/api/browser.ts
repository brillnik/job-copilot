import createClient, { type Middleware } from "openapi-fetch";
import { ApiError } from "./errors";
import type { paths } from "./schema";

// Browser client: talks to the same-origin Next proxy at /api/*, which holds
// the Auth0 session (HTTP-only cookie) and attaches the bearer access token
// before forwarding to FastAPI (see app/api/[...path]/route.ts). Tokens never
// reach the browser; `credentials: "include"` only sends the session cookie to
// our own origin.
//
// Network failures surface as ApiError(code "network_error") instead of a bare
// TypeError, so every caller sees the same error type.
const networkErrors: Middleware = {
  onError({ error }) {
    if (error instanceof DOMException && error.name === "AbortError")
      return error;
    return new ApiError({
      code: "network_error",
      message: "Can't reach the server. Check your connection and try again.",
      status: 0,
    });
  },
};

export const api = createClient<paths>({
  baseUrl: "/api",
  credentials: "include",
});
api.use(networkErrors);
