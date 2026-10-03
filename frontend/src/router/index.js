import { createRouter, createWebHistory } from 'vue-router'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'dashboard', component: () => import('../views/DashboardView.vue') },
    { path: '/flood-map', name: 'flood-map', component: () => import('../views/FloodMapView.vue') },
    { path: '/scenes', name: 'scenes', component: () => import('../views/SceneSearchView.vue') },
    { path: '/reports', name: 'reports', component: () => import('../views/ReportCenterView.vue') },
  ],
})
