import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV === "development";

const nextConfig: NextConfig = {
  // Netlify serves the prerendered files in out/. Every URL stays exactly where
  // the hand-built site had it: /cart.html, /products/<handle>.html. With
  // trailingSlash false, app/products/[handle] exports to products/<handle>.html.
  //
  // Only for builds: a static export forbids rewrites even under `next dev`,
  // and the dev server needs the rewrite below.
  ...(isDev ? {} : { output: "export" as const }),
  trailingSlash: false,
  reactStrictMode: true,
  poweredByHeader: false,

  // Plain <img> everywhere, never next/image — it would rewrite every image URL
  // Google has indexed. This keeps the build honest if someone adds one.
  images: { unoptimized: true },

  // The site links to /cart.html and /products/<handle>.html, because those are
  // the URLs Google knows. `next dev` serves routes without the extension, so
  // map one onto the other while developing. Builds never see this.
  ...(isDev
    ? {
        async rewrites() {
          return [{ source: "/:path*.html", destination: "/:path*" }];
        },
      }
    : {}),
};

export default nextConfig;
