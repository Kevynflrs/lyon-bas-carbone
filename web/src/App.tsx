import { useMemo, useState } from 'react'
import { REPO_URL, STALE_AFTER_MS } from './config'
import { displayName, formatAge, formatNumber, formatTime, normalize, plural } from './format'
import { StationMap } from './StationMap'
import { availability, COLORS, type Snapshot, type Station } from './types'
import { useNow, useSnapshot } from './useSnapshot'

export default function App() {
  const { state, retry } = useSnapshot()
  const [selected, setSelected] = useState<Station | null>(null)
  const stations = state.status === 'ready' ? state.snapshot.stations : []

  return (
    <div className="grid min-h-screen md:grid-cols-[minmax(340px,440px)_1fr]">
      <main className="flex flex-col gap-7 px-4 py-6 md:max-h-screen md:gap-9 md:overflow-y-auto md:border-r md:border-pierre-fonce md:px-9 md:pt-10 md:pb-8">
        <header>
          <h1 className="font-serif text-[1.35rem] font-semibold tracking-[0.01em]">Lyon bas carbone</h1>
          <p className="mt-0.5 text-[0.95rem] text-encre-douce">
            Se déplacer à Lyon en émettant le moins de CO2 possible.
          </p>
        </header>

        {state.status === 'loading' && <p>Chargement des stations…</p>}

        {state.status === 'error' && (
          <div role="alert" className="border-l-4 border-brique bg-brique-pale px-4 py-4">
            <p className="mb-3">
              Les disponibilités n'ont pas pu être chargées. {state.message} Le fichier est mis à jour
              toutes les 15 minutes : réessayez dans un instant.
            </p>
            <button
              type="button"
              onClick={retry}
              className="cursor-pointer rounded border border-encre px-3.5 py-1.5 hover:bg-encre hover:text-pierre"
            >
              Réessayer
            </button>
          </div>
        )}

        {state.status === 'ready' && (
          <>
            <LiveSentence snapshot={state.snapshot} checkedAt={state.checkedAt} />
            <StationSearch stations={stations} onSelect={setSelected} />
            <Legend />
          </>
        )}

        <section aria-labelledby="next-title">
          <h2 id="next-title" className="mb-1.5 font-serif text-[1.3rem] font-medium italic">
            Bientôt : comparer un trajet
          </h2>
          <p className="text-encre-douce">
            Pour un trajet dans la métropole, le temps, la fiabilité et le CO2 émis en transports en
            commun, en Vélo'v, à pied et en voiture. Y compris quand la marche ou le vélo font mieux que
            le tram.
          </p>
        </section>

        <footer className="mt-auto space-y-1.5 border-t border-pierre-fonce pt-5 text-[0.82rem] text-encre-douce">
          <p>
            Données : Métropole de Lyon et JCDecaux (Licence Ouverte 2.0), collectées toutes les 15
            minutes par un pipeline Python open source.
          </p>
          <p>Projet indépendant, sans lien avec la Métropole de Lyon, SYTRAL Mobilités ou JCDecaux.</p>
          <p>
            <a href={REPO_URL}>Voir le code sur GitHub</a>
          </p>
        </footer>
      </main>

      {/* Sur mobile, la carte passe au-dessus du texte. */}
      <div className="order-first h-[52vh] md:sticky md:top-0 md:order-none md:h-screen">
        <StationMap stations={stations} selected={selected} />
      </div>
    </div>
  )
}

function LiveSentence({ snapshot, checkedAt }: { snapshot: Snapshot; checkedAt: number }) {
  const { totals, generated_at } = snapshot
  const now = Math.max(useNow(), checkedAt)
  const stale = now - new Date(generated_at).getTime() > STALE_AFTER_MS
  const figure = 'font-semibold whitespace-nowrap text-rhone tabular-nums lining-nums'

  return (
    <section aria-live="polite">
      <p className="font-serif text-[clamp(1.9rem,1.2rem_+_1.6vw,2.6rem)] leading-[1.18] font-medium text-balance">
        En ce moment, <span className={figure}>{formatNumber(totals.bikes)}</span>{' '}
        {plural(totals.bikes, 'vélo attend', 'vélos attendent')} dans{' '}
        <span className={figure}>{formatNumber(totals.stations - totals.out_of_service)}</span> stations.
      </p>
      <p className="mt-4 max-w-[34em]">
        {formatNumber(totals.empty)} {plural(totals.empty, 'station est vide', 'stations sont vides')},{' '}
        {formatNumber(totals.full)} {plural(totals.full, 'est pleine', 'sont pleines')} et{' '}
        {formatNumber(totals.out_of_service)} {plural(totals.out_of_service, 'est', 'sont')} hors service.
      </p>
      <p className={`mt-3 text-[0.9rem] ${stale ? 'text-brique' : 'text-encre-douce'}`}>
        Données de {formatTime(generated_at)} ({formatAge(generated_at, now)}).{' '}
        {stale
          ? 'La collecte a pris du retard : les chiffres ne reflètent peut-être plus la situation.'
          : 'Mises à jour toutes les 15 minutes.'}
      </p>
    </section>
  )
}

function StationSearch({ stations, onSelect }: { stations: Station[]; onSelect: (s: Station) => void }) {
  const [query, setQuery] = useState('')
  const results = useMemo(() => {
    const needle = normalize(query)
    if (needle.length < 2) return []
    return stations.filter((s) => normalize(s.name).includes(needle)).slice(0, 6)
  }, [query, stations])

  return (
    <section aria-labelledby="search-label">
      <label id="search-label" htmlFor="station-query" className="mb-1.5 block font-bold">
        Trouver une station
      </label>
      <input
        id="station-query"
        type="search"
        placeholder="Bellecour, Croix-Rousse, Part-Dieu…"
        autoComplete="off"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        className="w-full rounded border border-[#b9c3c0] bg-white px-3 py-2.5 text-encre placeholder:text-[#7d8a90]"
      />
      {normalize(query).length >= 2 && results.length === 0 && (
        <p className="mt-2.5 text-encre-douce">Aucune station ne correspond à « {query} ».</p>
      )}
      {results.length > 0 && (
        <ul className="mt-2">
          {results.map((station) => (
            <li key={station.id}>
              <button
                type="button"
                onClick={() => onSelect(station)}
                className="grid w-full cursor-pointer grid-cols-[auto_1fr_auto] items-center gap-2.5 border-b border-pierre-fonce px-1.5 py-2 text-left hover:bg-pierre-fonce"
              >
                <Dot color={COLORS[availability(station)]} />
                <span className="truncate">{displayName(station.name)}</span>
                <span className="text-encre-douce tabular-nums">
                  {station.renting
                    ? `${formatNumber(station.bikes ?? 0)} ${plural(station.bikes ?? 0, 'vélo', 'vélos')}`
                    : 'hors service'}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function Dot({ color, hollow = false }: { color: string; hollow?: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={`inline-block size-3 shrink-0 rounded-full ${hollow ? 'border-2' : ''}`}
      style={hollow ? { borderColor: color } : { background: color }}
    />
  )
}

function Legend() {
  const items = [
    { kind: 'ok', label: '3 vélos ou plus' },
    { kind: 'low', label: '1 ou 2 vélos' },
    { kind: 'empty', label: 'Aucun vélo' },
    { kind: 'closed', label: 'Hors service' },
  ] as const
  return (
    <section aria-label="Légende de la carte">
      <ul className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-[0.92rem]">
        {items.map(({ kind, label }) => (
          <li key={kind} className="flex items-center gap-2">
            <Dot color={COLORS[kind]} hollow={kind === 'closed'} />
            {label}
          </li>
        ))}
      </ul>
      <p className="mt-2.5 text-[0.85rem] text-encre-douce">
        La taille d'un point suit la capacité de la station.
      </p>
    </section>
  )
}
