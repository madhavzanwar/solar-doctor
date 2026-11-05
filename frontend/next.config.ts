import type { NextConfig } from "next";

// Photos are self-hosted in public/images (credits in docs/IMAGE_CREDITS.md); no remote image hosts.
// NEXT_DIST_DIR lets the visual harness build into .next-visual without clobbering the normal build.
const nextConfig: NextConfig = {
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
