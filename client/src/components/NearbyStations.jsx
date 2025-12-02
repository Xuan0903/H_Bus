import React, { useEffect, useMemo, useRef, useState } from 'react'
import { getStations } from '../services/api'   // ✅ 改成從 API 抓取站點

function haversine(a, b) {
  const toRad = (d) => (d * Math.PI) / 180
  const R = 6371000
  const dLat = toRad(b.lat - a.lat)
  const dLon = toRad(b.lng - a.lng)
  const lat1 = toRad(a.lat)
  const lat2 = toRad(b.lat)
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}

export default function NearbyStations({ onClose }) {
  const [loc, setLoc] = useState({ lat: 23.99302, lng: 121.603219, ok: false })
  const [err, setErr] = useState(null)
  const [ready, setReady] = useState(false)
  const mapRef = useRef(null)
  const elRef = useRef(null)
  const userLayerRef = useRef(null)
  const stopLayerRef = useRef(null)
  const overlayRef = useRef(null)
  const [selectedId, setSelectedId] = useState(null)

  // ✅ 站點資料
  const [stations, setStations] = useState([])

  useEffect(() => {
    getStations()
      .then((data) => {
        console.log("[NearbyStations] API 取得站點:", data)
        setStations(data)
      })
      .catch((e) => {
        console.warn("載入站點失敗", e)
        setErr("無法載入站點，請稍後再試")
      })
  }, [])

  const nearest = useMemo(() => {
    const me = { lat: loc.lat, lng: loc.lng }
    return stations
      .map((s, idx) => ({
        id: s.id || `${s.name}-${idx}`,
        name: s.name,
        route: s._raw?.route_name || '',
        dir: s._raw?.direction || '',
        lat: Number(s.lat),
        lng: Number(s.lng),
      }))
      .filter((x) => Number.isFinite(x.lat) && Number.isFinite(x.lng))
      .map((x) => ({ ...x, dist: haversine(me, x) }))
      .sort((a, b) => a.dist - b.dist)
      .slice(0, 5) // 取最近 5 筆
  }, [loc, stations])

  useEffect(() => {
    if (!('geolocation' in navigator)) {
      setErr('此裝置不支援定位，改用預設位置')
      return
    }
    const id = navigator.geolocation.getCurrentPosition(
      (pos) => {
        const { latitude, longitude } = pos.coords
        setLoc({ lat: latitude, lng: longitude, ok: true })
      },
      (e) => {
        console.warn('geolocation error', e)
        setErr('無法取得定位，改用預設位置')
      },
      { enableHighAccuracy: true, timeout: 6000, maximumAge: 10000 }
    )
    return () => { try { navigator.geolocation.clearWatch?.(id) } catch {} }
  }, [])

  useEffect(() => {
    import('leaflet').then((mod) => {
      if (!window.L) window.L = mod
      setReady(true)
    })
  }, [])

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose?.() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  useEffect(() => {
    if (!ready || !elRef.current || mapRef.current) return
    const L = window.L
    const map = L.map(elRef.current, { center: [loc.lat, loc.lng], zoom: 15 })
    L.tileLayer('https://wmts.nlsc.gov.tw/wmts/EMAP/default/GoogleMapsCompatible/{z}/{y}/{x}', { tileSize:256 }).addTo(map)
    L.tileLayer('https://wmts.nlsc.gov.tw/wmts/EMAP2/default/GoogleMapsCompatible/{z}/{y}/{x}', { tileSize:256, opacity:.9 }).addTo(map)
    mapRef.current = map
    userLayerRef.current = L.layerGroup().addTo(map)
    stopLayerRef.current = L.layerGroup().addTo(map)
  }, [ready])

  useEffect(() => {
    if (!ready || !mapRef.current) return
    const L = window.L
    const userLayer = userLayerRef.current
    userLayer.clearLayers()
    const me = L.circleMarker([loc.lat, loc.lng], { radius: 8, color: '#2563eb', weight: 3, fillColor: '#2563eb', fillOpacity: 0.6 }).addTo(userLayer)
    me.bindTooltip('我的位置', { direction: 'top' })
    mapRef.current.setView([loc.lat, loc.lng], 15)
  }, [ready, loc])

  useEffect(() => {
    if (!ready || !mapRef.current) return
    const L = window.L
    const layer = stopLayerRef.current
    layer.clearLayers()
    nearest.forEach((s, i) => {
      const icon = L.divIcon({ className: '', html: `<div class="stop-badge">${i + 1}</div>`, iconSize: [24, 24], iconAnchor: [12, 12] })
      L.marker([s.lat, s.lng], { icon }).addTo(layer).bindTooltip(`${s.name} · ${s.route}（${s.dir}）`, { direction: 'top' })
    })
  }, [ready, nearest])

  const handleBackdrop = (e) => {
    if (e.target === overlayRef.current) onClose?.()
  }

  return (
    <div ref={overlayRef} className="route-detail-overlay" role="dialog" aria-modal="true" onClick={handleBackdrop}>
      <div
          className="route-detail-panel"
          onClick={(e) => e.stopPropagation()}
          style={{
            maxHeight: "85vh",      // ⭐ 限制最高 85% 螢幕
            overflow: "hidden",     // ⭐ 超出不允許
            display: "flex",
            flexDirection: "column"
          }}
        >

        <div className="panel-head">
          <div>
            <div className="route-title">附近站點</div>
            <div className="muted small">依目前位置計算最近 5 站</div>
            {err && <div className="small" style={{ color:'#c25' }}>{err}</div>}
          </div>
          <div>
            <button className="btn" style={{ marginRight: 8 }} onClick={() => {
              if ('geolocation' in navigator) {
                navigator.geolocation.getCurrentPosition((pos) => {
                  setLoc({ lat: pos.coords.latitude, lng: pos.coords.longitude, ok: true })
                }, () => setErr('重新定位失敗'))
              } else {
                setErr('此裝置不支援定位')
              }
            }}>重新定位</button>
            <button className="btn" onClick={onClose} aria-label="關閉">關閉 ✕</button>
          </div>
        </div>

        <div
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              overflow: "hidden",
              gap: 10
            }}
          >
          <div ref={elRef} style={{ width:'100%', height: 320, borderRadius: 12, overflow:'hidden', border:'1px solid rgba(0,0,0,.06)' }} />

          <div
            className="list"
            style={{
              flex: 1,
              overflowY: "auto",
              paddingBottom: 10
            }}
          >

            {nearest.map((s, i) => (
              <div className={`item ${selectedId===s.id?'selected':''}`} key={s.id} data-station-id={s.id}>
                <div>
                  <div style={{ fontWeight:700 }}>{i + 1}. {s.name}</div>
                  <div className="item-desc">{(s.route || '').trim()}（{s.dir || ''}） · {Math.round(s.dist)} m</div>
                </div>
                <button className="btn" onClick={() => { setSelectedId(s.id); if (mapRef.current) mapRef.current.setView([s.lat, s.lng], 16) }}>地圖</button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
