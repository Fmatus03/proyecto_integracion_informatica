<template>
  <div class="viewer-card">
    <div ref="container" class="viewer-canvas" />
    <div class="viewer-overlay">
      <el-tag :type="statusType" effect="dark">{{ statusLabel }}</el-tag>
      <span v-if="fileName">{{ fileName }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import * as THREE from "three";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { PLYLoader } from "three/examples/jsm/loaders/PLYLoader.js";

const props = defineProps({
  url: { type: String, default: "" },
  fileName: { type: String, default: "" },
});

const emit = defineEmits(["error", "ready"]);
const container = ref(null);
const status = ref("idle");
let renderer;
let scene;
let camera;
let animationId;
let modelGroup;
let resizeObserver;

const statusLabel = computed(() => {
  if (status.value === "ready") return "Modelo cargado";
  if (status.value === "loading") return "Cargando modelo";
  if (status.value === "failed") return "No disponible";
  return "Esperando modelo";
});

const statusType = computed(() => {
  if (status.value === "ready") return "success";
  if (status.value === "failed") return "danger";
  if (status.value === "loading") return "warning";
  return "info";
});

function initScene() {
  if (!container.value || renderer) return;
  scene = new THREE.Scene();
  scene.background = new THREE.Color(0x101816);

  camera = new THREE.PerspectiveCamera(45, 16 / 9, 0.01, 5000);
  camera.position.set(2.2, 1.6, 2.8);

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  container.value.appendChild(renderer.domElement);

  const hemi = new THREE.HemisphereLight(0xf4fff5, 0x26362d, 2.4);
  scene.add(hemi);
  const light = new THREE.DirectionalLight(0xffffff, 2.2);
  light.position.set(3, 4, 2);
  scene.add(light);

  const grid = new THREE.GridHelper(4, 24, 0x5f8172, 0x263d35);
  grid.position.y = -0.9;
  scene.add(grid);

  modelGroup = new THREE.Group();
  scene.add(modelGroup);

  resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(container.value);
  resize();
  animate();
}

function resize() {
  if (!container.value || !renderer || !camera) return;
  const width = Math.max(container.value.clientWidth, 320);
  const height = Math.max(container.value.clientHeight, 280);
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}

function clearModel() {
  if (!modelGroup) return;
  while (modelGroup.children.length) {
    const child = modelGroup.children.pop();
    child.traverse?.((object) => {
      object.geometry?.dispose?.();
      if (Array.isArray(object.material)) object.material.forEach((material) => material.dispose?.());
      else object.material?.dispose?.();
    });
  }
}

function frameModel(object) {
  const box = new THREE.Box3().setFromObject(object);
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const radius = Math.max(size.x, size.y, size.z) || 1;
  object.position.sub(center);
  object.scale.setScalar(1.8 / radius);
}

async function loadModel() {
  await nextTick();
  initScene();
  clearModel();
  if (!props.url) {
    status.value = "idle";
    return;
  }

  status.value = "loading";
  try {
    const response = await fetch(props.url);
    if (!response.ok) throw new Error(`Respuesta ${response.status}`);
    const buffer = await response.arrayBuffer();
    const lowerName = props.fileName.toLowerCase();

    if (lowerName.endsWith(".ply")) {
      const geometry = new PLYLoader().parse(buffer);
      geometry.computeVertexNormals();
      const material = new THREE.MeshStandardMaterial({ color: 0x6ab67b, roughness: 0.72, metalness: 0.04 });
      const mesh = new THREE.Mesh(geometry, material);
      frameModel(mesh);
      modelGroup.add(mesh);
    } else {
      const gltf = await new Promise((resolve, reject) => {
        new GLTFLoader().parse(buffer, "", resolve, reject);
      });
      frameModel(gltf.scene);
      modelGroup.add(gltf.scene);
    }

    status.value = "ready";
    emit("ready");
  } catch (error) {
    status.value = "failed";
    emit("error", error);
  }
}

function animate() {
  animationId = requestAnimationFrame(animate);
  if (modelGroup) modelGroup.rotation.y += 0.006;
  renderer?.render(scene, camera);
}

watch(() => props.url, loadModel, { immediate: true });

onBeforeUnmount(() => {
  if (animationId) cancelAnimationFrame(animationId);
  resizeObserver?.disconnect();
  clearModel();
  renderer?.dispose();
});
</script>
