// import { defineConfig } from 'vite'
// import react from '@vitejs/plugin-react'
// import tailwindcss from '@tailwindcss/vite'

// // https://vite.dev/config/
// export default defineConfig({
//   plugins: [react(),tailwindcss()],
//   server: {
//     host: true, 
//     port: 5173, 
//     watch: {
//       usePolling: true, 
//     },
//   },
// })

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true, 
    port: 5173, 
    watch: {
      usePolling: true, 
    },
    proxy: {
      '/api': {
        target: 'http://backend:8000', // Targets the local backend container name in docker-compose
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''), // Strips /api locally to match production Nginx behavior
      },
    },
  },
})