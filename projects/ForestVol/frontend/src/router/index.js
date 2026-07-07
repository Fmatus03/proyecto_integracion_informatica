import { createRouter, createWebHistory } from "vue-router";

const routes = [
  {
    path: "/",
    name: "dashboard",
    component: () => import("@/views/Dashboard.vue"),
    meta: { title: "Dashboard" },
  },
  {
    path: "/upload",
    name: "upload",
    component: () => import("@/views/Upload.vue"),
    meta: { title: "Carga y procesamiento" },
  },
  {
    path: "/process/:sessionId?",
    name: "process",
    component: () => import("@/views/ProcessDetail.vue"),
    meta: { title: "Detalle del proceso" },
  },
  {
    path: "/visualization/:sessionId?",
    name: "visualization",
    component: () => import("@/views/Visualization.vue"),
    meta: { title: "Visualizacion 3D" },
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;
