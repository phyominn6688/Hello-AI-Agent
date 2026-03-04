/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone", // For Docker / ECS deployment

  // API base URL — NEXT_PUBLIC_ vars are inlined at build time
  // Override per environment in Amplify build settings
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  },

  images: {
    remotePatterns: [
      { protocol: "https", hostname: "*.googleusercontent.com" },
      { protocol: "https", hostname: "*.amazonaws.com" },
    ],
  },
};

module.exports = nextConfig;
