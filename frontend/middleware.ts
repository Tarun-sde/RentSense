import { NextRequest, NextResponse } from "next/server";

// Routes that don't need authentication
const PUBLIC_PATHS = ["/login"];

// Static asset prefixes that should never be redirected
const BYPASS_PREFIXES = ["/_next/", "/favicon.ico", "/api/"];

const COOKIE_NAME = "access_token";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Never block static assets or API routes
  if (BYPASS_PREFIXES.some((p) => pathname.startsWith(p))) {
    return NextResponse.next();
  }

  const isPublic = PUBLIC_PATHS.some((p) => pathname === p);
  const hasToken = Boolean(request.cookies.get(COOKIE_NAME)?.value);

  if (!hasToken && !isPublic) {
    // Unauthenticated access to protected route → /login
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }

  // Cookie presence does not prove validity; allow re-login after JWT expiry.

  return NextResponse.next();
}

export const config = {
  // Run on all routes except static files
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
