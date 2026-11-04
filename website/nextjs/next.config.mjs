/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ['three', '@react-three/fiber', '@react-three/drei', '@react-three/postprocessing'],
  output: 'standalone',
  // TEMPORARY: serve the static landing page (public/site/index.html) at "/".
  // To restore the 3D scroll site, delete this rewrites() block and public/site/.
  async rewrites() {
    return {
      beforeFiles: [
        { source: '/', destination: '/site/index.html' },
        // Static technical investor brief — plain HTML, no React.
        // Lives in public/stack/index.html rather than a 1000-line route handler.
        { source: '/stack', destination: '/stack/index.html' },
      ],
    }
  },
}

export default nextConfig
