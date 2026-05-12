import type { NextConfig } from "next";

const API_HOST = process.env.API_HOST || "backend";
const API_PORT = process.env.API_PORT || "8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `http://${API_HOST}:${API_PORT}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
