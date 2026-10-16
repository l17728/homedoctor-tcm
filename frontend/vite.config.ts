import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target:
          process.env.HOMEDOCTOR_API_PROXY_TARGET ??
          `http://127.0.0.1:${process.env.HOMEDOCTOR_API_PORT ?? '7459'}`,
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return;
          if (
            id.includes('react-router') ||
            id.includes('/react/') ||
            id.includes('/react-dom/') ||
            id.includes('/scheduler/')
          ) {
            return 'react-vendor';
          }
          if (
            id.includes('react-markdown') ||
            id.includes('remark') ||
            id.includes('micromark') ||
            id.includes('mdast') ||
            id.includes('unified') ||
            id.includes('unist') ||
            id.includes('hast') ||
            id.includes('decode-named-character-reference') ||
            id.includes('character-reference') ||
            id.includes('trim-lines') ||
            id.includes('bail') ||
            id.includes('is-plain-obj') ||
            id.includes('trough') ||
            id.includes('vfile') ||
            id.includes('web-namespaces')
          ) {
            return 'markdown-vendor';
          }
        },
      },
    },
    chunkSizeWarningLimit: 600,
  },
});
