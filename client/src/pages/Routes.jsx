import React, { useEffect, useState } from 'react'
import RouteDetail from '../components/RouteDetail'
import { getRoutes } from '../services/api'
import { useParams } from 'react-router-dom'

export default function RoutesPage() {
  const [routes, setRoutes] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const { routeId, stopOrder } = useParams()
  const [highlightStop, setHighlightStop] = useState(null)
  const [selected, setSelected] = useState(null)

  // === 當網址帶 routeId / stopOrder 時，自動選中 ===
  useEffect(() => {
    if (routes.length > 0 && routeId) {
      const found = routes.find(r =>
        String(r.id) === String(routeId) ||
        String(r.route_id) === String(routeId) ||
        String(r.key) === String(routeId) ||
        String(r.name) === String(routeId) // 有些 API 沒 id，就用 name 比對
      )
      if (found) {
        setSelected(found)
        if (stopOrder) {
          const stopNum = Number(stopOrder)
          if (!isNaN(stopNum)) {
            setHighlightStop(stopNum)
          }
        }
      }
    }
  }, [routes, routeId, stopOrder])

  // === 載入路線資料 ===
  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        setLoading(true)
        setError(null)
        const apiRoutes = await getRoutes()
        if (!cancelled) setRoutes(apiRoutes)
      } catch (e) {
        console.warn('API 取得路線失敗，改用本地資料', e)
        if (!cancelled) {
          const fallback = buildRoutesFromStations(stations).map((r) => ({
            ...r,
            source: 'static',
          }))
          setRoutes(fallback)
          setError('無法連線後端 API，已使用本地資料')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => { cancelled = true }
  }, [])

  // === 若 API 掛掉，從靜態站點重建路線 ===
  const buildRoutesFromStations = (rows) => {
    const map = new Map()
    rows.forEach((row) => {
      const name = row['路線名稱'] || '未命名路線'
      const direction = row['路向'] || ''
      const key = `${name} ${direction}`.trim()
      if (!map.has(key)) {
        map.set(key, {
          name,
          direction,
          key,
          sample: row,
        })
      }
    })
    return Array.from(map.values())
  }

  return (
    <div className="routes-page">
      <div className="page-header">
        <h2>路線列表</h2>
        <div className="muted" style={{ color: '#000' }}>
          點選路線以查看詳細資訊
        </div>
        {loading && <div className="muted">載入中...</div>}
        {error && <div className="muted" style={{ color: '#c25' }}>{error}</div>}
      </div>

      <div className="routes-list">
        {routes.map((r, idx) => (
          <div
            key={r.key || `${r.name}-${r.direction}-${idx}`}
            className="route-card route-card--animate"
            role="button"
            tabIndex={0}
            style={{ animationDelay: `${idx * 60}ms` }}
            onClick={() => {
              console.log(
                `[使用者選擇路線] ID: ${r.id || r.route_id || '(未知)'}, 名稱: ${r.name || '(未命名)'}, 方向: ${r.direction || '(未定義)'}`
              )
              setSelected(r)
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                console.log(
                  `[使用者選擇路線] ID: ${r.id || r.route_id || '(未知)'}, 名稱: ${r.name || '(未命名)'}, 方向: ${r.direction || '(未定義)'}`
                )
                setSelected(r)
              }
            }}
          >
            <div className="route-left">
              <div className="route-title">{r.name}</div>
              <div className="route-sub muted">
                {r.direction === '雙向' ? '折返線' :
                r.direction === '單向' ? '循環線' : r.direction}
              </div>
            </div>
            <div className="route-action muted">查看</div>
          </div>
        ))}
      </div>

      {selected && (
        <RouteDetail
          route={selected}
          highlightStop={highlightStop}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  )
}
