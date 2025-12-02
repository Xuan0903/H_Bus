// src/components/Header.jsx
import React from 'react'
import { useNavigate } from 'react-router-dom'

export default function Header() {
  const navigate = useNavigate()
  const handleLogo = () => {
    navigate('/')
  }

  return (
    <header className="header">
      <div className="header-inner">
        <div
          className="logo-square"
          role="button"
          tabIndex={0}
          onClick={handleLogo}
          onKeyDown={(e) => e.key === 'Enter' && handleLogo()}
          aria-label="回到首頁"
        >
          <img
            src="/LOGO.png"
            alt="市民小巴 Logo"
            className="logo-image"
          />
        </div>
        <div className="title-block">
          <div className="app-title">市民小巴</div>
          <div className="subtitle muted">即時動態</div>
        </div>
      </div>
    </header>
  )
}
