// Simple service worker for web notifications and push demo
// This file is served from /sw.js by Vite (public folder)

self.addEventListener('install', (event) => {
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim())
})

// Handle Web Push messages (from server). Not used in one-shot demo,
// but left here for future backend integration.
self.addEventListener('push', (event) => {
  let data = {}
  try { data = event.data ? event.data.json() : {} } catch (e) {}
  const title = data.title || '小巴通知'
  const options = {
    body: data.body || '您有一則新通知',
    icon: '/icon.png',
    badge: '/icon.png',
    data,
  }
  event.waitUntil(self.registration.showNotification(title, options))
})

// Optional: allow page to request SW to show a notification
self.addEventListener('message', (event) => {
  const { type, title, body } = event.data || {}
  if (type === 'SHOW_NOTIFICATION') {
    event.waitUntil(self.registration.showNotification(title || '小巴通知', {
      body: body || '',
      icon: '/icon.png',
    }))
  }
})

