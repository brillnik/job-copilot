import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { auth0 } from "@/lib/auth0";
import { API_URL } from "@/lib/api/server";

// Same-origin proxy: /api/<path> -> FastAPI /<path> with the Auth0 access token.
async function proxy(
  req: NextRequest,
  ctx: { params: Promise<{ path: string[] }> },
) {
  const session = await auth0.getSession();
  if (!session) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }
  const { token } = await auth0.getAccessToken();

  const { path } = await ctx.params;
  const url = new URL(`/${path.join("/")}`, API_URL);
  url.search = req.nextUrl.search;

  const headers = new Headers(req.headers);
  headers.set("authorization", `Bearer ${token}`);
  headers.delete("cookie");
  headers.delete("host");

  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  const upstream = await fetch(url, {
    method: req.method,
    headers,
    body: hasBody ? req.body : undefined,
    // @ts-expect-error duplex is required for streaming request bodies
    duplex: "half",
    redirect: "manual",
    cache: "no-store",
  });

  // Strip hop-by-hop / encoding headers; the body is passed through as-is.
  const resHeaders = new Headers(upstream.headers);
  resHeaders.delete("content-encoding");
  resHeaders.delete("content-length");
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: resHeaders,
  });
}

export {
  proxy as GET,
  proxy as POST,
  proxy as PUT,
  proxy as PATCH,
  proxy as DELETE,
};
