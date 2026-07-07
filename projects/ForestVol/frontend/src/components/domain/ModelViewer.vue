<template>
  <div class="viewer-card">
    <div ref="container" class="viewer-canvas" />
    <div class="viewer-overlay">
      <el-tag :type="statusType" effect="dark">{{ statusLabel }}</el-tag>
      <span v-if="fileName">{{ fileName }}</span>
      <el-button v-if="status === 'ready'" size="small" :icon="RefreshRight" @click="fitCameraToCurrentModel">
        Reencuadrar
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import * as THREE from "three";
import { RefreshRight } from "@element-plus/icons-vue";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
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
let controls;
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
  camera.position.set(3, 2, 3);

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  container.value.appendChild(renderer.domElement);

  controls = new OrbitControls(camera, renderer.domElement);
  controls.autoRotate = true;
  controls.autoRotateSpeed = 0.7;
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.target.set(0, 0, 0);

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
  if (status.value === "ready") fitCameraToCurrentModel();
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
  object.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(object);
  if (box.isEmpty()) throw new Error("El modelo no contiene geometria visible");
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const radius = Math.max(size.length() / 2, 0.001);
  const targetRadius = 1.6;
  object.position.sub(center);
  object.scale.multiplyScalar(targetRadius / radius);
  object.updateMatrixWorld(true);
}

function fitCameraToCurrentModel() {
  if (!camera || !modelGroup || !modelGroup.children.length) return;

  modelGroup.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(modelGroup);
  if (box.isEmpty()) return;

  const sphere = box.getBoundingSphere(new THREE.Sphere());
  const radius = Math.max(sphere.radius, 0.1);
  const verticalFov = THREE.MathUtils.degToRad(camera.fov);
  const horizontalFov = 2 * Math.atan(Math.tan(verticalFov / 2) * camera.aspect);
  const limitingFov = Math.max(0.01, Math.min(verticalFov, horizontalFov));
  const distance = (radius / Math.sin(limitingFov / 2)) * 1.35;
  const direction = new THREE.Vector3(1.55, 1.05, 1.75).normalize();

  camera.position.copy(sphere.center).add(direction.multiplyScalar(distance));
  camera.near = Math.max(0.001, distance - radius * 4);
  camera.far = distance + radius * 5;
  camera.lookAt(sphere.center);
  camera.updateProjectionMatrix();

  if (controls) {
    controls.target.copy(sphere.center);
    controls.minDistance = Math.max(radius * 0.25, 0.05);
    controls.maxDistance = Math.max(radius * 8, distance * 2);
    controls.update();
  }
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

    modelGroup.rotation.set(0, 0, 0);
    fitCameraToCurrentModel();
    status.value = "ready";
    emit("ready");
  } catch (error) {
    status.value = "failed";
    emit("error", error);
  }
}

function animate() {
  animationId = requestAnimationFrame(animate);
  controls?.update();
  renderer?.render(scene, camera);
}

watch(() => props.url, loadModel, { immediate: true });

onBeforeUnmount(() => {
  if (animationId) cancelAnimationFrame(animationId);
  resizeObserver?.disconnect();
  clearModel();
  controls?.dispose();
  renderer?.dispose();
});
</script>
