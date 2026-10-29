import createClient from "openapi-fetch";
import type { paths } from "./schema";

// Browser client: talks to the same-origin proxy at /api/*, which attaches the
// Auth0 access token and forwards to the FastAPI service (see app/api/[...path]).
export const api = createClient<paths>({ baseUrl: "/api" });
