import { NextResponse } from "next/server";

/**
 * Some browsers and crawlers request /favicon.ico regardless of the <link rel="icon">
 * metadata tag (which points at /icon.svg). Redirect to it so the request never shows up
 * as a 404 in QA or the console.
 */
export function GET(request: Request) {
  return NextResponse.redirect(new URL("/icon.svg", request.url), { status: 308 });
}
