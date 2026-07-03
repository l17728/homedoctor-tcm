import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return;
          if (
            id.includes('@antv') ||
            id.includes('antv-dagre') ||
            id.includes('antv/') ||
            id.includes('/g-lite') ||
            id.includes('/g-canvas') ||
            id.includes('/g-math') ||
            id.includes('/g-plugin')
          ) {
            return 'g6-vendor';
          }
          if (
            id.includes('antd') ||
            id.includes('@ant-design') ||
            id.includes('/rc-') ||
            id.includes('rc-util') ||
            id.includes('rc-picker') ||
            id.includes('rc-table') ||
            id.includes('rc-field-form') ||
            id.includes('rc-select') ||
            id.includes('rc-tree') ||
            id.includes('rc-input') ||
            id.includes('rc-menu') ||
            id.includes('rc-tooltip') ||
            id.includes('rc-drawer') ||
            id.includes('rc-notification') ||
            id.includes('rc-motion') ||
            id.includes('rc-overflow') ||
            id.includes('rc-resize-observer') ||
            id.includes('rc-pagination') ||
            id.includes('rc-progress') ||
            id.includes('rc-rate') ||
            id.includes('rc-segmented') ||
            id.includes('rc-slider') ||
            id.includes('rc-steps') ||
            id.includes('rc-switch') ||
            id.includes('rc-tabs') ||
            id.includes('rc-upload') ||
            id.includes('rc-collapse') ||
            id.includes('rc-dialog') ||
            id.includes('rc-image')
          ) {
            return 'antd-vendor';
          }
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
