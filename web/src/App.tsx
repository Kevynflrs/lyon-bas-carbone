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
    <div className="layout">
      <main className="panel">
        <header className="brand">
          <h1>Lyon bas carbone</h1>
          <p className="tagline">Se déplacer à Lyon en émettant le moins de CO2 possible.</p>
        </header>

        {state.status === 'loading' && <p className="status">Chargement des stations…</p>}

        {state.status === 'error' && (
          <div className="status status-error" role="alert">
            <p>
              Les disponibilités n'ont pas pu être chargées. {state.message} Le fichier est mis à jour
              toutes les 15 minutes : réessayez dans un instant.
            </p>
            <button type="button" onClick={retry}>
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

        <section className="next" aria-labelledby="next-title">
          <h2 id="next-title">Bientôt : comparer un trajet</h2>
          <p>
            Pour un trajet dans la métropole, le temps, la fiabilité et le CO2 émis en transports en
            commun, en Vélo'v, à pied et en voiture. Y compris quand la marche ou le vélo font mieux que
            le tram.
          </p>
        </section>

        <footer className="credits">
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

      <div className="map-wrap">
        <StationMap stations={stations} selected={selected} />
      </div>
    </div>
  )
}

function LiveSentence({ snapshot, checkedAt }: { snapshot: Snapshot; checkedAt: number }) {
  const { totals, generated_at } = snapshot
  const now = Math.max(useNow(), checkedAt)
  const stale = now - new Date(generated_at).getTime() > STALE_AFTER_MS

  return (
    <section className="live" aria-live="polite">
      <p className="sentence">
        En ce moment, <span className="figure">{formatNumber(totals.bikes)}</span>{' '}
        {plural(totals.bikes, 'vélo attend', 'vélos attendent')} dans{' '}
        <span className="figure">{formatNumber(totals.stations - totals.out_of_service)}</span> stations.
      </p>
      <p className="detail">
        {formatNumber(totals.empty)} {plural(totals.empty, 'station est vide', 'stations sont vides')},{' '}
        {formatNumber(totals.full)} {plural(totals.full, 'est pleine', 'sont pleines')} et{' '}
        {formatNumber(totals.out_of_service)} {plural(totals.out_of_service, 'est', 'sont')} hors service.
      </p>
      <p className={stale ? 'freshness freshness-stale' : 'freshness'}>
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
    <section className="search" aria-labelledby="search-label">
      <label id="search-label" htmlFor="station-query">
        Trouver une station
      </label>
      <input
        id="station-query"
        type="search"
        placeholder="Bellecour, Croix-Rousse, Part-Dieu…"
        autoComplete="off"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      {normalize(query).length >= 2 && results.length === 0 && (
        <p className="search-empty">Aucune station ne correspond à « {query} ».</p>
      )}
      {results.length > 0 && (
        <ul className="results">
          {results.map((station) => (
            <li key={station.id}>
              <button type="button" onClick={() => onSelect(station)}>
                <span
                  className="dot"
                  style={{ background: COLORS[availability(station)] }}
                  aria-hidden="true"
                />
                <span className="result-name">{displayName(station.name)}</span>
                <span className="result-count">
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

function Legend() {
  const items = [
    { kind: 'ok', label: '3 vélos ou plus' },
    { kind: 'low', label: '1 ou 2 vélos' },
    { kind: 'empty', label: 'Aucun vélo' },
    { kind: 'closed', label: 'Hors service' },
  ] as const
  return (
    <section className="legend" aria-label="Légende de la carte">
      <ul>
        {items.map(({ kind, label }) => (
          <li key={kind}>
            <span
              className={kind === 'closed' ? 'dot dot-hollow' : 'dot'}
              style={kind === 'closed' ? { borderColor: COLORS.closed } : { background: COLORS[kind] }}
              aria-hidden="true"
            />
            {label}
          </li>
        ))}
      </ul>
      <p>La taille d'un point suit la capacité de la station.</p>
    </section>
  )
}
