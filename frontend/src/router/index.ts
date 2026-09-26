import { createRouter, createWebHistory } from 'vue-router'

import HomeView from '../views/HomeView.vue'
import ChecklistView from '../views/ChecklistView.vue'
import ResultsView from '../views/ResultsView.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/tasks/:taskId/checklist', name: 'checklist', component: ChecklistView },
    { path: '/tasks/:taskId/results', name: 'results', component: ResultsView },
  ],
})
