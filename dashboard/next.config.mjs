/** @type {import('next').NextConfig} */
const nextConfig = {
  // Every page here is a client component talking straight to Supabase, so the
  // whole dashboard prerenders to static files and Cloudflare serves them from
  // the edge. Two consequences worth remembering:
  //   - middleware cannot run; components/AuthGuard.tsx is the front door now
  //   - headers() below would be ignored, so they live in public/_headers
  output: 'export',
  reactStrictMode: true,
  poweredByHeader: false,

  // Cloudflare serves /products as /products.html, so ask Next for that shape.
  trailingSlash: false,

  images: {
    // No server to optimise on. Nothing uses next/image today, but this keeps
    // the build honest if someone adds one.
    unoptimized: true,
  },
};

export default nextConfig;
