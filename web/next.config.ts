import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  env: {
    NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000",
  },

  // A production build and the dev server share `.next` by default, so building while `make web`
  // is running wipes the dev server's compiled assets out from under it: the page starts serving
  // a 404 stylesheet (every figure renders as a black rectangle) and then 500s outright. Giving
  // the build its own directory means the two cannot collide.
  distDir: process.env.NODE_ENV === "production" ? ".next-build" : ".next",
};

export default nextConfig;
