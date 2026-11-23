import type { NextRequest } from "next/server";

/**
 * Same-origin proxy to the FastAPI backend.
 *
 * The browser only ever talks to this app, so there is no CORS to configure,
 * and the hub token (HUB_WRITE_TOKEN) is attached here on the server instead
 * of being shipped to the client bundle. proxy.ts has already checked the
 * visitor's sign-in by the time a request reaches this handler.
 */
const BACKEND = (process.env.BACKEND_URL ?? "http://127.0.0.1:8137").replace(/\/$/, "");

async function forward(req: NextRequest, ctx: RouteContext<"/api/[...path]">) {
  const { path } = await ctx.params;
  const target = `${BACKEND}/api/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;

  const headers = new Headers({ accept: "application/json" });
  const contentType = req.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  const token = process.env.HUB_WRITE_TOKEN;
  // Sent on reads too: the backend withholds positions (holdings, portfolio)
  // from requests without it.
  if (token) headers.set("x-hub-token", token);

  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  try {
    const upstream = await fetch(target, {
      method: req.method,
      headers,
      body: hasBody ? await req.text() : undefined,
      cache: "no-store",
    });
    return new Response(upstream.body, {
      status: upstream.status,
      headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return Response.json(
      { detail: `Backend unreachable at ${BACKEND}. Is the API server running?` },
      { status: 502 },
    );
  }
}

export const GET = forward;
export const POST = forward;
export const PATCH = forward;
export const DELETE = forward;
