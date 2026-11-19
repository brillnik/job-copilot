import { NextResponse } from "next/server";
import { auth0 } from "@/lib/auth0";

// DEV ONLY: shows the signed-in user's Auth0 access token so you can paste it
// into Swagger (/docs) or curl. Delete this file when you are done testing.
export async function GET() {
  if (process.env.NODE_ENV === "production") {
    return NextResponse.json({ detail: "Not found" }, { status: 404 });
  }
  const session = await auth0.getSession();
  if (!session) {
    return NextResponse.json({ detail: "Not authenticated" }, { status: 401 });
  }
  const { token } = await auth0.getAccessToken();
  return NextResponse.json(
    { sub: session.user.sub, token },
    { headers: { "Cache-Control": "no-store" } },
  );
}
