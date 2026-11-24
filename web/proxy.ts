import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE, safeEqual, sessionToken } from "@/lib/session";

/** Gate the whole site behind SITE_PASSWORD when it is set. */
export async function proxy(req: NextRequest) {
  const password = process.env.SITE_PASSWORD;
  if (!password) return NextResponse.next();

  const { pathname, search } = req.nextUrl;
  if (pathname === "/login" || pathname.startsWith("/auth/")) return NextResponse.next();

  const cookie = req.cookies.get(SESSION_COOKIE)?.value ?? "";
  if (safeEqual(cookie, await sessionToken(password))) return NextResponse.next();

  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ detail: "Sign in required." }, { status: 401 });
  }
  const login = new URL("/login", req.url);
  if (pathname !== "/") login.searchParams.set("next", pathname + search);
  return NextResponse.redirect(login);
}

// The logo, app icon and link-preview card are public: the sign-in page and link
// previews (fetched by crawlers with no session) need them.
export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|icon.png|sm-mark.png|opengraph-image).*)"],
};
