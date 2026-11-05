import { NextResponse, type NextRequest } from "next/server";
import { SESSION_COOKIE, guardDecision } from "@/lib/auth-guard";

export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const decision = guardDecision(pathname, search, Boolean(request.cookies.get(SESSION_COOKIE)?.value));
  if (decision.action === "redirect") {
    return NextResponse.redirect(new URL(decision.location, request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard", "/dashboard/:path*"],
};
