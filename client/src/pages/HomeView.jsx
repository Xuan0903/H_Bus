import React, { useState, useEffect, useRef } from 'react'
import MyReservations from '../components/MyReservations'
import { getRoutes } from '../services/api'
import { getAllStatus } from '../services/api';
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

        // 載入總路線
        const routes = allRoutes.length ? allRoutes : await getRoutes()
        if (!allRoutes.length) setAllRoutes(routes)

        // --- 使用 Process_Route → All_Status ---
        const allStatus = await getAllStatus()

        const active = allStatus.filter(s =>
          s.vehicle_status === 'on_duty' &&
          s["當班位置"] !== "NONE"
        )

        const itemsCur = active.map(s => {
          const matchRoute = routes.find(r => Number(r.id) === Number(s.route_no))
          return {
            id: s.route_no,
            route: matchRoute?.name || `路線 ${s.route_no}`,
            directionLabel: `(${/返|回/.test(s.direction) ? '返' : '去'})`,
            stop: s["當班位置"],
            status: "當前所在",
            key: `${s.route_no}-${s.direction}`
          }
        })

        setArrivals(itemsCur)
        setLastUpdated(new Date())

      } catch (e) {
        setError('無法載入即將到站資料')
        console.warn('Home arrivals load error:', e)
      } finally {
        setLoading(false)
      }
    }

    refresh({ hard: true })
    return () => { cancelled = true }
  }, [tick])

  return (
    <main className="container">
      <div className="arrival-container">
        <div className="arrival-header arrival-header--row">
          <div className="arrival-header-left">
            <div className="arrival-header-title">當前車次所在站點</div>
            <div className="arrival-header-timer">
              {countdown === null
                ? '自動更新中'
                : <>自動更新倒數 <small>{countdown}</small> 秒</>}
            </div>
          </div>

          <button
            className="btn btn-blue arrival-header-btn"
            onClick={() => onAction('附近站點')}
          >
            附近站點
          </button>
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
              <div className="arrival-left arrival-left--nowrap" style={{ display: 'flex', flexDirection: 'column' }}>
                {/* 第一行：完整路線名稱 */}
                  <div className="route-name route-name--wrap" style={{ fontWeight: 600, fontSize: '0.95rem' }}>
                    {a.route}
                  </div>

                {/* 第二行：去/返 + 站點 */}
                  <div style={{ marginTop: 6, fontSize: '0.9rem', fontWeight: 500 }}>
                    <span style={{ color: '#0046BE' }}>
                      [{a.directionLabel.replace(/[()]/g,'')}]
                    </span>
                    <span style={{ color: '#FF8A00', marginLeft: 6 }}>
                      [{a.stop}]
                    </span>
                  </div>
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
