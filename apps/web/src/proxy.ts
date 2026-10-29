import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { auth0 } from "./lib/auth0";

export async function proxy(request: NextRequest) {
  // Mounts /auth/login, /auth/logout, /auth/callback and rolls the session.
  const response = await auth0.middleware(request);
  const { pathname } = request.nextUrl;
  // /api/* is the FastAPI proxy; it answers 401 itself instead of redirecting.
  if (pathname.startsWith("/auth/") || pathname.startsWith("/api/")) {
    return response;
  }

  const session = await auth0.getSession(request);
  if (!session && pathname !== "/sign-in") {
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
