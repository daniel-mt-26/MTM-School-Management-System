import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'prompt',
      manifest: {
        name: 'MTM School Management System',
        short_name: 'MTM SMS',
        description: 'MTM School Management System',
        theme_color: '#2457a5',
        background_color: '#f7f8fa',
        display: 'standalone',
        start_url: '/',
        scope: '/',
        icons: [{ src: '/mtm-icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any maskable' }],
      },
      workbox: {
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//],
        runtimeCaching: [],
      },
    }),
  ],
})
