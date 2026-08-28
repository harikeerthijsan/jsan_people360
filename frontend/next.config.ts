import type { NextConfig } from 'next';

/**
 * Security headers applied to every response the Next.js server produces.
 * The API sets its own; these protect the document itself.
 */
const securityHeaders = [
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'X-Frame-Options', value: 'DENY' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  { key: 'Permissions-Policy', value: 'geolocation=(), microphone=(), camera=()' },
];

const nextConfig: NextConfig = {
  reactStrictMode: true,

  // A self-contained server bundle (`.next/standalone`) for the Docker image;
  // the runtime stage copies only that plus the static assets.
  output: 'standalone',

  // Fail the production build on a type or lint error rather than shipping it.
  typescript: { ignoreBuildErrors: false },
  eslint: { ignoreDuringBuilds: false },

  // Do not advertise the framework version to the world.
  poweredByHeader: false,

  async headers() {
    return [{ source: '/:path*', headers: securityHeaders }];
  },
};

export default nextConfig;
