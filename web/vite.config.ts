import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// En production (GitHub Pages), le site est servi sous /<nom-du-dépôt>/ :
// le workflow de déploiement fournit ce chemin via VITE_BASE.
export default defineConfig({
  base: process.env.VITE_BASE ?? '/',
  plugins: [react(), tailwindcss()],
  // Version lue dans package.json (fournie par npm lors de `npm run dev` / `npm run build`).
  define: {
    __APP_VERSION__: JSON.stringify(process.env.npm_package_version ?? 'dev'),
  },
})
