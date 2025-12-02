import React, { useEffect } from 'react';
import './FontSizeSwitcher.css';

const fontSizes = [16, 18, 20, 22, 24];

export default function FontSizeSwitcher() {
  useEffect(() => {
    // 頁面載入時讀取 localStorage
    const saved = localStorage.getItem('hb_fontsize');
    if (saved) {
      document.documentElement.style.setProperty('--base-font-size', saved + 'px');
    }
  }, []);

  const handleChange = (e) => {
    document.documentElement.style.setProperty('--base-font-size', e.target.value + 'px');
    localStorage.setItem('hb_fontsize', e.target.value);
  };

  return (
    <div className="font-size-switcher">
      <span className="font-size-label">字體大小：</span>
      <select className="font-size-select" onChange={handleChange} defaultValue={localStorage.getItem('hb_fontsize') || 16}>
        {fontSizes.map(size => (
          <option key={size} value={size}>{size}px</option>
        ))}
      </select>
    </div>
  );
}
