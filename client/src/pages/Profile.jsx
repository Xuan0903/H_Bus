import React, { useEffect, useState, useRef } from 'react'
import { getMyReservations } from '../services/api'
import MyReservations from '../components/MyReservations'
import RecentTrips from '../components/RecentTrips'
import { useNavigate, useLocation } from 'react-router-dom'

function ProfilePage({ user, onLogin, onLogout }) {
  const navigate = useNavigate()
  const location = useLocation()
  const [sessionUser, setSessionUser] = useState(null)
  const [sessionLoading, setSessionLoading] = useState(true)
  const [unauthorized, setUnauthorized] = useState(false)
  const [myResv, setMyResv] = useState([])
  const [toastMsg, setToastMsg] = useState('')
  const resvRef = useRef(null)
  const [contactField, setContactField] = useState(null)
  const [contactValue, setContactValue] = useState('')
  const [contactError, setContactError] = useState('')
  const [contactSaving, setContactSaving] = useState(false)
  const [showMoreTrips, setShowMoreTrips] = useState(false)
  const [privacyContent, setPrivacyContent] = useState('')
  const [showPrivacy, setShowPrivacy] = useState(false)
  const [reserveContent, setReserveContent] = useState('')
  const [showReserve, setShowReserve] = useState(false)
  const supportPhone = "0800-827656";
  const phoneDisplay = supportPhone.replace(/(\d{4})(\d{3})(\d{3})/,'$1 $2 $3');
  const supportEmail = "aspring51000@gmail.com";
  const emailLink = `mailto:${supportEmail}`;

  function copyToClipboard(text){
    if (!navigator?.clipboard) {
      // fallback
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy'); } catch(e){}
      document.body.removeChild(ta);
      setToastMsg('已複製');
      return;
    }
    navigator.clipboard.writeText(text)
      .then(() => setToastMsg('已複製'))
      .catch(() => setToastMsg('複製失敗'))

  }

  function viewPrivacy() {
    fetch('/api/privacy')
      .then(resp => resp.json())
      .then(data => {
        setPrivacyContent(data.content)
        setShowPrivacy(true)
      })
      .catch(err => console.error(err))
  }

  function viewReserve() {
    fetch('/api/reserve')
      .then(resp => resp.json())
      .then(data => {
        setReserveContent(data.content)
        setShowReserve(true)
      })
      .catch(err => console.error(err))
  }  

  // 加上時間判斷
  const now = new Date()

  // 已過期 or 狀態失敗 → 最近行程
  const recentTrips = myResv.filter(r => {
    const bookingTime = new Date(r.booking_time)
    const expired = !isNaN(bookingTime) && bookingTime < now
    const failed = (
      String(r.review_status||'').toLowerCase().includes('reject') ||
      String(r.review_status||'').toLowerCase().includes('canceled') ||
      String(r.payment_status||'').toLowerCase().includes('fail')
    )
    return expired || failed
  })

  useEffect(() => {
  if (!toastMsg) return;
  const timer = setTimeout(() => setToastMsg(''), 2000); // 2 秒後清空
  return () => clearTimeout(timer);
}, [toastMsg]);

  useEffect(() => {
    if (import.meta.env.MODE === 'production') return
    const helper = async (passcode, overrides = {}) => {
      if (passcode !== 'Lab@109**') {
        console.warn('[H_Bus] 測試密碼錯誤')
        return false
      }
      const nowIso = new Date().toISOString()
      const fakeUser = {
        user_id: overrides.user_id ?? -999,
        line_id: overrides.line_id ?? 'lab-tester',
        username: overrides.username ?? 'Lab 測試人員',
        email: overrides.email ?? 'lab@example.com',
        phone: overrides.phone ?? null,
        last_login: overrides.last_login ?? nowIso,
        testing: true,
        source: 'local-dev',
        ...overrides,
      }
      setSessionUser(fakeUser)
      setUnauthorized(false)
      setSessionLoading(false)
      if (onLogin) {
        try { onLogin(fakeUser) } catch (err) { console.warn(err) }
      }
      setToastMsg('已以測試帳號登入 (僅本地用途)')
      console.info('[H_Bus] 已載入測試帳號，重新整理即可恢復。')
      return true
    }
    Object.defineProperty(window, 'hbusTestLogin', { value: helper, configurable: true })
    console.info('[H_Bus] 測試模式：在 console 呼叫 hbusTestLogin(\'Lab@109**\') 可載入測試帳號。')
    return () => {
      if (window.hbusTestLogin === helper) {
        delete window.hbusTestLogin
      }
    }
  }, [onLogin])

  // 檢查 session 狀態，決定是否顯示登入介面
  useEffect(() => {
    async function checkSession() {
      setSessionLoading(true)
      try {
        const resp = await fetch(`/me`, { credentials: 'include' });
        if (!resp.ok) throw new Error('未登入')
        const data = await resp.json()
        if (data && data.user_id) {
          setSessionUser(data)
          if (onLogin) onLogin(data)
        } else {
          setSessionUser(null)
        }
      } catch {
        setSessionUser(null)
        setUnauthorized(true)
      } finally {
        setSessionLoading(false)
      }
    }
    checkSession()
  }, [])

  // 當確認為未登入（/me 回 401 或錯誤）時，通知父層清空使用者狀態
  useEffect(() => {
    if (unauthorized) {
      try { if (onLogout) onLogout() } catch {}
    }
  }, [unauthorized])

  // 導覽狀態處理（預約完成提示、滾動）
  useEffect(() => {
    if (!location) return
    const params = new URLSearchParams(location.search || '')
    const tab = params.get('tab')
    const toast = location.state && location.state.toast
    if (toast) {
      setToastMsg(String(toast))
      try { navigate(location.pathname + location.search, { replace: true, state: {} }) } catch {}
    }
    if (tab === 'reservations' && resvRef.current) {
      setTimeout(() => { resvRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }, 100)
    }
  }, [location])

useEffect(() => {
  const currentUser = getEffectiveUser()
  const uid = currentUser?.user_id ?? currentUser?.id
  if (!uid) return

  let cancelled = false
  const load = async () => {
    try {
      const list = await getMyReservations(uid)
      if (!cancelled) setMyResv(list ?? [])
    } catch (err) {
      console.warn('recent trips fetch failed', err)
    }
  }

  load()
  return () => { cancelled = true }
}, [sessionUser, user])

  // 登出功能
  const handleLogout = () => {
    window.location.href = `/logout`;
  };

  const getEffectiveUser = () => (sessionUser && sessionUser.user_id) ? sessionUser : user
  
  const statusText = (s) => {
    const str = String(s || '').toLowerCase()
    if (str.includes('approved') || str.includes('paid') || str.includes('assigned') || str.includes('complete')) {
      return '通過'
    }
    if (str.includes('pending') || str.includes('not_assigned')) {
      return '待辦'
    }
    if (str.includes('reject') || str.includes('cancel') || str.includes('fail')) {
      return '失敗'
    }
    return str || '-'
  }

  const openContactDialog = (field) => {
    const currentUser = getEffectiveUser()
    const currentValue = field === 'email' ? (currentUser?.email ?? '') : (currentUser?.phone ?? '')
    setContactField(field)
    setContactValue(currentValue || '')
    setContactError('')
  }

  const closeContactDialog = () => {
    if (contactSaving) return
    setContactField(null)
    setContactValue('')
    setContactError('')
  }

  const handleContactSubmit = async (e) => {
    e.preventDefault()
    if (!contactField) return
    const trimmed = contactValue.trim()
    if (!trimmed) {
      setContactError(contactField === 'email' ? '請輸入 Email' : '請輸入手機號碼')
      return
    }
    if (contactField === 'email' && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(trimmed)) {
      setContactError('請輸入有效的 Email')
      return
    }
    if (contactField === 'phone' && !/^[0-9+\-#* ]{6,}$/.test(trimmed)) {
      setContactError('請輸入有效的手機號碼')
      return
    }
    const currentUser = getEffectiveUser()
    const userId = currentUser?.user_id ?? currentUser?.id
    if (!userId) {
      setContactError('找不到使用者 ID')
      return
    }

    setContactSaving(true)
    setContactError('')
    const endpoint = contactField === 'email' ? '/api/users/update_mail' : '/api/users/update_phone'
    const params = new URLSearchParams({ user_id: String(userId) })
    params.append(contactField, trimmed)

    try {
      const resp = await fetch(`${endpoint}?${params.toString()}`, { method: 'POST' })
      if (!resp.ok) {
        throw new Error('更新失敗')
      }
      const data = await resp.json().catch(() => ({}))
      if (data.status !== 'success') {
        throw new Error(data.detail || '更新失敗')
      }
      const updatedUser = { ...(currentUser || {}), [contactField]: trimmed }
      setSessionUser(updatedUser)
      if (onLogin) {
        try { onLogin(updatedUser) } catch (err) { console.warn(err) }
      }
      setToastMsg(contactField === 'email' ? 'Email 已更新' : '手機已更新')
      setContactSaving(false)
      closeContactDialog()
    } catch (err) {
      console.error(err)
      setContactError(err.message || '更新失敗')
      setContactSaving(false)
    }
  }

  // ========== 介面渲染 ==========
  if (sessionLoading) {
    return <div className="auth-wrapper"><div className="auth-card">載入中…</div></div>
  }

  const effectiveUser = getEffectiveUser()
  const displayEmail = effectiveUser?.email || '尚未填寫'
  const displayPhone = effectiveUser?.phone || '尚未填寫'

  if (!effectiveUser) {
    return (
      <div className="auth-wrapper">
        <div className="auth-card">
          <h2 className="auth-title">尚未登入</h2>
          <p className="auth-subtitle">請先登入後再查看個人資訊。</p>
          <button
            className="line-login-button"
            onClick={() => {
              const ret = `${window.location.origin}/profile`
              window.location.href = `/auth/line/login?return_to=${encodeURIComponent(ret)}`
            }}
          >
            使用 LINE 登入
          </button>
        </div>
      </div>
    )
  }

  if (!user) {
    return (
      <div className="auth-wrapper">
        <div className="auth-card">
          <h2 className="auth-title">歡迎回來</h2>
          <p className="auth-subtitle">請使用 LINE 登入以繼續</p>
          <button className="line-login-button" onClick={() => {
            const ret = `${window.location.origin}/profile`
            window.location.href = `/auth/line/login?return_to=${encodeURIComponent(ret)}`
          }}>
            <img src="https://scdn.line-apps.com/n/line_reg_v2_oauth/img/naver/btn_login_base.png" alt="LINE Login" className="line-icon" />
            使用 LINE 登入
          </button>
        </div>
      </div>
    );
  }
  
    return (
      /* 主頁面內容 */
      <div className="container">
        {toastMsg && (
          <div
            style={{
              background: '#ecfdf5',
              border: '1px solid #34d399',
              color: '#065f46',
              padding: 10,
              borderRadius: 8,
              marginBottom: 12,
            }}
          >
            {toastMsg}
          </div>
        )}

        {/* 使用者 App 概覽 */}
        <section className="card profile-overview">
          <div className="overview-hero">
            <div className="overview-meta">
              <div className="meta-title">{user.username} 的帳戶</div>
              <div className="meta-list meta-inline">
                <div className="meta-item">
                  <div className="meta-label">狀態</div>
                  <div className="meta-value">{user?.role_display || '一般使用者'}</div>
                </div>

                <div className="meta-item">
                  <div className="meta-label">Email</div>
                  <div className="meta-value">
                    <span className="ellipsis" title={displayEmail}>
                      {displayEmail || '未設定'}
                    </span>
                    <button className="link-btn" onClick={() => openContactDialog('email')}>
                      修改
                    </button>
                  </div>
                </div>

                <div className="meta-item">
                  <div className="meta-label">手機</div>
                  <div className="meta-value">
                    <span className="ellipsis" title={displayPhone}>
                      {displayPhone || '未設定'}
                    </span>
                    <button className="link-btn" onClick={() => openContactDialog('phone')}>
                      修改
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* 預約紀錄 */}
        <MyReservations user={user} filterExpired={true} />

        {/* 最近行程 */}
        <RecentTrips
          trips={recentTrips}
          showMore={showMoreTrips}
          onToggle={() => setShowMoreTrips(!showMoreTrips)}
          statusText={statusText}
        />

        {/* 幫助區塊 */}
        <section className="card help-card" aria-labelledby="help-title">
          <div className="card-title" id="help-title">
            <span>幫助</span>
          </div>
          <div className="card-body">
            <div className="help-list">
              {/* 聯絡客服 */}
              <div
                className="help-item"
                style={{ display: 'flex', flexDirection: 'column', gap: '12px', padding: '8px 0' }}
              >
                <div className="help-left">
                  <div className="help-title" style={{ textAlign: 'center', fontWeight: 600, fontSize: '16px', marginBottom: '4px' }}>
                    聯絡客服
                  </div>
                  <div className="help-sub muted" style={{ fontSize: '13px', color: '#666', marginBottom: '8px' }}>
                    聯絡時間：週一–週五 09:00 – 18:00
                  </div>
                </div>

                <div
                  className="help-right"
                  style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: '8px' }}
                >
                  {/* 電話 */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <a
                      className="phone-pill"
                      href={`tel:${supportPhone}`}
                      aria-label={`撥打客服電話 ${supportPhone}`}
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '6px',
                        color: '#2563eb',
                        background: '#eef5ff',
                        borderRadius: '20px',
                        padding: '6px 12px',
                        fontWeight: 600,
                        textDecoration: 'none',
                        fontSize: '14px',
                      }}
                    >
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                        <path
                          d="M22 16.92v3a2 2 0 0 1-2.18 2 19.87 19.87 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.87 19.87 0 0 1 3.08 4.18 2 2 0 0 1 5 2h3a2 2 0 0 1 2 1.72c.12 1.05.38 2.08.78 3.02a2 2 0 0 1-.45 2.11L9.91 10.09a16 16 0 0 0 6 6l1.24-1.24a2 2 0 0 1 2.11-.45c.94.4 1.97.66 3.02.78A2 2 0 0 1 22 16.92z"
                          fill="currentColor"
                        />
                      </svg>
                      <span title={supportPhone}>{phoneDisplay}</span>
                    </a>
                    <button
                      type="button"
                      className="btn-icon btn-copy"
                      onClick={() => copyToClipboard(supportPhone)}
                      title="複製電話"
                    >
                      📋
                    </button>
                  </div>

                  {/* 信箱 */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <a
                      className="email-pill"
                      href={emailLink}
                      aria-label={`寄信至 ${supportEmail}`}
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '6px',
                        color: '#2563eb',
                        background: '#eef5ff',
                        borderRadius: '20px',
                        padding: '6px 12px',
                        fontWeight: 600,
                        textDecoration: 'none',
                        fontSize: '14px',
                      }}
                    >
                      <span title={supportEmail}>{supportEmail}</span>
                    </a>
                     <button
                      type="button"
                      className="btn-icon btn-copy"
                      onClick={() => copyToClipboard(supportEmail)}
                      title="複製信箱"
                    >
                      📋
                    </button>
                  </div>
                </div>
              </div>

              {/* 隱私政策 */}
              <div className="help-item">
                <div className="help-left">
                  <div className="help-title" style={{ textAlign: 'center' }}>隱私政策</div>
                  {/* <div className="help-sub muted">查看隱私政策與個資使用說明</div> */}
                </div>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={viewPrivacy}
                    style={{ width: '100%', display: 'block' }}
                  >
                    查看
                  </button>
              </div>

              {/* 預約規範 */}
              <div className="help-item">
                <div className="help-left">
                  <div className="help-title" style={{ textAlign: 'center' }}>預約規範</div>
                  {/* <div className="help-sub muted">查看預約規範說明</div> */}
                </div>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={viewReserve}
                    style={{ width: '100%', display: 'block' }}
                  >
                    查看
                  </button>
              </div>              

              {/* 權益與保障 */}
              <div className="help-item help-rights">
                <div className="help-left">
                  <div className="help-title" style={{ textAlign: 'center' }}>權益與保障</div>
                  <div className="help-sub muted">退款、申訴與個資權益重點</div>
                  <ul className="rights-list">
                    <li>
                      <strong>退款/退票：</strong>依本平台退票規範辦理，申請後 7 個工作日處理。
                    </li>
                    <li>
                      <strong>客訴處理：</strong>受理後 48 小時內回覆處理進度。
                    </li>
                    <li>
                      <strong>個資保護：</strong>可提出刪除或資料限縮請求，平台將依法定程序回覆。
                    </li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* 登出 */}
        <section className="card">
          <div className="list">
            <div className="item">
              <button className="btn btn-orange" onClick={handleLogout}>
                登出
              </button>
            </div>
          </div>
        </section>

        {/* 修改聯絡資訊 Modal */}
        {contactField && (
          <div className="modal-overlay">
            <div className="modal-card">
              <h3 style={{ fontWeight: '800', fontSize: '18px', marginBottom: '12px' }}>
                {contactField === 'email' ? '修改 Email' : '修改手機號碼'}
              </h3>
              <form onSubmit={handleContactSubmit} className="auth-form">
                <input
                  className="auth-input"
                  type={contactField === 'email' ? 'email' : 'tel'}
                  value={contactValue}
                  onChange={e => setContactValue(e.target.value)}
                  disabled={contactSaving}
                  placeholder={contactField === 'email' ? '請輸入新 Email' : '請輸入新手機號碼'}
                />
                {contactError && <div className="auth-error">{contactError}</div>}
                <div className="modal-actions">
                  <button type="submit" className="btn btn-blue" disabled={contactSaving}>
                    {contactSaving ? '儲存中...' : '儲存'}
                  </button>
                  <button type="button" className="btn btn-orange" onClick={closeContactDialog} disabled={contactSaving}>
                    取消
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* 隱私政策 Modal */}
        {showPrivacy && (
          <div className="modal-overlay">
            <div className="modal-card" style={{ maxHeight: '80vh', overflowY: 'auto' }}>
              <h3 className="help-title" style={{ fontWeight: '800', fontSize: '18px', marginBottom: '12px' }}>隱私政策          </h3>
              <pre style={{ whiteSpace: 'pre-wrap', fontSize: '14px' }}>{privacyContent}</pre>
              <div className="modal-actions">
                <button className="btn btn-orange" onClick={() => setShowPrivacy(false)}>
                  關閉
                </button>
              </div>
            </div>
          </div>
        )}

        {/* 預約規範 Modal */}
        {showReserve && (
          <div className="modal-overlay">
            <div className="modal-card" style={{ maxHeight: '80vh', overflowY: 'auto' }}>
              <h3 className="help-title" style={{ fontWeight: '800', fontSize: '18px', marginBottom: '12px' }}>預約規範          </h3>
              <pre style={{ whiteSpace: 'pre-wrap', fontSize: '14px' }}>{reserveContent}</pre>
              <div className="modal-actions">
                <button className="btn btn-orange" onClick={() => setShowReserve(false)}>
                  關閉
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    )

}
export default ProfilePage
