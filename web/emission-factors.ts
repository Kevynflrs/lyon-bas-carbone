// Lecture des facteurs d'émission au moment du build (voir vite.config.ts).
// Source unique : reference/emission_factors.csv, produit par pipeline/ingest/emission_factors.py.
// Un fichier absent ou incohérent fait échouer le build : l'erreur apparaît dans la CI, pas en prod.
import { readFileSync } from 'node:fs'

export interface EmissionFactor {
  mode: string
  total: number
  usage: number
  construction: number
  hypothese: string
  source: string
  retrievedOn: string
}

const EXPECTED_MODES = [
  'voiture_thermique',
  'voiture_electrique',
  'bus_thermique',
  'bus_electrique',
  'tramway',
  'metro',
  'velo',
  'velo_electrique',
  'marche',
]

/** Découpe un CSV simple (RFC 4180) : champs entre guillemets, virgules et guillemets doublés. */
export function parseCsv(text: string): string[][] {
  const rows: string[][] = []
  let row: string[] = []
  let field = ''
  let quoted = false
  for (let i = 0; i < text.length; i++) {
    const char = text[i]
    if (quoted) {
      if (char === '"' && text[i + 1] === '"') {
        field += '"'
        i++
      } else if (char === '"') {
        quoted = false
      } else {
        field += char
      }
    } else if (char === '"') {
      quoted = true
    } else if (char === ',') {
      row.push(field)
      field = ''
    } else if (char === '\n' || char === '\r') {
      if (char === '\r' && text[i + 1] === '\n') i++
      row.push(field)
      if (row.some((value) => value !== '')) rows.push(row)
      row = []
      field = ''
    } else {
      field += char
    }
  }
  row.push(field)
  if (row.some((value) => value !== '')) rows.push(row)
  return rows
}

export function loadEmissionFactors(path: string): EmissionFactor[] {
  const [header, ...lines] = parseCsv(readFileSync(path, 'utf-8').replace(/^\uFEFF/, ''))
  const column = (name: string) => {
    const index = header.indexOf(name)
    if (index === -1) throw new Error(`${path} : colonne « ${name} » absente`)
    return index
  }
  const number = (line: string[], name: string) => {
    const value = Number(line[column(name)])
    if (!Number.isFinite(value) || value < 0) {
      throw new Error(`${path} : ${name} invalide pour ${line[column('mode')]} (${line[column(name)]})`)
    }
    return value
  }

  const factors = lines.map((line) => ({
    mode: line[column('mode')],
    total: number(line, 'total_g_per_km'),
    usage: number(line, 'usage_g_per_km'),
    construction: number(line, 'construction_g_per_km'),
    hypothese: line[column('hypothese')],
    source: line[column('source')],
    retrievedOn: line[column('retrieved_on')],
  }))

  const modes = factors.map((f) => f.mode)
  const missing = EXPECTED_MODES.filter((mode) => !modes.includes(mode))
  if (missing.length > 0) throw new Error(`${path} : modes manquants ${missing.join(', ')}`)
  for (const f of factors) {
    if (Math.abs(f.usage + f.construction - f.total) > 0.01) {
      throw new Error(`${path} : usage + construction ≠ total pour ${f.mode}`)
    }
  }
  return factors
}
