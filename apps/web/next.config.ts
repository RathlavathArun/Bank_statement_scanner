import type { NextConfig } from "next";

// In production (ECS), API_URL points to the internal Cloud Map service discovery address.
// Locally, defaults to the Python backend on localhost.
const apiUrl = process.env.API_URL || "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  turbopack: {},

  async rewrites() {
    return [
      {
        source: "/api/auth/:path*",
        destination: `${apiUrl}/v1/auth/:path*`,
      },
      {
        source: "/api/:path*",
        destination: `${apiUrl}/:path*`,
      },
    ];
  },
};

export default nextConfig;