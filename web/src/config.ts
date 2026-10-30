// Fichier JSON produit toutes les 15 minutes par le pipeline Python (pipeline/export/snapshot.py).
// En production, le workflow de déploiement fournit ces deux adresses au moment du build.
export const SNAPSHOT_URL: string =
  import.meta.env.VITE_SNAPSHOT_URL ??
  'https://huggingface.co/datasets/Kevynflrs/lyon-bas-carbone-data/resolve/main/public/velov_latest.json'

export const REPO_URL: string =
  import.meta.env.VITE_REPO_URL ?? 'https://github.com/Kevynflrs/lyon-bas-carbone'

// Le front relit le fichier toutes les 5 minutes ; la collecte tourne toutes les 15 minutes.
export const REFRESH_MS = 5 * 60 * 1000

// Au-delà, la collecte est considérée en retard.
export const STALE_AFTER_MS = 60 * 60 * 1000
