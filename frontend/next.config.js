/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Static export — this app has no server-side API routes (every data
  // call goes to the FastAPI backend via fetch), so it can ship as plain
  // static files. Cloudflare Pages serves this directly, no adapter needed.
  output: "export",
};

module.exports = nextConfig;
