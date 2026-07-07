import { reactive } from "vue";

const storageKey = "forestvol.sessions";

function loadStoredSessions() {
  try {
    return JSON.parse(localStorage.getItem(storageKey) || "[]");
  } catch {
    return [];
  }
}

export const sessionStore = reactive({
  currentSessionId: "",
  recentSessions: loadStoredSessions(),
});

export function rememberSession(sessionId, payload = {}) {
  if (!sessionId) return;
  const entry = {
    sessionId,
    state: payload.pipeline_state || payload.state || "VALIDATED",
    volume: payload.volume_m3 ?? null,
    updatedAt: new Date().toISOString(),
  };
  sessionStore.currentSessionId = sessionId;
  sessionStore.recentSessions = [entry, ...sessionStore.recentSessions.filter((item) => item.sessionId !== sessionId)].slice(0, 8);
  localStorage.setItem(storageKey, JSON.stringify(sessionStore.recentSessions));
}
