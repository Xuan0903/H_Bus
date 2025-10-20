import React from 'react'

export default function RecentTrips({ trips = [], showMore, onToggle, statusText }) {
  const fmt = (s) => {
    try {
      if (!s) return '-'
      const d = new Date(s)
      if (isNaN(d)) return String(s)
      const y = d.getFullYear()
      const M = String(d.getMonth() + 1).padStart(2, '0')
      const D = String(d.getDate()).padStart(2, '0')
      const h = String(d.getHours()).padStart(2, '0')
      const m = String(d.getMinutes()).padStart(2, '0')
      return `${y}-${M}-${D} ${h}:${m}`
    } catch {
      return String(s)
    }
  }

  if (!trips || trips.length === 0) {
    return (
      <section className="card">
        <div className="card-title"><span>最近行程</span></div>
        <div className="muted small">最近沒有行程</div>
      </section>
    )
  }

  // 僅顯示過去兩週內的紀錄（含今天）
  const now = new Date()
  const twoWeeksAgo = new Date(now.getTime() - 14 * 24 * 60 * 60 * 1000)
  const visibleTrips = (trips || []).filter((row) => {
    try {
      const t = new Date(row.booking_time)
      if (isNaN(t)) return false
      return t >= twoWeeksAgo && t <= now
    } catch {
      return false
    }
  })

  return (
    <section className="card">
      <div className="card-title">
        <span>最近行程</span>
      </div>
      <div className="list">
        {(showMore ? visibleTrips : visibleTrips.slice(0, 3))
          .filter(r => !String(r.review_status || '').toLowerCase().includes('canceled'))
          .map((r, idx) => (
            <div
              key={idx}
              className="trip-card"
              style={{
                background: '#fff',
                borderRadius: 10,
                padding: '12px 14px',
                marginBottom: 10,
                boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
              }}
            >
              <div style={{ fontWeight: 600, marginBottom: 4 }}>
                {r.booking_start_station_name} → {r.booking_end_station_name}
              </div>
              <div style={{ fontSize: 14, color: '#374151' }}>
                {fmt(r.booking_time)} ・ {r.booking_number} 人
              </div>
              <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>
                狀態：審核 {statusText(r.review_status)} ・ 支付 {statusText(r.payment_status)} ・ 編號：{r.booking_code || r.reservation_id}
              </div>
            </div>
          ))}
      </div>

      {trips.length > 3 && (
        <div className="mt-12" style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button className="btn btn-primary" onClick={onToggle}>
            {showMore ? '收起' : '查看更多'}
          </button>
        </div>
      )}
    </section>
  )
}
