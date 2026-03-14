import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  // Disable React Strict Mode — double-mount in dev causes WebGL context loss
  // because R3F Canvas creates/destroys/recreates GPU resources too fast.
  reactStrictMode: false,
  transpilePackages: ["three", "@react-three/fiber", "@react-three/drei"],
  async headers() {
    return [
      {
        // PowerSync OPFS/SharedArrayBuffer requires these headers
        source: "/(.*)",
        headers: [
          { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
          { key: "Cross-Origin-Embedder-Policy", value: "credentialless" },
        ],
      },
    ];
  },
  async rewrites() {
    // Only proxy /api/* to local backend in development.
    // In production, frontend calls NEXT_PUBLIC_API_URL directly.
    if (process.env.NODE_ENV !== "production") {
      return [
        {
          source: "/api/:path*",
          destination: "http://localhost:8000/api/:path*",
        },
      ];
    }
    return [];
  },
  httpAgentOptions: {
    keepAlive: true,
  },
  experimental: {
    proxyTimeout: 300_000,
  },
  // Force all packages to use the SAME React instance (client-side only).
  // Without this, R3F's react-reconciler can resolve a different React copy,
  // causing "ReactCurrentOwner" errors that next/dynamic silently swallows.
  webpack: (config, { isServer }) => {
    if (!isServer) {
      config.resolve.alias = {
        ...config.resolve.alias,
        react: path.resolve("./node_modules/react"),
        "react-dom": path.resolve("./node_modules/react-dom"),
      };
      // PowerSync WASM support: allow .wasm files to be imported as assets
      config.resolve.fallback = {
        ...config.resolve.fallback,
        fs: false,
        path: false,
      };
    }
    return config;
  },
  // Required for PowerSync WASM/Worker assets served from node_modules
  serverExternalPackages: ["@powersync/web"],
};

export default nextConfig;
