import { useCallback, useEffect, useState } from 'react'
import { REFRESH_MS, SNAPSHOT_URL } from './config'
import type { Snapshot } from './types'

type State =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; snapshot: Snapshot; checkedAt: number }

async function fetchSnapshot(): Promise<Snapshot> {
  // Paramètre anti-cache : le fichier change toutes les 15 minutes à la même adresse.
  const separator = SNAPSHOT_URL.includes('?') ? '&' : '?'
  const response = await fetch(`${SNAPSHOT_URL}${separator}t=${Date.now()}`)
  if (!response.ok) throw new Error(`Le serveur de données a répondu ${response.status}.`)
  return (await response.json()) as Snapshot
}

export function useSnapshot() {
  const [state, setState] = useState<State>({ status: 'loading' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    const load = () =>
      fetchSnapshot().then(
        (snapshot) => {
          if (!cancelled) setState({ status: 'ready', snapshot, checkedAt: Date.now() })
        },
        (error: unknown) => {
          if (cancelled) return
          // On garde les dernières données affichées si un rafraîchissement échoue.
          setState((previous) =>
            previous.status === 'ready'
              ? previous
              : { status: 'error', message: error instanceof Error ? error.message : String(error) },
          )
        },
      )
    void load()
    const timer = window.setInterval(() => void load(), REFRESH_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [attempt])

  const retry = useCallback(() => {
    setState({ status: 'loading' })
    setAttempt((n) => n + 1)
  }, [])

  return { state, retry }
}

/** Heure courante, rafraîchie toutes les 30 secondes (pour « il y a 6 min »). */
export function useNow(): number {
  const [now, setNow] = useState(0)
  useEffect(() => {
    const tick = () => setNow(Date.now())
    const timer = window.setInterval(tick, 30_000)
    const first = window.setTimeout(tick, 0)
    return () => {
      window.clearInterval(timer)
      window.clearTimeout(first)
    }
  }, [])
  return now
}
