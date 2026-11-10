import { REPO_URL } from './config'

// Libellés affichés ; les valeurs viennent de reference/emission_factors.csv (injecté au build).
const LABELS: Record<string, string> = {
  voiture_thermique: 'Voiture thermique, seul à bord',
  voiture_electrique: 'Voiture électrique, seul à bord',
  bus_thermique: 'Bus thermique',
  bus_electrique: 'Bus électrique ou trolleybus',
  tramway: 'Tramway',
  metro: 'Métro',
  velo: 'Vélo',
  velo_electrique: 'Vélo à assistance électrique',
  marche: 'Marche',
}

const FACTORS = [...__EMISSION_FACTORS__].sort((a, b) => b.total - a.total)
const MAX = FACTORS[0]?.total ?? 1
const byMode = Object.fromEntries(FACTORS.map((f) => [f.mode, f]))

const grams = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 1 })
const wholeGrams = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 })
/** « 142 g », « 4,4 g », « 0,2 g » : une décimale seulement sous 10 g. */
const formatGrams = (value: number) => `${(value >= 10 ? wholeGrams : grams).format(value)} g`

const retrievedOn = FACTORS[0]
  ? // Date sans heure : formatée en UTC pour ne pas reculer d'un jour à l'ouest de Greenwich.
    new Intl.DateTimeFormat('fr-FR', { dateStyle: 'long', timeZone: 'UTC' }).format(
      new Date(FACTORS[0].retrievedOn),
    )
  : ''

const METHODOLOGY_URL = `${REPO_URL}/blob/main/docs/methodologie-co2.md`

export function EmissionFactors() {
  const car = byMode.voiture_thermique
  const tram = byMode.tramway
  if (!car || !tram) return null
  const ratio = Math.round(car.total / tram.total)

  return (
    <section aria-labelledby="co2-title">
      <h2 id="co2-title" className="mb-1.5 font-serif text-[1.3rem] font-medium italic">
        Ce que pèse un kilomètre
      </h2>
      <p className="text-encre-douce">
        Émissions de CO2 par personne et par kilomètre, fabrication du véhicule comprise.
      </p>
      <p className="mt-4 font-serif text-[1.35rem] leading-[1.25] text-balance">
        Seul en voiture, 1 km émet autant que{' '}
        <span className="font-semibold whitespace-nowrap text-rhone tabular-nums">{ratio} km</span> en
        tramway.
      </p>

      <ul className="mt-5 space-y-2.5">
        {FACTORS.map((f) => (
          <li key={f.mode}>
            <div className="flex items-baseline justify-between gap-3 text-[0.95rem]">
              <span>{LABELS[f.mode] ?? f.mode}</span>
              <span className="font-semibold whitespace-nowrap tabular-nums">{formatGrams(f.total)}</span>
            </div>
            <Bar usage={f.usage} construction={f.construction} />
          </li>
        ))}
      </ul>

      <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[0.85rem] text-encre-douce" aria-label="Légende">
        <li className="flex items-center gap-2">
          <span aria-hidden="true" className="inline-block h-2.5 w-4 rounded-sm bg-encre" />
          Usage (carburant, électricité)
        </li>
        <li className="flex items-center gap-2">
          <span aria-hidden="true" className="inline-block h-2.5 w-4 rounded-sm bg-gris" />
          Fabrication du véhicule
        </li>
      </ul>

      <details className="mt-5 text-[0.95rem]">
        <summary className="cursor-pointer font-bold">Hypothèses et limites</summary>
        <ul className="mt-2 list-disc space-y-1.5 pl-5 text-encre-douce">
          <li>
            Moyennes nationales de l'ADEME : il n'existe pas de facteurs publiés propres au réseau
            lyonnais.
          </li>
          <li>
            Pour les transports en commun, c'est une moyenne par voyageur ; à plusieurs en voiture, les
            émissions se partagent entre les occupants.
          </li>
          <li>
            La motorisation des bus TCL n'est pas publiée ligne par ligne : le comparateur retiendra le
            bus thermique, sauf pour les trolleybus.
          </li>
          <li>Pour Vélo'v, les stations et le rééquilibrage des vélos ne sont pas comptés.</li>
        </ul>
        <p className="mt-2">
          <a href={METHODOLOGY_URL}>Lire la méthodologie complète</a>
        </p>
      </details>

      <p className="mt-4 text-[0.82rem] text-encre-douce">
        Source : ADEME, Impact CO2 (Base Empreinte et modélisation de la voiture), facteurs au{' '}
        {retrievedOn}.
      </p>
    </section>
  )
}

/** Barre empilée : usage puis fabrication, à l'échelle du mode le plus émetteur. */
function Bar({ usage, construction }: { usage: number; construction: number }) {
  const width = (value: number) => `${(value / MAX) * 100}%`
  // Une valeur non nulle reste visible (2 px au minimum), même pour le vélo.
  const visible = (value: number) => (value > 0 ? '2px' : '0')
  return (
    <div aria-hidden="true" className="mt-1 flex h-2.5 overflow-hidden rounded-sm bg-pierre-fonce">
      <span className="bg-encre" style={{ width: width(usage), minWidth: visible(usage) }} />
      <span className="bg-gris" style={{ width: width(construction), minWidth: visible(construction) }} />
    </div>
  )
}
