import type { NextConfig } from "next";

// In production (ECS), API_URL points to the internal Cloud Map service discovery address.
// Locally, defaults to the Python backend on localhost.
const apiUrl = process.env.API_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  output: "standalone",

  async rewrites() {
    return [
      {
        // All frontend API calls go through /api/* and get proxied to the backend.
        // e.g. /api/v1/auth/signup → http://api-host:8000/v1/auth/signup
        source: "/api/:path*",
        destination: `${apiUrl}/:path*`,
      },
    ];
  },
};

export default nextConfig;