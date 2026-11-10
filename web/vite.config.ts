import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import { loadEmissionFactors } from './emission-factors.ts'

// Facteurs d'émission versionnés à la racine du dépôt, lus et contrôlés à chaque build.
const EMISSION_FACTORS_CSV = fileURLToPath(new URL('../reference/emission_factors.csv', import.meta.url))

// En production (GitHub Pages), le site est servi sous /<nom-du-dépôt>/ :
// le workflow de déploiement fournit ce chemin via VITE_BASE.
export default defineConfig({
  base: process.env.VITE_BASE ?? '/',
  plugins: [react(), tailwindcss()],
  define: {
    // Version lue dans package.json (fournie par npm lors de `npm run dev` / `npm run build`).
    __APP_VERSION__: JSON.stringify(process.env.npm_package_version ?? 'dev'),
    __EMISSION_FACTORS__: JSON.stringify(loadEmissionFactors(EMISSION_FACTORS_CSV)),
  },
})
