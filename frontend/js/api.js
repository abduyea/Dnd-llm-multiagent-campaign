/**
 * api.js — All HTTP calls to the D&D Storyteller backend.
 * Returns plain objects; throws Error with .message on non-2xx.
 */

const API_BASE = "http://localhost:8000/api/v1";

async function _fetch(path, opts = {}) {
  const res = await fetch(API_BASE + path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { const d = await res.json(); msg = d.detail || d.message || msg; } catch {}
    throw new Error(msg);
  }
  return res.json();
}

// ── Health ──────────────────────────────────────────────
async function healthCheck() {
  const res = await fetch("http://localhost:8000/health");
  return res.json();
}

// ── Campaigns ───────────────────────────────────────────
async function listCampaigns() {
  return _fetch("/campaigns");
}
async function getCampaign(id) {
  return _fetch(`/campaigns/${id}`);
}
async function createCampaign({ name, description = "", world_setting = "" }) {
  return _fetch("/campaigns", { method: "POST", body: JSON.stringify({ name, description, world_setting }) });
}
async function updateCampaign(id, { name, description = "", world_setting = "", status = null }) {
  const body = { name, description, world_setting };
  if (status !== null) body.status = status;
  return _fetch(`/campaigns/${id}`, { method: "PUT", body: JSON.stringify(body) });
}
async function exportCampaign(id) {
  return _fetch(`/campaigns/${id}/export`);
}
async function importCampaign(bundle) {
  return _fetch("/campaigns/import", { method: "POST", body: JSON.stringify(bundle) });
}
async function deleteCampaign(id) {
  const res = await fetch(API_BASE + `/campaigns/${id}`, { method: "DELETE" });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { const d = await res.json(); msg = d.detail || msg; } catch {}
    throw new Error(msg);
  }
}

// ── Characters ──────────────────────────────────────────
async function listCharacters(campaignId) {
  return _fetch(`/campaigns/${campaignId}/characters`);
}
async function createCharacter(campaignId, data) {
  return _fetch(`/campaigns/${campaignId}/characters`, { method: "POST", body: JSON.stringify(data) });
}
async function updateCharacter(id, data) {
  return _fetch(`/characters/${id}`, { method: "PUT", body: JSON.stringify(data) });
}
async function deleteCharacter(id) {
  const res = await fetch(API_BASE + `/characters/${id}`, { method: "DELETE" });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { const d = await res.json(); msg = d.detail || msg; } catch {}
    throw new Error(msg);
  }
}

// ── Sessions ────────────────────────────────────────────
async function listSessions() {
  return _fetch("/sessions");
}
async function listCampaignSessions(campaignId) {
  return _fetch(`/campaigns/${campaignId}/sessions`);
}
async function getSession(id) {
  return _fetch(`/sessions/${id}`);
}
async function createSession(campaignId, name) {
  return _fetch("/sessions", { method: "POST", body: JSON.stringify({ campaign_id: campaignId, name }) });
}
async function endSession(id) {
  return _fetch(`/sessions/${id}/end`, { method: "POST", body: "{}" });
}
async function getSessionTurns(id) {
  return _fetch(`/sessions/${id}/turns`);
}
async function deleteSession(id) {
  const res = await fetch(API_BASE + `/sessions/${id}`, { method: "DELETE" });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { const d = await res.json(); msg = d.detail || msg; } catch {}
    throw new Error(msg);
  }
}

// ── Actions ─────────────────────────────────────────────
async function submitAction(sessionId, { character_id, action_type, description, target_id = null, dice_expression = null, enemies = [], location = null }) {
  return _fetch(`/sessions/${sessionId}/actions`, {
    method: "POST",
    body: JSON.stringify({ character_id, action_type, description, target_id, dice_expression, enemies, location }),
  });
}

// ── Streaming Actions ────────────────────────────────────
/**
 * Submit an action and receive SSE events via onChunk.
 * Events: {type:"result",...} → {type:"token",text:""} → {type:"done",...}
 */
async function submitActionStream(sessionId, body, onChunk) {
  const res = await fetch(API_BASE + `/sessions/${sessionId}/actions/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { const d = await res.json(); msg = d.detail || d.message || msg; } catch {}
    throw new Error(msg);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";
      for (const part of parts) {
        for (const line of part.split("\n")) {
          if (line.startsWith("data: ")) {
            try { onChunk(JSON.parse(line.slice(6))); } catch {}
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

// ── Demo ────────────────────────────────────────────────
async function createDemoCampaign() {
  return _fetch("/campaigns/demo", { method: "POST", body: "{}" });
}

// ── Stats ────────────────────────────────────────────────
async function getStats() {
  return _fetch("/stats");
}

// ── Dice ────────────────────────────────────────────────
async function rollDice(expression, seed = null) {
  return _fetch("/dice/roll", { method: "POST", body: JSON.stringify({ expression, seed }) });
}
