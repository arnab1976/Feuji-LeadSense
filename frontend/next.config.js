/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  env: {
    // Same-origin by default so the browser never hits a mismatched localhost/IPv6 host.
    NEXT_PUBLIC_API_BASE_URL:
      process.env.NEXT_PUBLIC_API_BASE_URL || "/api/v1",
  },
  async rewrites() {
    const upstream =
      process.env.LEADSENSE_API_ORIGIN || "http://127.0.0.1:8000";
    return [
      {
        source: "/api/v1/:path*",
        destination: `${upstream}/api/v1/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
