import { defineConfig } from 'vite';
import liveReload from 'vite-plugin-live-reload';
import { resolve } from 'path';

export default defineConfig({
  root: 'static',
  plugins: [
    liveReload([
      'static/pages/**/*.html',
      'static/design-system/**/*.html',
    ]),
  ],
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  css: {
    preprocessorOptions: {
      scss: {
        loadPaths: [resolve(__dirname, 'node_modules')],
      },
    },
  },
  build: {
    outDir: '../dist',
    emptyOutDir: true,
    rollupOptions: {
      input: {
        dashboard: resolve(__dirname, 'static/pages/dashboard.html'),
        assessment: resolve(__dirname, 'static/pages/assessment.html'),
        conversation: resolve(__dirname, 'static/pages/conversation.html'),
        review: resolve(__dirname, 'static/pages/review.html'),
        play: resolve(__dirname, 'static/pages/play.html'),
        base: resolve(__dirname, 'static/pages/base.html'),
      },
    },
  },
});
