import { createRouter, createWebHistory } from 'vue-router'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'flood-map', component: () => import('../views/FloodMapView.vue') },
    { path: '/flood-map', redirect: '/' },
    { path: '/dashboard', name: 'dashboard', component: () => import('../views/DashboardView.vue') },
    { path: '/scenes', name: 'scenes', component: () => import('../views/SceneSearchView.vue') },
    { path: '/reports', name: 'reports', component: () => import('../views/ReportCenterView.vue') },
  ],
})
