/** Dual-write debug logs: ingest server + same-origin Next route. */
export function agentLog(payload: Record<string, unknown>) {
  const body = JSON.stringify({
    sessionId: "2cda69",
    timestamp: Date.now(),
    ...payload,
  });
  // #region agent log
  fetch("http://127.0.0.1:7781/ingest/08f6c092-5346-4b67-bd6d-f5c293b29325", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Debug-Session-Id": "2cda69",
    },
    body,
  }).catch(() => {});
  fetch("/_debug_ingest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
  }).catch(() => {});
  // #endregion
}
