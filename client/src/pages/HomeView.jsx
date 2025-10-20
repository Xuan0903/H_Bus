import React, { useState, useEffect, useRef } from 'react'
import MyReservations from '../components/MyReservations'
import { getRoutes, getRouteStops } from '../services/api'
import { getCarPositions } from '../services/api'
import { useNavigate } from 'react-router-dom'

export default function HomeView({ onAction, user, onNavigateRoutes }) {
  const [allRoutes, setAllRoutes] = useState([])
  const [searchOpen, setSearchOpen] = useState(false)
  const [query, setQuery] = useState('')
  const navigate = useNavigate()
  const [announcements, setAnnouncements] = useState([])
  const [arrivals, setArrivals] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [tick, setTick] = useState(0)
  const [lastUpdated, setLastUpdated] = useState(null)
  const [pressedKey, setPressedKey] = useState(null)
  const AUTO_REFRESH_MS = 30000
  const interactingRef = useRef(false)
  const interactTimer = useRef(null)
  const [countdown, setCountdown] = useState(30)
  const nextRefreshRef = useRef(Date.now() + AUTO_REFRESH_MS)

  useEffect(() => {
    nextRefreshRef.current = Date.now() + AUTO_REFRESH_MS
    setCountdown(Math.ceil(AUTO_REFRESH_MS / 1000))
  }, [])

  useEffect(() => {
    const markInteract = () => {
      interactingRef.current = true
      clearTimeout(interactTimer.current)
      interactTimer.current = setTimeout(() => (interactingRef.current = false), 900)
    }
    const onScroll = () => markInteract()
    const onTouchStart = () => markInteract()
    const onTouchEnd = () => markInteract()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('touchstart', onTouchStart, { passive: true })
    window.addEventListener('touchend', onTouchEnd, { passive: true })
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('touchstart', onTouchStart)
      window.removeEventListener('touchend', onTouchEnd)
      clearTimeout(interactTimer.current)
    }
  }, [])

  useEffect(() => {
    nextRefreshRef.current = Date.now() + AUTO_REFRESH_MS
    setCountdown(Math.ceil(AUTO_REFRESH_MS / 1000))

    const id = setInterval(() => {
      if (document.hidden) return
      if (interactingRef.current) return
      if (searchOpen) return

      nextRefreshRef.current = Date.now() + AUTO_REFRESH_MS
      setTick((t) => (t + 1) % 1_000_000)
      setCountdown(Math.ceil(AUTO_REFRESH_MS / 1000))
    }, AUTO_REFRESH_MS)

    return () => clearInterval(id)
  }, [searchOpen])

  useEffect(() => {
    const tickCountdown = () => {
      if (document.hidden) return
      const remain = nextRefreshRef.current - Date.now()
      setCountdown(Math.max(0, Math.ceil(remain / 1000)))
    }

    tickCountdown()
    const timer = setInterval(tickCountdown, 1000)
    return () => clearInterval(timer)
  }, [searchOpen])

    // 載入服務公告
  useEffect(() => {
    const loadAnnouncements = async () => {
      try {
        const res = await fetch('/api/announcements')
        const json = await res.json()
        if (json.status === 'success' && Array.isArray(json.data)) {
          setAnnouncements(json.data)
        } else {
          console.warn('公告資料格式異常', json)
        }
      } catch (err) {
        console.error('載入公告失敗', err)
      }
    }

    loadAnnouncements()
  }, [])


  useEffect(() => {
    let cancelled = false
    const refresh = async ({ hard = false } = {}) => {
      try {
        if (hard) setLoading(true)
        setError(null)
        const routes = allRoutes.length ? allRoutes : await getRoutes()
        if (!allRoutes.length) setAllRoutes(routes)
        const pick = routes.slice(0, 3)
        const perRoute = await Promise.all(
          pick.map(async (r) => {
            let stops = []
            try {
              stops = await getRouteStops(r.id, '去程')
            } catch {
              try { stops = await getRouteStops(r.id, '回程') } catch {}
            }
            return { route: r, stops }
          })
        )
        const items = perRoute.flatMap(({ route: r, stops }) => {
          if (!stops || stops.length === 0) return []
          const lastEta = stops.reduce((m, s) => Math.max(m, Number(s.etaFromStart) || 0), 0)
          const cycle = Math.max(lastEta + 5, stops.length * 3) || 20
          const nowMin = (Date.now() / 60000) % cycle
          const annotate = (eta) => {
            const delta = eta - nowMin
            if (delta <= -1.0) return { label: '已過站', etaText: null, score: 999 }
            if (delta <= 0.25) return { label: '到站中', etaText: '0 分鐘', score: 0 }
            if (delta <= 5.0) return { label: '即將到站', etaText: `${Math.ceil(delta)} 分鐘`, score: delta }
            return { label: '等待中', etaText: `${Math.ceil(delta)} 分鐘`, score: delta + 100 }
          }
          const enriched = stops
            .map((s, idx) => {
              const eta = Number(s.etaFromStart ?? (idx * 3))
              const a = annotate(eta)
              return {
                route: r.name,
                directionLabel: r.direction?.includes('回') ? '(回)' : '(去)',
                stop: s.stopName || `第${(s.order ?? (idx + 1))}站`,
                eta: a.etaText || '-',
                status: a.label,
                score: a.score,
                key: `${r.id}-${s.order ?? idx}`,
              }
            })
            .sort((a, b) => a.score - b.score)
          return enriched.slice(0, 1)
        })
        if (!cancelled) {
          const next = items.slice(0, 3)
          const a = JSON.stringify(next)
          const b = JSON.stringify(arrivals)
          if (a !== b) setArrivals(next)
          setLastUpdated(new Date())
          try {
            const res = await fetch('/api/GIS_AllFast')
            const json = await res.json()

            let cars = []
            if (Array.isArray(json.data)) {
              cars = json.data
            } else if (json && typeof json === 'object' && json.route) {
              const keys = Object.keys(json.route || {})
              cars = keys.map((k) => ({
                route: json.route[k],
                X: json.Y?.[k] ?? null, // 這裡反過來取
                Y: json.X?.[k] ?? null, // 這裡反過來取
                direction: json.direction?.[k] ?? '',
                Current_Location: json.Current_Location?.[k] ?? ''
              }))
            }

            const pickCur = routes.slice(0, 3)
            const normDir = (d) => {
              const t = String(d || '').trim()
              if (/返|回|1/.test(t)) return '返程'
              if (/去|往|0/.test(t)) return '去程'
              return t
            }
            const itemsCur = pickCur.map((r) => {
              const routeCars = (cars || []).filter(
                c => String(c.route) === String(r.id) || String(c.route) === String(r.name)
              )

              // 有多方向時，自動挑選有座標的；若都沒有，就拿第一筆
              let car = null
              if (routeCars.length > 0) {
                // 優先：有座標的（代表正在行駛）
                car = routeCars.find(c => c.X != null && c.Y != null) || routeCars[0]
              }

              return {
                id: r.id,
                route: r.name,
                directionLabel: car ? `(${normDir(car.direction) === '返程' ? '返' : '去'})` : '',
                stop: car?.Current_Location || car?.nearest_stop_name || '—',
                eta: '',
                status: car && car.X != null && car.Y != null ? '當前所在' : '未發車',
                key: `${r.id}-${car?.station_id || 'none'}`,
              }
            })
            .filter(a => a.stop && a.stop !== '—') // ✅ 新增：只顯示有站點名稱的
            if (!cancelled) {
              setArrivals(itemsCur)
              setLastUpdated(new Date())
            }
          } catch {}
        }
      } catch (e) {
        if (!cancelled) {
          setError('無法載入即將到站資料')
          console.warn('Home arrivals load error:', e)
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }
    refresh({ hard: true })
    return () => { cancelled = true }
  }, [tick]) // eslint-disable-line

  return (
    <main className="container">
      {/* 搜尋區 */}
      <section className="search-section">
        {!searchOpen ? (
          <div
            className="search-input"
            role="button"
            tabIndex={0}
            onClick={() => setSearchOpen(true)}
            onKeyDown={(e) => e.key === 'Enter' && setSearchOpen(true)}
          >
            搜尋路線、站點或目的地
          </div>
        ) : (
          <div className="search-input" style={{ padding: 10 }}>
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="輸入路線名稱關鍵字"
              className="search-field"
              onKeyDown={(e) => { if (e.key === 'Escape') setSearchOpen(false) }}
            />
            <div className="search-suggestions">
              {allRoutes && query.trim() !== '' ? (
                allRoutes
                  .filter((r) => (r.name || '').toLowerCase().includes(query.trim().toLowerCase()))
                  .slice(0, 10)
                  .map((r) => (
                    <div
                      key={r.key}
                      className="suggest-item"
                      role="button"
                      tabIndex={0}
                      onClick={() => { 
                        setSearchOpen(false); 
                        navigate(`/routes/${r.id}`)
                      }}
                      onKeyDown={(e) => { if (e.key === 'Enter') { setSearchOpen(false); onNavigateRoutes && onNavigateRoutes() } }}
                    >
                      <div className="suggest-name">{r.name}</div>
                      <div className="muted small">{r.direction}</div>
                    </div>
                  ))
              ) : (
                <div className="muted small">輸入關鍵字以搜尋路線</div>
              )}
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              <button className="btn" onClick={() => setSearchOpen(false)}>取消</button>
              <button className="btn btn-blue" onClick={() => navigate('/routes')}>
                查看全部路線
              </button>
            </div>
          </div>
        )}

        <div className="search-actions">
          <button className="btn btn-blue" onClick={() => onAction('附近站點')}>附近站點</button>
          <button className="btn btn-orange" onClick={() => navigate('/routes')}>常用路線</button>
        </div>
      </section>

      {/* 外層白底父容器 */}
      <div className="arrival-container">
        <div className="arrival-header">
          <div className="arrival-header-title">當前車次所在站點</div>
          <div className="arrival-header-timer">
            {searchOpen || countdown === null
              ? '自動更新中'
              : <>自動更新倒數 <small>{countdown}</small> 秒</>}
          </div>
        </div>

        <div className="arrival-list">
          {loading && <div className="muted small">載入中</div>}
          {error && <div className="muted small" style={{ color: '#c25' }}>{error}</div>}
          {!loading && arrivals.map((a) => (
            <div
              key={a.key}
              className={`arrival-item arrival-item--tight ${pressedKey === a.key ? 'is-pressed' : ''}`}
              role="button"
              tabIndex={0}
              onPointerDown={() => setPressedKey(a.key)}
              onPointerUp={() => setPressedKey(null)}
              onPointerCancel={() => setPressedKey(null)}
              onPointerLeave={() => setPressedKey(null)}
              onClick={() => navigate(`/routes/${a.id}`)}
              onKeyDown={(e) => e.key === 'Enter' && navigate(`/routes/${a.id}`)}
            >
              <div className="arrival-left arrival-left--nowrap">
                <div className="route-line">
                  <div className="route-name route-name--wrap">
                    {a.route} {a.directionLabel}
                  </div>
                </div>
              </div>
              <div className="arrival-right">
                <div className="eta eta--right">{a.stop}</div>
              </div>
            </div>
          ))}
          {!loading && arrivals.length === 0 && !error && (
            <div className="muted small">目前沒有車次位置資訊</div>
          )}
        </div>
      </div>


      <MyReservations user={user} filterExpired={true} />
      {/* 服務公告 */}
      <section className="card">
        <div className="card-title"><span>服務公告</span></div>
        <div className="card-body">
          <div className="announcement">
            {announcements.length === 0 ? (
              <div className="muted small">目前沒有公告</div>
            ) : (
              announcements.map((a) => (
                <div key={a.id} className="announce-item">
                  <strong>{a.title}</strong>
                  <div className="muted small">{a.content}</div>
                </div>
              ))
            )}
          </div>
        </div>
      </section>
    </main>
  )
}
