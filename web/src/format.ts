const numberFormat = new Intl.NumberFormat('fr-FR')

export const formatNumber = (value: number): string => numberFormat.format(value)

/** « 14 h 32 », à l'heure de Lyon quel que soit le fuseau du visiteur. */
export function formatTime(iso: string): string {
  const parts = new Intl.DateTimeFormat('fr-FR', {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Europe/Paris',
  }).formatToParts(new Date(iso))
  const hour = parts.find((p) => p.type === 'hour')?.value ?? ''
  const minute = parts.find((p) => p.type === 'minute')?.value ?? ''
  return `${hour} h ${minute}`
}

/** « il y a 6 min », « il y a 2 h ». */
export function formatAge(iso: string, now: number): string {
  const minutes = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60000))
  if (minutes < 1) return "à l'instant"
  if (minutes < 60) return `il y a ${minutes} min`
  return `il y a ${Math.floor(minutes / 60)} h`
}

export const plural = (count: number, singular: string, pluralForm: string): string =>
  count > 1 ? pluralForm : singular

/** Recherche insensible aux accents et à la casse : « croix rousse » trouve « CROIX-ROUSSE ». */
export const normalize = (text: string): string =>
  text
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-zA-Z0-9]+/g, ' ')
    .trim()
    .toLowerCase()

const SMALL_WORDS = new Set(['de', 'du', 'des', 'la', 'le', 'les', 'et', 'en', 'sur', 'sous', 'à', 'au', 'aux'])

/** Le flux publie les noms en majuscules : « 16 BVD DE LA CROIX-ROUSSE » → « 16 Bvd de la Croix-Rousse ». */
export function displayName(raw: string): string {
  const capitalize = (part: string) => part.charAt(0).toUpperCase() + part.slice(1)
  return raw
    .toLocaleLowerCase('fr-FR')
    .split(' ')
    .map((word, index) => {
      if (index > 0 && SMALL_WORDS.has(word)) return word
      // « d'armaillé » → « d'Armaillé », « croix-rousse » → « Croix-Rousse »
      const elided = word.match(/^([dl]')(.+)$/)
      if (elided) {
        const article = index > 0 ? elided[1] : capitalize(elided[1])
        return article + elided[2].split('-').map(capitalize).join('-')
      }
      return word.split('-').map(capitalize).join('-')
    })
    .join(' ')
}
