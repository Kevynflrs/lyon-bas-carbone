import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// En production (GitHub Pages), le site est servi sous /<nom-du-dépôt>/ :
// le workflow de déploiement fournit ce chemin via VITE_BASE.
export default defineConfig({
  base: process.env.VITE_BASE ?? '/',
  plugins: [react(), tailwindcss()],
})
