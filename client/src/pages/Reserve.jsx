import React, { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getStations } from '../services/api'

async function ensureLeafletLoaded() {
  if (window.L) return window.L
  const mod = await import('leaflet')
  const L = mod.default ?? mod
  window.L = L
  return L
}

async function ensurePolylineDecorator() {
  if (window.L && window.L.polylineDecorator) return true
  await import('leaflet-polylinedecorator')
  return true
}

async function osrmRouteBetween(a, b) {
  const coords = `${a[1]},${a[0]};${b[1]},${b[0]}`
  const url = `https://router.project-osrm.org/route/v1/driving/${coords}?overview=full&geometries=geojson`
  const r = await fetch(url)
  if (!r.ok) throw new Error('OSRM fail')
  const j = await r.json()
  if (!(j.routes && j.routes[0])) throw new Error('No route')
  return j.routes[0]
}

function drawRouteWithArrows(L, layer, geojson) {
  const stroke = L.geoJSON(geojson, {
    style: { color: '#2563eb', weight: 7, opacity: .98, lineCap: 'round', lineJoin: 'round' }
  }).addTo(layer)
  try {
    if (L.polylineDecorator) {
      const poly = stroke.getLayers()[0]
      if (poly) {
        L.polylineDecorator(poly, {
          patterns: [{ offset: 0, repeat: '48px', symbol: L.Symbol.arrowHead({ pixelSize: 11, pathOptions: { color: '#2563eb', weight: 6, opacity: 0.95 } }) }]
        }).addTo(layer)
      }
    }
  } catch { }
  return stroke
}

// 工具：產生五分鐘間隔時間
function generateTimeOptions(selectedDateStr) {
  const options = []
  if (!selectedDateStr) return options

  const d = new Date(selectedDateStr)
  const day = d.getDay() // 0=週日, 6=週六
  const isWeekend = (day === 0 || day === 6)

  const startHour = isWeekend ? 10 : 9
  const endHour = isWeekend ? 15 : 16
  const endMinute = isWeekend ? 30 : 30

  for (let h = startHour; h <= endHour; h++) {
    for (let m = 0; m < 60; m += 5) {
      if (h === endHour && m > endMinute) break
      const hh = String(h).padStart(2, '0')
      const mm = String(m).padStart(2, '0')
      options.push(`${hh}:${mm}`)
    }
  }
  return options
}


function getEarliestDate() {
  const d = new Date()
  d.setDate(d.getDate() + 1) // 從明天開始
  return d
}

function getLatestDate() {
  const d = new Date()
  d.setMonth(d.getMonth() + 1) // 一個月後
  return d
}

export default function ReservePage({ user, onRequireLogin }) {
  const navigate = useNavigate()
  const [stations, setStations] = useState([])
  const [fromId, setFromId] = useState('')
  const [toId, setToId] = useState('')
  const [whenDate, setWhenDate] = useState('')
  const [whenTime, setWhenTime] = useState('')
  const [when, setWhen] = useState('')
  const [people, setPeople] = useState(1)
  const [hint, setHint] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const isLoggedIn = Boolean(user)
  const mapEl = useRef(null)
  const mapRef = useRef(null)
  const routeLayerRef = useRef(null)

  // 載入站點 API
  useEffect(() => {
    let cancelled = false
    getStations().then((rows) => {
      if (!cancelled) setStations(rows)
    }).catch((e) => console.warn('取得站點失敗', e))
    return () => { cancelled = true }
  }, [])

  // Leaflet 地圖初始化
  useEffect(() => {
    let destroyed = false
    ensureLeafletLoaded().then((L) => {
      if (destroyed || !mapEl.current) return
      const map = L.map(mapEl.current, { center: [23.99302, 121.603219], zoom: 14 })
      mapRef.current = map
      L.tileLayer('https://wmts.nlsc.gov.tw/wmts/EMAP/default/GoogleMapsCompatible/{z}/{y}/{x}', { tileSize: 256 }).addTo(map)
      routeLayerRef.current = L.layerGroup().addTo(map)
    })
    return () => {
      destroyed = true
      if (mapRef.current) {
        mapRef.current.remove()
        mapRef.current = null
      }
    }
  }, [])

  // 日期+時間組合成完整 datetime
  useEffect(() => {
    if (whenDate && whenTime) {
      setWhen(`${whenDate}T${whenTime}:00`)
    }
  }, [whenDate, whenTime])

  async function drawRoute(from, to) {
    if (!mapRef.current || !routeLayerRef.current) return
    const L = window.L
    const layer = routeLayerRef.current
    layer.clearLayers()
    try {
      await ensurePolylineDecorator()
      const result = await osrmRouteBetween([from.lat, from.lng], [to.lat, to.lng])
      if (result && result.geometry) {
        const stroke = drawRouteWithArrows(L, layer, result.geometry)
        mapRef.current.fitBounds(stroke.getBounds(), { padding: [30, 30], animate: false })
        return
      }
    } catch (e) {
      console.warn('OSRM 繪製失敗，改用直線', e)
    }
    const poly = L.polyline([[from.lat, from.lng], [to.lat, to.lng]], { color: '#94a3b8', weight: 4, opacity: 0.85 }).addTo(layer)
    mapRef.current.fitBounds(poly.getBounds(), { padding: [30, 30], animate: false })
  }

  function validateSelection() {
    setError('')
    const from = stations.find((s) => String(s.id) === String(fromId))
    const to = stations.find((s) => String(s.id) === String(toId))
    if (!from || !to) { setError('請選擇出發與到達站'); return null }
    if (String(fromId) === String(toId)) { setError('出發與到達站不能相同'); return null }
    return { from, to }
  }

  async function handleViewRoute(e) {
    e.preventDefault()
    const v = validateSelection()
    if (!v) return
    setLoading(true)
    try {
      await drawRoute(v.from, v.to)
    } finally {
      setLoading(false)
    }
  }

  async function handleSubmit(e) {
    e.preventDefault()
    const v = validateSelection()
    if (!v) return

    if (!whenDate || !whenTime) {
      setError("請選擇日期與時間")
      return
    }

    // 小工具：判斷空字串/空白
    const isBlank = (x) => {
      if (x == null) return true
      const s = String(x).trim().toLowerCase()
      return s === "" || s === "none" || s === "null" || s === "undefined"
    }

    // 確認 user 結構
    console.log("ReservePage user:", user)
    const uid = user?.user_id || user?.id
    if (!uid) {
      setError("找不到使用者 ID，請重新登入")
      return
    }

    // ✅ 驗證必填聯絡資料（Email 與手機）
    const hasEmail = !isBlank(user?.email)
    const hasPhone = !isBlank(user?.phone)
    if (!hasEmail || !hasPhone) {
      setError("請先於個人資料填寫『Email』與『手機號碼』後再預約。")
      // 可選：導去個人頁面讓他直接補資料
      // navigate("/profile", { state: { toast: "請先填寫 Email 與手機號碼" } })
      return
    }

    // 格式化時間 (ISO)
    const bookingTime = `${whenDate}T${whenTime}:00`

    setLoading(true)
    try {
      const resp = await fetch("/api/reservation", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: String(uid),                     // 後端若用 string 型別就保險轉字串
          booking_time: bookingTime,
          booking_number: String(people),           // 同上
          booking_start_station_name: v.from.name,
          booking_end_station_name: v.to.name,
        }),
      })

      if (!resp.ok) {
        const msg = await resp.text()
        throw new Error(`API 錯誤 ${resp.status}: ${msg}`)
      }

      const data = await resp.json()
      console.log("Reservation success:", data)

      navigate("/profile?tab=reservations", {
        state: { toast: "預約成功，等待審核。" },
      })
    } catch (err) {
      console.error("Reservation failed:", err)
      setError(err.message || "送出預約失敗")
    } finally {
      setLoading(false)
    }
  }

  function validateReservationDateTime(dateStr, timeStr) {
  if (!dateStr || !timeStr) return { ok: false, msg: "請選擇日期與時間" }

  const selected = new Date(`${dateStr}T${timeStr}:00`)

  const earliest = getEarliestDate()
  const latest = getLatestDate()

  if (selected < earliest || selected > latest) {
    return { ok: false, msg: "預約日期必須在明天到一個月內" }
  }

  // 檢查「前一天 17:00 截止」
  const deadline = new Date(selected)
  deadline.setDate(deadline.getDate() - 1)
  deadline.setHours(17, 0, 0, 0)

  const now = new Date()
  if (now > deadline) {
    return { ok: false, msg: "必須在前一天下午五點前完成預約" }
  }

  return { ok: true }
  }

  if (!isLoggedIn) {
    return (
      <div className="container">
        <section className="card">
          <div className="card-title"><span>預約系統</span></div>
          <div className="card-body">
            <div className="muted">請先登入才能使用預約功能。</div>
            <button className="btn btn-blue" onClick={onRequireLogin}>立即登入</button>
          </div>
        </section>
      </div>
    )
  }

  return (
    <div className="container">
      <section className="card">
        <div className="card-title"><span>預約系統</span></div>
        <div className="card-body">
          <form onSubmit={handleSubmit} style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
            <div>
              <div className="muted small">站點 1（出發）</div>
              <select className="search-field" value={fromId} onChange={(e) => setFromId(e.target.value)}>
                <option value="">起點</option>
                {stations.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div>
              <div className="muted small">站點 2（到達）</div>
              <select className="search-field" value={toId} onChange={(e) => setToId(e.target.value)}>
                <option value="">迄點</option>
                {stations.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div>
              <div className="muted small">預約日期</div>
              <input
                type="date"
                className="search-field"
                value={whenDate}
                min={getEarliestDate().toISOString().split("T")[0]}
                max={getLatestDate().toISOString().split("T")[0]}
                onChange={(e) => setWhenDate(e.target.value)}
              />
            </div>
            <div>
              <div className="muted small">預約時間</div>
              <select
                className="search-field"
                value={whenTime}
                onChange={(e) => setWhenTime(e.target.value)}
                disabled={!whenDate}
              >
                <option value="">搭乘時間</option>
                {generateTimeOptions(whenDate).map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <div className="muted small">人數</div>
              <select className="search-field" value={people} onChange={(e) => setPeople(e.target.value)}>
                {[1,2,3,4].map(n => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'end', flexWrap: 'wrap' }}>
              <button className="btn" onClick={handleViewRoute} disabled={loading}>
                {loading ? '處理中' : '查看路線'}
              </button>
              <button className="btn btn-orange" type="submit" disabled={loading || !fromId || !toId || !when}>
                {loading ? '處理中' : '送出預約'}
              </button>
              {error && <span className="small" style={{ color: '#c0392b' }}>{error}</span>}
              {hint && <span className="muted">{hint}</span>}
            </div>
          </form>
        </div>
      </section>

      <section className="card">
        <div className="card-title"><span>地圖</span><small>顯示您的路線</small></div>
        <div ref={mapEl} style={{ height: '30vh', width: '100%', borderRadius: 12 }} />
      </section>
    </div>
  )
}
