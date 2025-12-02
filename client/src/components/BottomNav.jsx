// src/components/BottomNav.jsx
import React from 'react'

export default function BottomNav({ onNavClick, active }) {
  const items = ['首頁', '路線', '預約', '個人']
  return (
    <nav className="bottom-nav" role="navigation" aria-label="主要選單">
      {items.map((it, idx) => (
        <div
          key={it}
          className={`nav-item ${active ? (active === it ? 'active' : '') : (idx === 0 ? 'active' : '')}`}
          role="button"
          tabIndex={0}
          onClick={() => (onNavClick ? onNavClick(it) : console.log(`${it} 被按下`))}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              onNavClick ? onNavClick(it) : console.log(`${it} 被按下`)
            }
          }}
        >
          {it}
        </div>
      ))}
    </nav>
  )
}
