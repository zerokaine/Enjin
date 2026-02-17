/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  transpilePackages: ['globe.gl', 'three'],
}

module.exports = nextConfig
