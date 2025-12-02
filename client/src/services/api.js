const envBase = (import.meta.env && import.meta.env.VITE_API_BASE_URL) || ''
const BASE = (envBase?.trim?.() || (import.meta.env?.DEV ? '/api' : ''))

export async function getRoutes() {
  const res = await fetch(`${BASE}/Cache/Total_Route`, {
    headers: { accept: 'application/json' },
  })
  if (!res.ok) {
    throw new Error(`Failed to load cached routes: ${res.status}`)
  }

  const data = await res.json()

  // 格式直接轉成 RoutesPage 需要的格式
  return data.map((r) => ({
    id: r.route_id,
    name: r.route_name,
    direction: r.direction || '',
    status: 1,  // 你快取目前沒 status，給 1 讓前端正常運作
    source: 'cache',
    key: `${r.route_name} ${r.direction || ''}`.trim(),
    _raw: r,
  }))
}

export async function getRouteProcess(routeId) {
  const res = await fetch(`${BASE}/Cache/Process_Route`, {
    headers: { accept: 'application/json' },
  })
  if (!res.ok) {
    throw new Error(`Failed to load process route: ${res.status}`)
  }

  /** @type {Record<string, Array<any>>} */
  const data = await res.json().catch(() => ({}))

  const routeIdStr = String(routeId)

  // 把所有 key ("1-GO", "1-BACK"...) 攤平後，先只抓這條路線的
  const allRows = Object.values(data)
    .flat()
    .filter((row) => String(row.route_id) === routeIdStr)

  const byDir = {
    去程: [],
    回程: [],
  }

  for (const row of allRows) {
    const rawDir = String(row.direction || '').trim()
    const isBack = /返|回/.test(rawDir)
    const dir = isBack ? '回程' : '去程'

    byDir[dir].push({
      // 保留原始資料給地圖用
      ...row,
      routeId: row.route_id,
      direction: dir,
      stopName: row.stop_name,
      carStatus: row['車子所在位置'], // 後端算好的顯示字串
      nextStop: row['Next_Stop'],
    })
  }

  return byDir
}

export async function getAllStatus() {
  const res = await fetch(`/api/Cache/Process_Route`, {
    headers: { accept: 'application/json' }
  });

  if (!res.ok) throw new Error('Failed to load Process_Route');

  const json = await res.json();
  return Array.isArray(json.All_Status) ? json.All_Status : [];
}

export async function getRouteCarStatus(routeId) {
  const res = await fetch(`${BASE}/Cache/Process_Route`, {
    headers: { accept: 'application/json' },
  });

  if (!res.ok) {
    throw new Error(`Failed to load Process_Route: ${res.status}`);
  }

  const json = await res.json().catch(() => ({}));

  const allStatus = Array.isArray(json.All_Status) ? json.All_Status : [];

  const routeIdNum = Number(routeId);

  // 只抓該路線的
  const rows = allStatus.filter((r) => Number(r.route_no) === routeIdNum);

  // 統一轉換格式
  return rows.map((r) => ({
    routeId: r.route_no,
    direction: /返|回/.test(r.direction) ? "回程" : "去程",
    licensePlate: r.license_plate,
    operationStatus: r.operation_status,
    vehicleStatus: r.vehicle_status,   // on_duty / rest
    lat: r.Y === "NONE" ? null : Number(r.Y),
    lng: r.X === "NONE" ? null : Number(r.X),
    locationName: r["當班位置"] || "NONE"
  }));
}


export async function getScheduleRoute() {
  const res = await fetch(`${BASE}/Cache/Schedule_Route`, {
    headers: { accept: "application/json" }
  });

  if (!res.ok) throw new Error("Failed to load Schedule_Route");

  const data = await res.json();

  return data
    .filter(r =>
      r.vehicle_status === "on_duty" &&
      r.X !== "NONE" &&
      r.Y !== "NONE"
    )
    .map(r => ({
      routeId: r.route_no,
      direction: /返|回/.test(r.direction) ? "回程" : "去程",
      licensePlate: r.license_plate,
      lat: Number(r.Y),
      lng: Number(r.X)
    }));
}



// Route_Stations
// export async function getRouteStops(routeId, direction) {
//   const res = await fetch(`${BASE}/Route_Stations`, {
//     method: 'POST',
//     headers: {
//       accept: 'application/json',
//       'content-type': 'application/json',
//     },
//     body: JSON.stringify({ route_id: routeId, direction }),
//   })
//   if (!res.ok) {
//     throw new Error(`Failed to load stops: ${res.status}`)
//   }
//   /** @type {Array} */
//   const data = await res.json()
//   const sorted = data
//     .map((s) => ({
//       routeId: s.route_id,
//       routeName: s.route_name,
//       direction: s.direction,
//       stopName: s.stop_name,
//       latitude: s.latitude,
//       longitude: s.longitude,
//       etaFromStart: Number(s.eta_from_start) || 0,
//       order: s.stop_order,
//       createdAt: s.created_at,
//     }))
//     .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))

//   // 加上 etaToHere
//   for (let i = 0; i < sorted.length; i++) {
//     if (i === 0) {
//       sorted[i].etaToHere = 0   // 首站沒有上一站
//     } else {
//       sorted[i].etaToHere = sorted[i].etaFromStart - sorted[i - 1].etaFromStart
//     }
//   }
//   return sorted
// }

// Route_ScheduleTime
// export async function getRouteScheduleTime(routeId, direction) {
//   const res = await fetch(`${BASE}/Route_ScheduleTime?route_id=${routeId}&direction=${encodeURIComponent(direction || '')}`, {
//     headers: { accept: 'application/json' },
//   })
//   if (!res.ok) {
//     throw new Error(`Failed to load schedule time: ${res.status}`)
//   }

//   const data = await res.json()
//   return Array.isArray(data.data) ? data.data : []
// }

// Route_Stations
// export async function getRouteStopsBulk(routeId) {
//   const __mapDir = (v) => {
//     const t = String(v || '').trim()
//     if (/返|回|1/.test(t)) return '返程'
//     if (/去|往|0/.test(t)) return '去程'
//     return t
//   }
//   const res = await fetch(`${BASE}/Route_Stations`, {
//     method: 'POST',
//     headers: {
//       accept: 'application/json',
//       'content-type': 'application/json',
//     },
//     body: JSON.stringify({ route_id: Number(routeId) }), // no direction -> all
//   })
//   if (!res.ok) {
//     throw new Error(`Failed to load stops (bulk): ${res.status}`)
//   }
//   const data = await res.json()
//   const rows = Array.isArray(data) ? data : []
//   const mapped = rows.map((s) => ({
//     routeId: s.route_id,
//     routeName: s.route_name,
//     direction: __mapDir(s.direction),
//     stopName: s.stop_name,
//     latitude: s.latitude,
//     longitude: s.longitude,
//     etaFromStart: Number(s.eta_from_start) || 0,
//     order: s.stop_order,
//     createdAt: s.created_at,
//   }))
//   const byDir = {
//     去程: [],
//     返程: [],
//   }
//   for (const r of mapped) {
//     const d = __mapDir(r.direction)
//     if (d === '返程') byDir.返程.push(r)
//     else if (d === '去程') byDir.去程.push(r)
//   }
//   byDir.去程.sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
//   byDir.返程.sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
//   // add etaToHere
//   const addEtaToHere = (arr) => {
//     for (let i = 0; i < arr.length; i++) {
//       arr[i].etaToHere = i === 0 ? 0 : (arr[i].etaFromStart - arr[i-1].etaFromStart)
//     }
//   }
//   addEtaToHere(byDir.去程)
//   addEtaToHere(byDir.返程)
//   return byDir
// }

// yo_hualien
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

// GIS_AllFast
// export async function getCarPositions() {
//   const res = await fetch(`${BASE}/GIS_AllFast`)
//   const data = await res.json()
//   return Object.keys(data.route).map(i => ({
//     route: data.route[i],
//     X: parseFloat(data.X[i]),
//     Y: parseFloat(data.Y[i]),
//     direction: data.direction[i],
//     currentLocation: data.Current_Location[i]
//   }))
// }

// route_schedule
// export async function getRouteSchedule(routeId) {
//   try {
//     const res = await fetch(`/api/route_schedule?route_id=${routeId}`);
//     if (!res.ok) throw new Error(`HTTP ${res.status}`);
//     const data = await res.json();
//     return data.data || [];
//   } catch (err) {
//     console.error("❌ getRouteSchedule error:", err);
//     return [];
//   }
// }