export type Station = {
  id: string
  name: string
  lat: number
  lon: number
  capacity: number | null
  bikes: number | null
  docks: number | null
  renting: boolean
  last_reported: string | null
}

export type Snapshot = {
  generated_at: string
  source: string
  totals: {
    stations: number
    bikes: number
    docks: number
    empty: number
    full: number
    out_of_service: number
  }
  stations: Station[]
}

export type Availability = 'empty' | 'low' | 'ok' | 'closed'

export function availability(station: Station): Availability {
  if (!station.renting) return 'closed'
  const bikes = station.bikes ?? 0
  if (bikes === 0) return 'empty'
  if (bikes <= 2) return 'low'
  return 'ok'
}

export const COLORS: Record<Availability, string> = {
  ok: '#1E6E8A',
  low: '#C98F2E',
  empty: '#A8432F',
  closed: '#8A9499',
}
