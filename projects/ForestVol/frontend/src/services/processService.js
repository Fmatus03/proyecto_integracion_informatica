import { api, apiUrl } from "./api";

export async function checkHealth() {
  const { data } = await api.get("/health", { timeout: 8000 });
  return data;
}

export async function calibrateSession(sessionId, manualScalePxPerCm = null) {
  const body = manualScalePxPerCm ? { manual_scale_px_per_cm: Number(manualScalePxPerCm) } : {};
  const { data } = await api.post(`/api/calibrate/${encodeURIComponent(sessionId)}`, body, {
    timeout: 120000,
  });
  return data;
}

export async function startReconstruction(sessionId) {
  const { data } = await api.post(`/api/reconstruct/${encodeURIComponent(sessionId)}`, null, {
    timeout: 120000,
  });
  return data;
}

export async function getResults(sessionId) {
  const { data } = await api.get(`/api/results/${encodeURIComponent(sessionId)}`, {
    timeout: 45000,
  });
  return data;
}

export function modelUrl(sessionId) {
  return apiUrl(`/api/model/${encodeURIComponent(sessionId)}`);
}

export function exportUrl(sessionId, format) {
  return apiUrl(`/api/export/${encodeURIComponent(sessionId)}/${format}`);
}
