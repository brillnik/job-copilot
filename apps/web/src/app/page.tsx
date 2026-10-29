import { Suspense } from "react";

async function ApiStatus() {
  let status = "unreachable";
  try {
    const res = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/health`,
      { cache: "no-store" },
    );
    status = (await res.json()).status;
  } catch {}
  return <strong>{status}</strong>;
}

export default function Home() {
  return (
    <main className="flex min-h-screen items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <p className="text-xl">
          API status:{" "}
          <Suspense fallback={<strong>checking…</strong>}>
            <ApiStatus />
          </Suspense>
        </p>
        <a href="/auth/logout" className="underline">
          Sign out
        </a>
      </div>
    </main>
  );
}
