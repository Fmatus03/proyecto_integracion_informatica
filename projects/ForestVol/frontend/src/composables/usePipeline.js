import { computed, onBeforeUnmount, ref } from "vue";
import { ElMessage } from "element-plus";
import { calibrateSession, getResults, startReconstruction } from "@/services/processService";
import { uploadImages } from "@/services/uploadService";
import { rememberSession } from "@/stores/sessionStore";
import { canPoll, isTerminalState } from "@/utils/labels";

export function usePipeline() {
  const selectedFiles = ref([]);
  const sessionId = ref("");
  const manualScale = ref("");
  const result = ref(null);
  const busy = ref(false);
  const logItems = ref([{ time: new Date(), message: "Listo para procesar." }]);
  const pollTimer = ref(null);

  const validFiles = computed(() =>
    selectedFiles.value.filter((file) => /\.(jpe?g|png)$/i.test(file.name)),
  );
  const hasEnoughFiles = computed(() => validFiles.value.length >= 10);

  function pushLog(message) {
    logItems.value = [{ time: new Date(), message }, ...logItems.value].slice(0, 20);
  }

  function setFiles(files) {
    selectedFiles.value = Array.from(files || []);
    result.value = null;
    pushLog(selectedFiles.value.length ? `${validFiles.value.length} imagenes validas seleccionadas.` : "Seleccion limpiada.");
  }

  function mergeResult(payload) {
    result.value = { ...(result.value || {}), ...payload };
    if (payload.session_id) {
      sessionId.value = payload.session_id;
      rememberSession(payload.session_id, payload);
    }
  }

  async function upload() {
    if (!hasEnoughFiles.value) {
      ElMessage.warning("Selecciona al menos 10 imagenes JPG/PNG.");
      return null;
    }
    const payload = await uploadImages(validFiles.value);
    mergeResult(payload);
    pushLog(`Carga completada: ${payload.image_count} imagenes.`);
    return payload;
  }

  async function calibrate() {
    if (!sessionId.value) {
      ElMessage.warning("Ingresa o crea un identificador de proceso.");
      return null;
    }
    const payload = await calibrateSession(sessionId.value, manualScale.value || null);
    mergeResult(payload);
    pushLog(`Calibracion completada: ${payload.scale_px_per_cm?.toFixed?.(3) || payload.scale_px_per_cm} px/cm.`);
    return payload;
  }

  async function reconstruct() {
    if (!sessionId.value) {
      ElMessage.warning("Ingresa o crea un identificador de proceso.");
      return null;
    }
    const payload = await startReconstruction(sessionId.value);
    mergeResult(payload);
    pushLog(payload.message || "Reconstruccion iniciada.");
    startPolling();
    return payload;
  }

  async function loadResults(targetSessionId = sessionId.value) {
    if (!targetSessionId) {
      ElMessage.warning("Ingresa un identificador de proceso.");
      return null;
    }
    sessionId.value = targetSessionId;
    const payload = await getResults(targetSessionId);
    mergeResult(payload);
    if (canPoll(payload.pipeline_state) && !pollTimer.value) startPolling();
    return payload;
  }

  async function runFullPipeline() {
    busy.value = true;
    try {
      pushLog("Iniciando flujo completo.");
      await upload();
      await calibrate();
      await reconstruct();
    } catch (error) {
      pushLog(`Proceso detenido: ${error.message}`);
      ElMessage.error(error.message);
    } finally {
      busy.value = false;
    }
  }

  async function runAction(action, label) {
    busy.value = true;
    try {
      return await action();
    } catch (error) {
      pushLog(`${label} fallo: ${error.message}`);
      ElMessage.error(error.message);
      return null;
    } finally {
      busy.value = false;
    }
  }

  function startPolling() {
    if (!sessionId.value) return;
    if (pollTimer.value) clearInterval(pollTimer.value);
    pollTimer.value = setInterval(async () => {
      try {
        const payload = await loadResults(sessionId.value);
        if (!payload || isTerminalState(payload.pipeline_state)) stopPolling();
      } catch (error) {
        pushLog(`Seguimiento interrumpido: ${error.message}`);
        stopPolling();
      }
    }, 3500);
    pushLog("Seguimiento automatico activo.");
  }

  function stopPolling() {
    if (pollTimer.value) clearInterval(pollTimer.value);
    pollTimer.value = null;
  }

  onBeforeUnmount(stopPolling);

  return {
    selectedFiles,
    validFiles,
    hasEnoughFiles,
    sessionId,
    manualScale,
    result,
    busy,
    logItems,
    pollTimer,
    setFiles,
    upload: () => runAction(upload, "Carga"),
    calibrate: () => runAction(calibrate, "Calibracion"),
    reconstruct: () => runAction(reconstruct, "Reconstruccion"),
    loadResults: (targetSessionId) => runAction(() => loadResults(targetSessionId), "Consulta"),
    runFullPipeline,
    startPolling,
    stopPolling,
  };
}
