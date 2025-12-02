// src/App.jsx
import React, { useEffect, useState } from 'react'
import Header from './components/Header'
import BottomNav from './components/BottomNav'
import RoutesPage from './pages/Routes'
import ReservePage from './pages/Reserve'
import ProfilePage from './pages/Profile'
import { Routes, Route, useNavigate, useLocation, Navigate } from 'react-router-dom'
import NearbyStations from './components/NearbyStations'
import HomeView from './pages/HomeView'
import { AnimatePresence, motion } from 'framer-motion'
import FontSizeSwitcher from './components/FontSizeSwitcher'

export default function App() {
  const [user, setUser] = useState(null)
  const navigate = useNavigate()
  const location = useLocation()
  const [showNearby, setShowNearby] = useState(false)

  const handleAction = (name) => {
    console.log(`${name} 被觸發`)
    if (name && String(name).includes('附近')) {
      setShowNearby(true)
    }
  }

  const navMap = {
    '首頁': '/',
    '路線': '/routes',
    '預約': '/reserve',
    '個人': '/profile',
  }

  const handleNav = (name) => {
    const to = navMap[name]
    if (to) {
      navigate(to)
    } else {
      console.log(`${name} 沒有對應的路徑`)
    }
  }

  const activeLabel = (() => {
    if (location.pathname.startsWith('/routes')) return '路線'
    if (location.pathname.startsWith('/reserve')) return '預約'
    if (location.pathname.startsWith('/profile')) return '個人'
    return '首頁'
  })()

  // Persist user across sessions
  useEffect(() => {
    try {
      const raw = localStorage.getItem('hb_user')
      if (raw) setUser(JSON.parse(raw))
    } catch {}
  }, [])

  const handleLogin = (u) => {
    setUser(u)
    try { localStorage.setItem('hb_user', JSON.stringify(u)) } catch {}
  }
  const handleLogout = () => {
    setUser(null)
    try { localStorage.removeItem('hb_user') } catch {}
  }

  return (
    <div className="page-root">
      <Header />
      {/* 只在首頁顯示字體調整元件，並放在最下方 */}
      <div style={{ flex: 1, width: '100%' }}>
        <AnimatePresence mode="wait">
          <Routes location={location} key={location.pathname}>
            <Route
              path="/"
              element={
                <motion.div
                  initial={{ opacity: 0, x: 50 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -50 }}
                  transition={{ duration: 0.3 }}
                >
                  <HomeView onAction={handleAction} user={user} />
                </motion.div>
              }
            />
            <Route
              path="/routes"
              element={
                <motion.div
                  initial={{ opacity: 0, x: 50 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -50 }}
                  transition={{ duration: 0.3 }}
                >
                  <RoutesPage />
                </motion.div>
              }
            />
            <Route
              path="/reserve"
              element={
                <motion.div
                  initial={{ opacity: 0, x: 50 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -50 }}
                  transition={{ duration: 0.3 }}
                >
                  <ReservePage user={user} onRequireLogin={() => navigate('/profile?from=reserve')} />
                </motion.div>
              }
            />

            <Route
              path="/routes/:routeId"
              element={
                <motion.div
                  initial={{ opacity: 0, x: 50 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -50 }}
                  transition={{ duration: 0.3 }}
                >
                  <RoutesPage />
                </motion.div>
              }
            />
            <Route
              path="/routes/:routeId/stop/:stopOrder"
              element={
                <motion.div
                  initial={{ opacity: 0, x: 50 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -50 }}
                  transition={{ duration: 0.3 }}
                >
                  <RoutesPage />
                </motion.div>
              }
            />

            <Route
              path="/profile"
              element={
                <motion.div
                  initial={{ opacity: 0, x: 50 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: -50 }}
                  transition={{ duration: 0.3 }}
                >
                  <ProfilePage user={user} onLogin={handleLogin} onLogout={handleLogout} />
                </motion.div>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </AnimatePresence>
        {showNearby && <NearbyStations onClose={() => setShowNearby(false)} />}
      </div>
      <BottomNav onNavClick={handleNav} active={activeLabel} />
    </div>
  )
}
