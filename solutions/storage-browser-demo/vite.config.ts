import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // Proxy /api/credentials to local credentials server
      '/api/credentials': {
        target: 'http://localhost:3001',
        changeOrigin: true,
      },
    },
  },
});
