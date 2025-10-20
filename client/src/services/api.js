const envBase = (import.meta.env && import.meta.env.VITE_API_BASE_URL) || ''
const BASE = (envBase?.trim?.() || (import.meta.env?.DEV ? '/api' : ''))

export async function getRoutes() {
  const res = await fetch(`${BASE}/All_Route`, {
    headers: { accept: 'application/json' },
  })
  if (!res.ok) {
    throw new Error(`Failed to load routes: ${res.status}`)
  }

  const data = await res.json()

  return data
    .filter((r) => r.status !== 0)
    .map((r) => ({
      id: r.route_id,
      name: r.route_name,
      direction: r.direction || '',
      stopCount: r.stop_count ?? null,
      startStop: r.start_stop ?? '',
      endStop: r.end_stop ?? '',
      status: r.status,
      createdAt: r.created_at,
      source: 'api',
      key: `${r.route_name} ${r.direction || ''}`.trim(),
      _raw: r,
    }))
}

// 改改A
export async function getRouteStops(routeId, direction) {
  const res = await fetch(`${BASE}/Route_Stations`, {
    method: 'POST',
    headers: {
      accept: 'application/json',
      'content-type': 'application/json',
    },
    body: JSON.stringify({ route_id: routeId, direction }),
  })
  if (!res.ok) {
    throw new Error(`Failed to load stops: ${res.status}`)
  }
  /** @type {Array} */
  const data = await res.json()
  const sorted = data
    .map((s) => ({
      routeId: s.route_id,
      routeName: s.route_name,
      direction: s.direction,
      stopName: s.stop_name,
      latitude: s.latitude,
      longitude: s.longitude,
      etaFromStart: Number(s.eta_from_start) || 0,
      order: s.stop_order,
      createdAt: s.created_at,
    }))
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))

  // 加上 etaToHere
  for (let i = 0; i < sorted.length; i++) {
    if (i === 0) {
      sorted[i].etaToHere = 0   // 首站沒有上一站
    } else {
      sorted[i].etaToHere = sorted[i].etaFromStart - sorted[i - 1].etaFromStart
    }
  }
  return sorted
}

export async function getRouteScheduleTime(routeId, direction) {
  const res = await fetch(`${BASE}/Route_ScheduleTime?route_id=${routeId}&direction=${encodeURIComponent(direction || '')}`, {
    headers: { accept: 'application/json' },
  })
  if (!res.ok) {
    throw new Error(`Failed to load schedule time: ${res.status}`)
  }

  const data = await res.json()
  // 後端格式是 { status, route_id, direction, data: [...] }
  return Array.isArray(data.data) ? data.data : []
}


// Bulk: fetch all stops (both directions) for a route in one request
export async function getRouteStopsBulk(routeId) {
  const __mapDir = (v) => {
    const t = String(v || '').trim()
    if (/返|回|1/.test(t)) return '返程'
    if (/去|往|0/.test(t)) return '去程'
    return t
  }
  const res = await fetch(`${BASE}/Route_Stations`, {
    method: 'POST',
    headers: {
      accept: 'application/json',
      'content-type': 'application/json',
    },
    body: JSON.stringify({ route_id: Number(routeId) }), // no direction -> all
  })
  if (!res.ok) {
    throw new Error(`Failed to load stops (bulk): ${res.status}`)
  }
  const data = await res.json()
  const rows = Array.isArray(data) ? data : []
  const mapped = rows.map((s) => ({
    routeId: s.route_id,
    routeName: s.route_name,
    direction: __mapDir(s.direction),
    stopName: s.stop_name,
    latitude: s.latitude,
    longitude: s.longitude,
    etaFromStart: Number(s.eta_from_start) || 0,
    order: s.stop_order,
    createdAt: s.created_at,
  }))
  const byDir = {
    去程: [],
    返程: [],
  }
  for (const r of mapped) {
    const d = __mapDir(r.direction)
    if (d === '返程') byDir.返程.push(r)
    else if (d === '去程') byDir.去程.push(r)
  }
  byDir.去程.sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
  byDir.返程.sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
  // add etaToHere
  const addEtaToHere = (arr) => {
    for (let i = 0; i < arr.length; i++) {
      arr[i].etaToHere = i === 0 ? 0 : (arr[i].etaFromStart - arr[i-1].etaFromStart)
    }
  }
  addEtaToHere(byDir.去程)
  addEtaToHere(byDir.返程)
  return byDir
}

export async function getStations() {
  const res = await fetch(`${BASE}/yo_hualien`, {
    headers: { accept: 'application/json' },
  })
  if (!res.ok) {
    throw new Error(`Failed to load stations: ${res.status}`)
  }
  const data = await res.json()
  return data
    .filter((s) => Number.isFinite(Number(s.latitude)) && Number.isFinite(Number(s.longitude)))
    .map((s, i) => ({
      id: i + 1,
      name: s.station_name,
      address: s.address,
      lat: Number(s.latitude),
      lng: Number(s.longitude),
      _raw: s,
    }))
}

// --- Reservations ---
export async function getMyReservations(userId) {
  const res = await fetch(`${BASE}/reservations/my?user_id=${encodeURIComponent(userId)}`, {
    headers: { accept: 'application/json' },
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(`Failed to load reservations: ${res.status}`)
  let rows = []
  if (Array.isArray(data?.reservations)) rows = data.reservations
  else if (Array.isArray(data?.sql)) rows = data.sql
  else if (Array.isArray(data?.data)) rows = data.data
  else if (Array.isArray(data)) rows = data
  return rows
}

export async function cancelReservation(reservationId, cancelReason) {
  const res = await fetch(`${BASE}/reservations/Canceled`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', accept: 'application/json' },
    body: JSON.stringify({
      reservation_id: reservationId,
      cancel_reason: cancelReason,
    }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail || `Cancel failed: ${res.status}`);
  return data;
}

export async function getTomorrowReservations(userId) {
  console.log("[API] getTomorrowReservations called with", userId)
  const res = await fetch(`${BASE}/reservations/tomorrow?user_id=${encodeURIComponent(userId)}`, {
    headers: { accept: 'application/json' },
  })
  console.log("[API] fetch done, status=", res.status)
  const data = await res.json().catch(() => ({}))
  console.log("[API] response json:", data)
  if (!res.ok) throw new Error(`Failed to load tomorrow reservations: ${res.status}`)

  if (Array.isArray(data?.sql)) return data.sql
  if (Array.isArray(data?.reservations)) return data.reservations
  return []
}

export async function getCarPositions() {
  const res = await fetch(`${BASE}/GIS_AllFast`)
  const data = await res.json()
  return Object.keys(data.route).map(i => ({
    route: data.route[i],
    X: parseFloat(data.X[i]),
    Y: parseFloat(data.Y[i]),
    direction: data.direction[i],
    currentLocation: data.Current_Location[i]
  }))
}