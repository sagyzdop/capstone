import type { NextConfig } from "next";

const config: NextConfig = {
  // native addon: load it from node_modules at runtime instead of bundling
  serverExternalPackages: ["onnxruntime-node"],
  // dev blocks HMR and /_next requests from any host but localhost unless listed here;
  // server.mjs listens on both loopbacks, so allow them by address too
  allowedDevOrigins: ["127.0.0.1", "[::1]", "::1"],
  devIndicators: false,
  // this folder is the app root; without it Turbopack picks up a lockfile further up the tree
  turbopack: { root: process.cwd() },
};

export default config;
