import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE, SESSION_MAX_AGE, safeEqual, safeNext, sessionToken } from "@/lib/session";

export async function POST(req: NextRequest) {
  const form = await req.formData();
  const next = safeNext(form.get("next"));
  const password = process.env.SITE_PASSWORD;
  if (!password) return NextResponse.redirect(new URL(next, req.url), 303);

  const given = String(form.get("password") ?? "");
  const expected = await sessionToken(password);
  if (!safeEqual(await sessionToken(given), expected)) {
    // A pause per wrong guess makes online guessing slow without a rate-limit store.
    await new Promise((r) => setTimeout(r, 1000));
    const back = new URL("/login", req.url);
    back.searchParams.set("error", "1");
    if (next !== "/") back.searchParams.set("next", next);
    return NextResponse.redirect(back, 303);
  }

  const res = NextResponse.redirect(new URL(next, req.url), 303);
  res.cookies.set(SESSION_COOKIE, expected, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: SESSION_MAX_AGE,
  });
  return res;
}
