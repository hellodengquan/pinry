import { defineConfig } from 'vitest/config';
import { createVuePlugin } from 'vite-plugin-vue2';

export default defineConfig({
  plugins: [createVuePlugin()],
  test: {
    globals: true,
    environment: 'jsdom',
    include: ['src/**/*.{test,spec}.{js,ts}'],
    setupFiles: ['./src/setupTests.js'],
  },
  resolve: {
    alias: {
      '@': '/src',
    },
  },
});
