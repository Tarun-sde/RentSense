import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://rentsense-backend/api/:path*",
      },
    ];
  },
};

export default nextConfig;
