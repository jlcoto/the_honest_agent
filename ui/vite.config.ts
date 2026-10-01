import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  // Relative asset URLs, so the built report works from any path it's hosted under.
  base: './',
})
