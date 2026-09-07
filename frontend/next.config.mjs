/** @type {import('next').NextConfig} */
const nextConfig = {
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  // Allow the dev server to accept requests from a tunnel host (Cloudflare
  // Tunnel / ngrok) so a candidate on another machine can open /interview/<token>.
  // Next 16 blocks non-localhost dev origins by default.
  allowedDevOrigins: [
    '*.trycloudflare.com',
    '*.ngrok-free.app',
    '*.ngrok.io',
    '*.ngrok.app',
  ],
}

export default nextConfig
