// src/router/index.ts
import { createRouter, createWebHistory } from 'vue-router'
import LoginPage from '../pages/LoginPage.vue'
import HomePage from '../pages/HomePage.vue'
import AdminManagement from '../pages/AdminManagement.vue'
import MemberManagement from '../pages/MemberManagement.vue'
import RouteManagement from '../pages/RouteManagement.vue'
import ReservationManagement from '../pages/ReservationManagement.vue'
import CarManagement from '../pages/CarManagement.vue'
import ScheduleManagement from '../pages/ScheduleManagement.vue'
import { isLoggedIn, getCurrentUser } from '../services/authService'

const routes = [
  { path: '/', component: LoginPage },
  { 
    path: '/home', 
    component: HomePage,
    meta: { requiresAuth: true }, // 標記需要認證
    children: [
      {
        path: 'admin-management',
        component: AdminManagement,
        meta: { requiresAuth: true }
      },
      {
        path: 'member-management',
        component: MemberManagement,
        meta: { requiresAuth: true }
      },
      {
        path: 'reservation-management',
        component: ReservationManagement,
        meta: { requiresAuth: true }
      },
      {
        path: 'car-management',
        component: CarManagement,
        meta: { requiresAuth: true }
      },
      {
        path: 'route-management',
        component: RouteManagement,
        meta: { requiresAuth: true }
      },
      {
        path: 'schedule-management',
        component: ScheduleManagement,
        meta: { requiresAuth: true }
      }
    ]
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 路由守衛：檢查認證狀態和權限
router.beforeEach((to, _from, next) => {
  console.log('🛡️ 路由守衛檢查:', to.path)
  
  // 如果目標路由需要認證
  if (to.meta.requiresAuth) {
    if (isLoggedIn()) {
      console.log('已登入，檢查權限', to.path)
      
      // 檢查 Dispatcher 權限
      const currentUser = getCurrentUser()
      const userRole = currentUser?.role?.toLowerCase()
      
      if (userRole === 'dispatcher') {
        // Dispatcher 只能存取特定頁面
        const allowedPaths = [
          '/home',
          '/home/reservation-management',
          '/home/car-management', 
          '/home/route-management',
          '/home/schedule-management'
        ]
        
        if (allowedPaths.includes(to.path)) {
          console.log('Dispatcher 有權限存取', to.path)
          next()
        } else {
          console.log('Dispatcher 沒有權限存取', to.path, '重定向到首頁')
          next('/home')
        }
      } else {
        // Super Admin 和 Admin 可以存取所有頁面
        console.log('管理員權限，允許進入', to.path)
        next()
      }
    } else {
      console.log('未登入，重定向到登入頁')
      next('/') // 重定向到登入頁
    }
  } else {
    // 如果已登入且要去登入頁，直接跳到首頁
    if (to.path === '/' && isLoggedIn()) {
      console.log('已登入，直接跳轉到首頁')
      next('/home')
    } else {
      next() // 允許進入
    }
  }
})

export default router
