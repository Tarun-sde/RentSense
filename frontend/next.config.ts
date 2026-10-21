import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination:
          "https://rentsense-backend.jollyfield-d646910c.uaenorth.azurecontainerapps.io/api/:path*",
      },
    ];
  },
};

export default nextConfig;
