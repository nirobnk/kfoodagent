import type { Viewport } from "next";
import { PIXEL_BASE_CODE, PIXEL_NOSCRIPT_SRC } from "@/lib/pixel";
import "./globals.css";

/* Next writes the charset and `width=device-width, initial-scale=1` itself. */
export const viewport: Viewport = { themeColor: "#e0222b" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en-LK">
      <head>
        <link rel="icon" type="image/png" href="/images/favicon.png" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        {/* eslint-disable-next-line @next/next/no-page-custom-font -- the root layout covers every page */}
        <link
          href="https://fonts.googleapis.com/css2?family=Black+Han+Sans&family=IBM+Plex+Mono:wght@400;600&family=Noto+Sans+KR:wght@400;500;700&display=swap"
          rel="stylesheet"
        />
        {/* Meta Pixel — inline, so PageView is queued before anything else runs */}
        <script dangerouslySetInnerHTML={{ __html: PIXEL_BASE_CODE }} />
      </head>
      <body>
        <noscript>
          {/* eslint-disable-next-line @next/next/no-img-element -- the pixel's no-JS fallback */}
          <img height="1" width="1" style={{ display: "none" }} alt="" src={PIXEL_NOSCRIPT_SRC} />
        </noscript>
        {children}
      </body>
    </html>
  );
}
