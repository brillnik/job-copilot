import "server-only";
import createClient from "openapi-fetch";
import { auth0 } from "../auth0";
import type { paths } from "./schema";

export const API_URL = process.env.API_URL ?? "http://localhost:8000";

// Server client (Server Components, route handlers): calls FastAPI directly and
// attaches the signed-in user's Auth0 access token.
export async function serverApi() {
  const { token } = await auth0.getAccessToken();
  return createClient<paths>({
    baseUrl: API_URL,
    headers: { Authorization: `Bearer ${token}` },
  });
}
