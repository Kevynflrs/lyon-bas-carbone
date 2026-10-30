import { useEffect, useRef } from 'react'
import { CircleMarker, MapContainer, Popup, TileLayer, useMap } from 'react-leaflet'
import type { CircleMarker as LeafletCircleMarker } from 'leaflet'
import { displayName, formatNumber, formatTime, plural } from './format'
import { availability, COLORS, type Station } from './types'

const LYON_CENTER: [number, number] = [45.757, 4.84]

function radius(station: Station): number {
  return 4 + Math.sqrt(station.capacity ?? 15) * 0.9
}

function FlyToSelection({
  station,
  markers,
}: {
  station: Station | null
  markers: React.RefObject<Map<string, LeafletCircleMarker>>
}) {
  const map = useMap()
  useEffect(() => {
    if (!station) return
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const target: [number, number] = [station.lat, station.lon]
    if (reduceMotion) map.setView(target, 16)
    else map.flyTo(target, 16, { duration: 0.8 })
    markers.current.get(station.id)?.openPopup()
  }, [station, map, markers])
  return null
}

export function StationMap({ stations, selected }: { stations: Station[]; selected: Station | null }) {
  const markers = useRef(new Map<string, LeafletCircleMarker>())

  return (
    <MapContainer
      center={LYON_CENTER}
      zoom={13}
      preferCanvas
      className="map h-full w-full"
      aria-label="Carte des stations"
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">contributeurs OpenStreetMap</a>'
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        maxZoom={19}
      />
      {stations.map((station) => {
        const kind = availability(station)
        return (
          <CircleMarker
            key={station.id}
            center={[station.lat, station.lon]}
            radius={radius(station)}
            ref={(marker) => {
              if (marker) markers.current.set(station.id, marker)
              else markers.current.delete(station.id)
            }}
            pathOptions={{
              color: kind === 'closed' ? COLORS.closed : '#FFFFFF',
              weight: kind === 'closed' ? 2 : 1.5,
              fillColor: COLORS[kind],
              fillOpacity: kind === 'closed' ? 0 : 0.92,
            }}
          >
            <Popup>
              <div className="flex flex-col gap-1">
                <p className="font-serif text-[1.05rem] font-semibold">{displayName(station.name)}</p>
                {station.renting ? (
                  <p>
                    <strong>{formatNumber(station.bikes ?? 0)}</strong>{' '}
                    {plural(station.bikes ?? 0, 'vélo', 'vélos')},{' '}
                    <strong>{formatNumber(station.docks ?? 0)}</strong>{' '}
                    {plural(station.docks ?? 0, 'place libre', 'places libres')}
                  </p>
                ) : (
                  <p>Station hors service</p>
                )}
                {station.last_reported && (
                  <p className="text-[0.82rem] text-encre-douce">
                    Relevé à {formatTime(station.last_reported)}
                  </p>
                )}
              </div>
            </Popup>
          </CircleMarker>
        )
      })}
      <FlyToSelection station={selected} markers={markers} />
    </MapContainer>
  )
}
