import React, { useEffect, useMemo, useRef, useState } from 'react'
import { getRouteProcess } from '../services/api';
import { getScheduleRoute } from '../services/api';

import debounce from 'lodash.debounce'

export default function RouteDetail({ route, onClose, highlightStop }) {
  const [selectedDir, setSelectedDir] = useState('去程')
  const [stops, setStops] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [viewMode, setViewMode] = useState('list')
  const isStatic = route.source === 'static'
  const isSingleDirection = route.direction && route.direction.includes('單向')
  const [initialLoading, setInitialLoading] = useState(true)
  const [tick, setTick] = useState(0)
  const [loadingCars, setLoadingCars] = useState(false)
  const [cars, setCars] = useState([])

  // Reloading
  useEffect(() => {
    const id = setInterval(() => setTick((t) => (t + 1) % 1_000_000), 15000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    let cancelled = false
    if (!route?.id) return

    async function load() {
      try {
        setLoading(true)
        setError(null)

        const byDir = await getRouteProcess(route.id)   // 🔥 只吃快取 API
        if (cancelled) return

        const dirKey = selectedDir
        const rawStops = byDir[dirKey] || []
        const allStatus = byDir.All_Status || []

        // 設定該路線該方向的車輛（只有 on_duty 才畫）
        // 🚍 直接從 Schedule_Route 取最新車輛位置
        const carsRaw = await getScheduleRoute();

        const carForThisRoute = carsRaw.filter(
          c => Number(c.routeId) === Number(route.id) &&
              c.direction === selectedDir
        );

        setCars(
          carForThisRoute.map(c => ({
            X: c.lng,
            Y: c.lat,
            direction: c.direction,
            route: c.routeId
          }))
        );


        const mapped = rawStops.map((row, idx) => ({
          // 順序：如果後端未給 stop_order，就用 index
          order: Number(row.stop_order ?? idx + 1),
          stop_order: Number(row.stop_order ?? idx + 1),
          name: row.stopName || row.stop_name,
          stopName: row.stopName || row.stop_name,
          latitude: Number(row.latitude),
          longitude: Number(row.longitude),
          carStatus: row.carStatus || row['車子所在位置'] || '',
          nextStop: row.nextStop || row['Next_Stop'] || '',
        }))

        setStops(mapped)
      } catch (err) {
        if (!cancelled) {
          console.warn('載入路線站點失敗:', err)
          setError('無法載入路線站點資料')
          setStops([])
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
          setInitialLoading(false)   // ⭐⭐ 加這行（非常重要）
        }
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [route, selectedDir])


  const list = useMemo(() => {
    if (!isStatic) return []
    return stations
      .filter((s) => {
        const nameMatch = (s['路徑名稱'] || '') === route.name
        const dirMatch = route.direction ? (s['路程'] || '') === route.direction : true
        return nameMatch && dirMatch
      })
      .sort((a, b) => {
        const na = Number(a['站次'] || 0)
        const nb = Number(b['站次'] || 0)
        return na - nb
      })
  }, [route, isStatic])

  // 站點資訊
  const displayStops = useMemo(() => {
    return (stops || []).map((s, idx) => ({
      ...s,
      order: s.order ?? s.stop_order ?? idx + 1,
      name: s.name || s.stopName || `第${idx + 1}站`,
      carStatus: s.carStatus || '',
    }))
  }, [stops])

  // 站點資訊
  const staticStopsForMap = useMemo(() => {
    if (!isStatic) return []
    return list.map((s, idx) => ({
      stop_name: s['站點'] || s['位置'] || `第${idx + 1}站`,
      stop_order: Number(s['站次'] ?? idx + 1) || idx + 1,
      latitude: Number(s['去程緯度'] ?? s['緯度'] ?? s['lat'] ?? s['Lat'] ?? 0),
      longitude: Number(s['去程經度'] ?? s['經度'] ?? s['lng'] ?? s['Lon'] ?? 0),
      etaFromStart: Number(s['首站到此站時間'] ?? idx * 3) || idx * 3,
    }))
      .filter((x) => Number.isFinite(x.latitude) && Number.isFinite(x.longitude))
      .sort((a, b) => (a.stop_order ?? 0) - (b.stop_order ?? 0))
  }, [isStatic, list])

  // 站點資訊
  if (initialLoading) {
    return (
      <div className="route-detail-overlay" role="dialog" aria-modal="true">
        <div className="route-detail-panel" style={{ display:'flex', alignItems:'center', justifyContent:'center', height:'60vh' }}>
          <div className="spinner" />
          <div className="muted small" style={{ marginTop:8 }}>載入中…</div>
        </div>
      </div>
    )
  }
  return (
    <div className="route-detail-overlay" role="dialog" aria-modal="true">
      <div className="route-detail-panel">

        <div
          className="route-detail-header"
          style={{
            textAlign: "center",
            paddingTop: 10,
            paddingBottom: 6,
          }}
        >
          {/* 標題 */}
          <div
            style={{
              fontSize: "30px",
              fontWeight: "900",
              color: "#111",
              marginBottom: 8,
            }}
          >
            {route.name}
          </div>

          {/* 三顆按鈕 */}
          <div
            style={{
              display: "flex",
              justifyContent: "center",
              gap: "12px",
            }}
          >
            {/* 去程 / 回程切換 */}
            {!isSingleDirection && (
              <button
                className="btn"
                onClick={() => {
                  if (!isSingleDirection) {
                    setSelectedDir(selectedDir === "去程" ? "回程" : "去程")
                  }
                }}
                disabled={isSingleDirection}
                style={{
                  backgroundColor: selectedDir === "去程" ? "#2563eb" : "#6b7280",
                  color: "#fff",
                  padding: "6px 16px",
                  borderRadius: 8,
                  fontSize: "15px",
                  fontWeight: 600,
                }}
              >
                {selectedDir}
              </button>
            )}

            {/* 地圖 / 時刻表切換 */}
            <button
              className="btn"
              onClick={() => setViewMode(viewMode === "list" ? "map" : "list")}
              style={{
                backgroundColor: viewMode === "list" ? "#007bff" : "#6366f1",
                color: "#fff",
                padding: "6px 16px",
                borderRadius: 8,
                fontSize: "15px",
                fontWeight: 600,
              }}
            >
              {viewMode === "list" ? "地圖" : "時刻表"}
            </button>

            {/* 關閉 */}
            <button
              className="btn"
              onClick={onClose}
              style={{
                backgroundColor: "#f97316",
                color: "#fff",
                padding: "6px 16px",
                borderRadius: 8,
                fontSize: "15px",
                fontWeight: 600,
              }}
            >
              關閉
            </button>
          </div>
        </div>

        {!isStatic ? (
          <>
            {viewMode === 'map' ? (
              <RouteMap stops={stops} cars={cars} route={route} direction={selectedDir} />
            ) : (
              <div className="stops-list">
                {loading && <div className="muted">載入中…</div>}
                {error && <div className="muted" style={{ color: '#c25' }}>{error}</div>}
                {loading && (
                  <div className="spinner-container">
                    <div className="spinner" />
                    <span className="muted small">載入車輛位置中…</span>
                  </div>
                )}

                {displayStops.map((s, idx) => {
                const isHighlight =
                  highlightStop !== null &&
                  highlightStop !== undefined &&
                  (s.order === highlightStop ||
                  s.stop_order === highlightStop ||
                  Number(s['站次']) === highlightStop)

                  return (
                    <div
                      key={idx}
                      className="stop-item"
                      style={isHighlight ? { border: '2px solid red', borderRadius: '8px' } : {}}
                    >
                      <div className="stop-left">
                        <div className="stop-name">{s.name}</div>
                      </div>
                      <div className="stop-right">
                          {(() => {
                            const txt = s.carStatus || ''
                            let bg = '#eaf2ff'
                            let color = '#1d4ed8'
                            let label = txt

                            if (txt === '當班') {
                              bg = '#e7f7ec'
                              color = '#16794c'
                              label = '到站中'
                            } else if (txt.includes('即將')) {
                              bg = '#fff2e5'
                              color = '#a24a00'
                              label = '即將進站'
                            } else if (/^\d+分/.test(txt)) {
                              bg = '#eaf2ff'
                              color = '#1d4ed8'
                              label = `約${txt}`
                            } else if (txt.includes('未發') || txt.includes('末班')) {
                              bg = '#fde8e8'
                              color = '#b91c1c'
                            }

                            return (
                              <span
                                className="muted small"
                                style={{
                                  padding: '2px 8px',
                                  borderRadius: 12,
                                  background: bg,
                                  color: color,
                                  whiteSpace: 'nowrap'
                                }}
                              >
                                {label}
                              </span>
                            )
                          })()}
                      </div>
                    </div>
                  )
                })}
                {!loading && displayStops.length === 0 && !error && (
                  <div className="muted">此方向目前無站點資料</div>
                )}
              </div>
            )}
          </>
        ) : (
          viewMode === 'map' ? (
            <RouteMap stops={staticStopsForMap} cars={cars} route={route} direction={selectedDir} />
          ) : (
            <div className="stops-list">
              {displayStops.map((s, idx) => (
                <div key={idx} className="stop-item">
                  <div className="stop-left">
                    <div className="stop-name">{s.name}</div>
                  </div>
                  <div className="stop-right">
                    <span
                      className="muted small"
                      style={{
                        padding: '2px 8px',
                        borderRadius: 12,
                        background:
                          s.status.tone === 'green'
                            ? '#e7f7ec'
                            : s.status.tone === 'orange'
                            ? '#fff2e5'
                            : s.status.tone === 'blue'
                            ? '#eaf2ff'
                            : '#f2f3f5',
                        color:
                          s.status.tone === 'green'
                            ? '#16794c'
                            : s.status.tone === 'orange'
                            ? '#a24a00'
                            : s.status.tone === 'blue'
                            ? '#1d4ed8'
                            : '#6b7280',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {s.status.label}
                    </span>
                  </div>
                </div>
              ))}
              {displayStops.length === 0 && <div className="muted">找不到此路線的站點資料</div>}
            </div>
          )
        )}
      </div>
    </div>
  )
}

// 地圖資訊
function useLeaflet() {
  const [ready, setReady] = useState(false)
  useEffect(() => {
    let cancelled = false
    if (window.L) { setReady(true); return }
    import('leaflet').then((mod) => {
      const L = mod.default ?? mod
      if (!cancelled) {
        window.L = L
        setReady(true)
      }
    })
    return () => { cancelled = true }
  }, [])
  return ready
}

// A. 完整的導航路徑點清單：定義為【去程】的精確順序 (花蓮轉運站 -> 門諾醫院)
const FULL_ROUTE_WAYPOINTS_BUS_5_GO = [
  // [緯度, 經度]
  [23.992880, 121.603436],  // 站牌 1: 花蓮轉運站 (去程起點)
  [23.994154, 121.604035],
  [23.994436, 121.603569],
  [24.001673, 121.607527],  // 十六股大道
  [24.001283, 121.613227],
  [23.993134, 121.616978],
  [23.992948, 121.618059],  // 站牌 2
  [23.992633, 121.618969],  // 站牌 3
  [23.991393, 121.618781],  // 站牌 4
  [23.990350, 121.618761],  // 左轉 (中繼點)
  [23.989914, 121.621415],
  [23.989492, 121.619704],  // 站牌 5
  [23.989163, 121.621378],  // 站牌 5 out
  [23.988637, 121.621244],
  [23.988996, 121.618588],
  // [23.988005, 121.618245],  // 站牌 6
  // [23.987822, 121.618336],  // back (迴轉點)
  [23.990096, 121.618681],  // 花蓮縣政府調度室
  [23.990634, 121.616636],
  [23.991914, 121.616793],  // 站牌 7
  [23.992905, 121.618345],
  [23.991352, 121.620766],
  [23.991483, 121.620159]   // 站牌 8
];
const FULL_ROUTE_WAYPOINTS_BUS_5_RE = [
  // [緯度, 經度]
  [23.991320, 121.619951],  // 站牌 1: 花蓮縣政府
  [23.991414, 121.620812],  // 縣政府出左轉 (中繼點)
  [23.992667, 121.620798],  // 瑞美路
  [23.992748, 121.618984],  // 左轉府後路
  [23.988977, 121.618753],  // 十字路口左轉介壽四街
  [23.989138, 121.621368],  // 左轉蘇花公路
  [23.989493, 121.619711],  // 法院
  [23.989547, 121.621434],  // 法院出來左轉
  [23.990257, 121.619469],  // 左轉介壽五街
  [23.990813, 121.616600],  // 右轉新興路
  [23.995210, 121.616732],
  [24.001582, 121.606885],
  [23.997408, 121.604855],  // 國興一街
  [23.993504, 121.603200],  // 左轉國民八街
  [23.992623, 121.603013]
];
const FULL_ROUTE_WAYPOINTS_BUS_6_GO = [
  // [緯度, 經度]
  [23.993020, 121.603219],   // 站牌 1: 花蓮轉運站 (去程起點)
  [23.983500, 121.607429],   // 站牌 2
  [23.980242, 121.610008],   // 站牌 3
  [23.978331, 121.611559],   // 站牌 4: 花蓮醫院慈愛大樓 (修正點路線用)
  [23.977804, 121.612066],   // 明禮x公園
  [23.982743, 121.621506],   // 站牌 5: 璽濱行旅 (舊座標)
  [23.984846, 121.621697],
  [23.987023, 121.622277],   // 站牌 6: 煙波飯店
  [23.988663, 121.623682],   // 站牌 7
  [23.988535, 121.626440]    // 站牌 8: 門諾醫院 (修正後的路線終點座標)
];
const FULL_ROUTE_WAYPOINTS_BUS_6_RE = [
  // [緯度, 經度]
  [23.988574, 121.626244],  // 門諾醫院 (回程起點)
  [23.988485, 121.624943],  // 民權八街
  [23.988851, 121.623602],  // 左轉中美路
  [23.985341, 121.620978],  // 左轉民權五街
  [23.981949, 121.620637],  // 民權路
  [23.980376, 121.615715],  // 菁華街
  [23.978328, 121.612864],  // 圓弧
  [23.978187, 121.611727],  // 右轉明禮路
  [23.984106, 121.607085],  // 叉路
  [23.992051, 121.605087],  // 左轉國聯四路
  [23.992658, 121.602928]   // 花蓮轉運站 (回程終點)
];
const FULL_ROUTE_WAYPOINTS_BUS_7 = [
  // [緯度, 經度]
  [23.993477, 121.603394],  // 轉運站
  [23.994173, 121.604330],  // 國聯一路
  [23.993036, 121.604443],  // 國民八街
  [23.991313, 121.603270],  // 國聯三路
  [23.988999, 121.600384],  // 國聯一路
  [23.988541, 121.600409],  // 中山路
  [23.984746, 121.603367],  // 自由廣場
  [23.982258, 121.605351],
  [23.978442, 121.602068],  // 仁愛
  [23.975257, 121.606532],
  [23.972469, 121.608785],  // 自由街底
  [23.973208, 121.610151],  // 東大門夜市
  [23.975851, 121.608322],  // 光復街尾
  [23.977512, 121.611650],  // 花崗國民中學
  [23.979378, 121.610766],  // 明禮路
  [23.980547, 121.612377],  // 將軍府
  [23.979658, 121.610559],  // 折返點
  [23.982020, 121.608574],  // 明禮路x大同街
  [23.984837, 121.606906],
  [23.993727, 121.604863],  // 國聯五路
  [23.993832, 121.603979],  // 國聯一路
  [23.992613, 121.603035]
];

function RouteMap({ stops, cars, route, direction }) {
  const ready = useLeaflet()
  const elRef = useRef(null)
  const mapRef = useRef(null)
  const layerRouteRef = useRef(null)
  const layerStopsRef = useRef(null)
  const layerBusRef = useRef(null)

  useEffect(() => {
    if (!ready || !elRef.current || mapRef.current) return
    const L = window.L
    const map = L.map(elRef.current, { center:[23.99302,121.603219], zoom:14 })
    L.tileLayer('https://wmts.nlsc.gov.tw/wmts/EMAP/default/GoogleMapsCompatible/{z}/{y}/{x}', { tileSize:256 }).addTo(map)
    L.tileLayer('https://wmts.nlsc.gov.tw/wmts/EMAP2/default/GoogleMapsCompatible/{z}/{y}/{x}', { tileSize:256, opacity:.9 }).addTo(map)
    mapRef.current = map
    layerRouteRef.current = L.layerGroup().addTo(map)
    layerStopsRef.current = L.layerGroup().addTo(map)
    layerBusRef.current = L.layerGroup().addTo(map)
  }, [ready])

  useEffect(() => {
    if (!ready || !mapRef.current) return
    const L = window.L
    const routeLayer = layerRouteRef.current
    const stopLayer = layerStopsRef.current
    routeLayer.clearLayers(); stopLayer.clearLayers()

    const ordered = (stops || []).slice().sort((a,b) => (a.order ?? a.stop_order ?? 0) - (b.order ?? b.stop_order ?? 0))
    const llOriginal = ordered.map(s => {
      const lat = Number(s.latitude ?? s.lat)
      const lng = Number(s.longitude ?? s.lng)
      return Number.isFinite(lat) && Number.isFinite(lng) ? [lat, lng] : null
    }).filter(Boolean)

    async function drawFullRoute() {
      if (llOriginal.length < 2) return
      let shapeCoords = route.shape

      let pointsForRouting;

      console.log(direction);
      const IS_RETURN_DIRECTION = direction === '回程'; // 使用傳入的方向判斷
      const IS_ROUTE_5 = Number(route.id) === 1; // 市民小巴5 的 ID=1
      const IS_ROUTE_6 = Number(route.id) === 2; // 市民小巴6 的 ID=2
      const IS_ROUTE_7 = Number(route.id) === 3; // 市民小巴7 的 ID=3

      if (IS_ROUTE_5) {
        if (!IS_RETURN_DIRECTION) {
          // 情況 1: 路線 5 且是【去程】
          pointsForRouting = FULL_ROUTE_WAYPOINTS_BUS_5_GO;
          console.log(`啟用小巴5去程精確導航 (靜態清單)，總計 ${pointsForRouting.length} 個點。`);
        } else {
          // 情況 2: 路線 5 且是【回程】
          pointsForRouting = FULL_ROUTE_WAYPOINTS_BUS_5_RE;
          console.log(`啟用小巴5回程精確導航 (靜態清單)，總計 ${pointsForRouting.length} 個點。`);
        }
      } else if (IS_ROUTE_6) {
        if (!IS_RETURN_DIRECTION) {
          // 情況 1: 路線 6 且是【去程】 (靜態清單就是去程順序)
          pointsForRouting = FULL_ROUTE_WAYPOINTS_BUS_6_GO;
          console.log(`啟用小巴6去程精確導航 (靜態清單)，總計 ${pointsForRouting.length} 個點。`);
        } else {
          // 情況 2: 路線 6 且是【回程】
          pointsForRouting = FULL_ROUTE_WAYPOINTS_BUS_6_RE;
          console.log(`啟用小巴6回程精確導航 (靜態清單)，總計 ${pointsForRouting.length} 個點。`);
        }
      } else if (IS_ROUTE_7) {
        // 循環線 共用
        pointsForRouting = FULL_ROUTE_WAYPOINTS_BUS_7;
        console.log(`啟用小巴6去程精確導航 (靜態清單)，總計 ${pointsForRouting.length} 個點。`);
      } else {
        // 其他路線，退回使用原始的 llOriginal 清單
        pointsForRouting = llOriginal; 
      }

      if (!shapeCoords || shapeCoords.length === 0) {
        // fallback：用 OSRM 計算整條路線
        
        // 將完整的路徑點列表轉換成 OSRM 格式
        const coords = pointsForRouting.map(p => `${p[1]},${p[0]}`).join(";") // 格式：經度,緯度;經度,緯度
        const url = `https://router.project-osrm.org/route/v1/driving/${coords}?overview=full&geometries=geojson`

        try {
          const res = await fetch(url)
          const data = await res.json()
          if (data.routes && data.routes[0]?.geometry) {
            // OSRM 回傳的 shapeCoords 是 [lng, lat] 格式，需轉為 Leaflet 的 [lat, lng]
            shapeCoords = data.routes[0].geometry.coordinates.map(([lng, lat]) => [lat, lng])
          }
        } catch (err) {
          console.warn("OSRM 失敗，退回直線", err)
          shapeCoords = llOriginal 
        }
      }

      if (shapeCoords && shapeCoords.length > 0) {
        const stroke = L.polyline(shapeCoords, {
          color: '#2563eb',
          weight: 7,
          opacity: 0.98
        }).addTo(layerRouteRef.current)

        mapRef.current.fitBounds(stroke.getBounds(), { padding: [30, 30] })
      }
    }
    drawFullRoute()

    const icon = (label, cls = '') => L.divIcon({
      className: '',
      html: `
        <div class="stop-badge ${cls}" style="
          display: flex;
          align-items: center;
          justify-content: center;
          width: auto;
          min-width: 28px;
          height: 28px;
          padding: 0 6px;
          border-radius: 50%;
          background: #2563eb;
          border: 2px solid #ffffff;
          color: #ffffff;
          font-weight: 700;
          font-size: 13px;
          font-family: Arial, Helvetica, sans-serif;
          text-align: center;
          white-space: nowrap;
          line-height: 0;           /* 防止上下分行 */
          transform: translateY(0); /* 避免被 Leaflet 壓偏 */
          box-shadow: 0 0 4px rgba(0,0,0,0.4);
        ">
          <span style="display:inline-block; line-height:1;">${label}</span>
        </div>
      `,
      iconSize: null,
      iconAnchor: [14, 14],
    })

    ordered.forEach((s, idx) => {
      const p = llOriginal[idx]; if (!p) return
      const isFirst = idx===0, isLast = idx===ordered.length-1
      const label = isFirst ? '1' : (s.order ?? s.stop_order ?? idx+1)
      const cls = isFirst ? 'stop-start' : (isLast ? 'stop-end' : '')
      L.marker(p, { icon: icon(label, cls) }).addTo(stopLayer).bindTooltip(`${s.stopName || s.stop_name || '站點'}`, { direction:'top' })
    })
  }, [ready, stops])
    
  useEffect(() => {
    if (!ready || !mapRef.current) return
    const L = window.L
    const busLayer = layerBusRef.current
    busLayer.clearLayers()

    const iconSize = 50
    const iconFontSize = 54

    // cars = [{X, Y, direction, route}]
    cars.forEach(car => {
      if (!car.X || !car.Y) return

      const busPt = [car.Y, car.X]

      const iconHtml = `
        <div style="
          display:flex;
          align-items:center;
          justify-content:center;
          width:${iconSize}px;
          height:${iconSize}px;
          border-radius:50%;
          background:#ffffff; /* 底色設定為白色 */
          border:none; /* 直接去除外框 */
          color:#2563eb; /* 公車圖案顏色設為藍色 */
          font-size:${iconFontSize}px;
          font-weight:900;
          box-shadow:0 0 12px rgba(0,0,0,0.4); /* 增加陰影讓它看起來更立體 */
        ">
          🚌
        </div>
      `

      const icon = L.divIcon({
        className: '',
        html: iconHtml,
        iconSize: [iconSize, iconSize],
        iconAnchor: [iconSize / 2, iconSize / 2], // 確保錨點在中心
      })

      L.marker(busPt, { 
        icon,
        zIndexOffset: 1000 // // 最上層顯示 (Z-index)
      }).addTo(busLayer)

      // const iconHtml = `
      //   <div style="
      //     display:flex;
      //     align-items:center;
      //     justify-content:center;
      //     width:32px;
      //     height:32px;
      //     border-radius:50%;
      //     background:#2563eb;
      //     border:2px solid #fff;
      //     color:#fff;
      //     font-size:18px;
      //     font-weight:900;
      //     box-shadow:0 0 6px rgba(0,0,0,0.3);
      //   ">
      //     🚌
      //   </div>
      // `

      // const icon = L.divIcon({
      //   className: '',
      //   html: iconHtml,
      //   iconSize: [32, 32],
      //   iconAnchor: [16, 16],
      // })

      // L.marker(busPt, { icon }).addTo(busLayer)
    })
  }, [ready, cars])


  return <div style={{ height:'60vh', borderRadius:12, overflow:'hidden' }} ref={elRef} />
}
