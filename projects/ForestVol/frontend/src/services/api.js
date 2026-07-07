import axios from "axios";

const runtimeConfig = window.__FORESTVOL_CONFIG__ || {};
const apiBaseUrl = (runtimeConfig.API_BASE_URL || import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

if (!apiBaseUrl) {
  console.warn("ForestVol API URL is not configured. Set VITE_API_URL or API_BASE_URL.");
}

export const api = axios.create({
  baseURL: apiBaseUrl,
  timeout: 30000,
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const detail = error.response?.data?.detail;
    const message =
      detail?.message ||
      detail?.error_code ||
      error.response?.data?.message ||
      error.message ||
      "Error inesperado al comunicarse con el backend";

    return Promise.reject({
      message,
      status: error.response?.status,
      code: detail?.error_code || error.response?.data?.error_code,
      raw: error,
    });
  },
);

export function apiUrl(path) {
  return `${apiBaseUrl}${path}`;
}
