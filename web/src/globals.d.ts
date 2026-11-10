// Constantes injectées par Vite au build (voir vite.config.ts).
declare const __APP_VERSION__: string

// Lu dans reference/emission_factors.csv (gCO2e par personne et par km).
declare const __EMISSION_FACTORS__: {
  mode: string
  total: number
  usage: number
  construction: number
  hypothese: string
  source: string
  retrievedOn: string
}[]
