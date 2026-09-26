import { createRouter, createWebHistory } from 'vue-router'

import HomeView from '../views/HomeView.vue'
import ChecklistView from '../views/ChecklistView.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/tasks/:taskId/checklist', name: 'checklist', component: ChecklistView },
  ],
})
