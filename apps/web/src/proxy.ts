import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { auth0 } from "./lib/auth0";

// E2E only: Playwright cannot complete a real Auth0 login, so the e2e web server
// is started with E2E_STUB_AUTH=1 and API calls are stubbed in the browser. The
// bypass is inert in production builds (NODE_ENV === "production").
const E2E_STUB_AUTH =
  process.env.E2E_STUB_AUTH === "1" && process.env.NODE_ENV !== "production";

export async function proxy(request: NextRequest) {
  if (E2E_STUB_AUTH) return NextResponse.next();
  // Mounts /auth/login, /auth/logout, /auth/callback and rolls the session.
  const response = await auth0.middleware(request);
  const { pathname } = request.nextUrl;
  // /api/* is the FastAPI proxy; it answers 401 itself instead of redirecting.
  if (pathname.startsWith("/auth/") || pathname.startsWith("/api/")) {
    return response;
  }

  const session = await auth0.getSession(request);
  // /account-deleted is the public landing page after "delete account" signs the user out.
  if (!session && pathname !== "/sign-in" && pathname !== "/account-deleted") {
    return NextResponse.redirect(new URL("/sign-in", request.url));
  }
  if (session && pathname === "/sign-in") {
    return NextResponse.redirect(new URL("/", request.url));
  }
  return response;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
