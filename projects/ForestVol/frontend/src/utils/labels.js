export const pipelineStates = {
  VALIDATED: "Carga validada",
  CALIBRATION_PENDING: "Calibracion en curso",
  CALIBRATED: "Calibracion lista",
  RECONSTRUCTION_PENDING: "Reconstruccion en cola",
  RECONSTRUCTING: "Reconstruyendo modelo",
  POINT_CLOUD_READY: "Nube de puntos lista",
  MESH_PENDING: "Generando malla",
  COMPLETED: "Completado",
  FAILED: "Fallido",
};

export const confidenceLabels = {
  HIGH: "Alta",
  MEDIUM: "Media",
  LOW: "Baja",
};

export const gateLabels = {
  PASS: "Aprobado",
  WARNING: "Advertencia",
  FAIL: "Fallido",
  passed: "Aprobado",
  warning: "Advertencia",
  failed: "Fallido",
};

export function formatNumber(value, suffix = "") {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "--";
  return `${Number(value).toFixed(3)}${suffix}`;
}

export function stateLabel(state) {
  return pipelineStates[state] || state || "--";
}

export function isTerminalState(state) {
  return state === "COMPLETED" || state === "FAILED";
}

export function canPoll(state) {
  return ["RECONSTRUCTION_PENDING", "RECONSTRUCTING", "POINT_CLOUD_READY", "MESH_PENDING"].includes(state);
}
