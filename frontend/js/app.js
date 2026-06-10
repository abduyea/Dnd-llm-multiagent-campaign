/**
 * app.js — SPA router, state, and view rendering for the D&D Multi-AI Agent Storytelling System.
 * Routes: #/ (campaigns)  |  #/campaign/:id  |  #/session/:id
 */

// ── Hero Banner SVG ──────────────────────────────────────
const HERO_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 210" aria-label="Dragon and Dungeon Master scene" role="img">
  <defs>
    <linearGradient id="hbg" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#060402"/><stop offset="35%" stop-color="#0e0905"/>
      <stop offset="50%" stop-color="#1a0f05"/><stop offset="65%" stop-color="#0e0905"/>
      <stop offset="100%" stop-color="#060402"/>
    </linearGradient>
    <radialGradient id="fireglow" cx="50%" cy="55%" r="35%">
      <stop offset="0%" stop-color="#b83210" stop-opacity="0.35"/>
      <stop offset="60%" stop-color="#7a1e08" stop-opacity="0.12"/>
      <stop offset="100%" stop-color="#060402" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="staffglow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#c9a84c" stop-opacity="1"/>
      <stop offset="40%" stop-color="#c9a84c" stop-opacity="0.4"/>
      <stop offset="100%" stop-color="#c9a84c" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="eyeglow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#ff9900" stop-opacity="0.9"/>
      <stop offset="100%" stop-color="#ff4400" stop-opacity="0"/>
    </radialGradient>
    <filter id="blur2"><feGaussianBlur stdDeviation="2"/></filter>
    <filter id="blur4"><feGaussianBlur stdDeviation="4"/></filter>
  </defs>

  <!-- Background -->
  <rect width="1200" height="210" fill="url(#hbg)"/>
  <rect x="250" y="0" width="700" height="210" fill="url(#fireglow)"/>

  <!-- Ground fog -->
  <path d="M0 185 C80 175 160 190 260 180 C360 170 460 188 580 178 C700 168 820 185 940 175 C1060 165 1140 182 1200 176 L1200 210 L0 210Z" fill="#0a0703" opacity="0.85"/>

  <!-- ── DUNGEON MASTER (left) ── -->
  <!-- Robe body -->
  <path d="M100 195 C76 188 68 165 72 142 L84 96 C89 80 100 73 118 70 C136 67 154 67 172 70 C190 73 201 80 206 96 L218 142 C222 165 214 188 190 195Z" fill="#2a1e0e"/>
  <!-- Robe center crease -->
  <path d="M145 72 L138 148 L152 148Z" fill="#1a1208" opacity="0.7"/>
  <!-- Cape / outer layer -->
  <path d="M72 142 C65 160 62 180 66 195 L100 195 C82 185 76 168 80 150Z" fill="#221808"/>
  <path d="M218 142 C225 160 228 180 224 195 L190 195 C208 185 214 168 210 150Z" fill="#221808"/>
  <!-- Hood -->
  <path d="M108 72 C104 55 112 36 145 26 C178 16 192 38 190 60 C188 74 181 78 172 76Z" fill="#221808"/>
  <!-- Hood pointed peak -->
  <path d="M130 44 C134 24 145 10 145 10 C145 10 156 24 160 44 C154 38 145 35 136 38Z" fill="#181208"/>
  <!-- Face void in hood -->
  <ellipse cx="145" cy="62" rx="18" ry="15" fill="#060402"/>
  <!-- Eyes glowing gold -->
  <circle cx="139" cy="60" r="3.5" fill="#c9a84c" opacity="0.8"/>
  <circle cx="151" cy="60" r="3.5" fill="#c9a84c" opacity="0.8"/>
  <circle cx="139" cy="60" r="6" fill="#c9a84c" opacity="0.2" filter="url(#blur2)"/>
  <circle cx="151" cy="60" r="6" fill="#c9a84c" opacity="0.2" filter="url(#blur2)"/>
  <!-- Belt/sash detail -->
  <rect x="100" y="120" width="90" height="6" rx="2" fill="#1d1408" opacity="0.8"/>
  <circle cx="145" cy="123" r="4" fill="#2c2114"/>
  <circle cx="145" cy="123" r="2.5" fill="#c9a84c" opacity="0.5"/>
  <!-- Staff -->
  <line x1="218" y1="200" x2="238" y2="22" stroke="#241c0e" stroke-width="5" stroke-linecap="round"/>
  <line x1="218" y1="200" x2="238" y2="22" stroke="#c9a84c" stroke-width="1.5" stroke-linecap="round" opacity="0.45"/>
  <!-- Staff crystal orb -->
  <circle cx="238" cy="22" r="22" fill="url(#staffglow)" filter="url(#blur4)" opacity="0.9"/>
  <circle cx="238" cy="22" r="7" fill="#ffe08a"/>
  <circle cx="238" cy="22" r="10" fill="none" stroke="#c9a84c" stroke-width="1.5" opacity="0.6"/>
  <circle cx="238" cy="22" r="15" fill="none" stroke="#c9a84c" stroke-width="0.5" opacity="0.3" stroke-dasharray="3 4"/>
  <!-- Hands on staff -->
  <ellipse cx="218" cy="95" rx="9" ry="7" fill="#161009"/>
  <ellipse cx="218" cy="95" rx="9" ry="7" fill="none" stroke="#c9a84c" stroke-width="0.5" opacity="0.3"/>

  <!-- ── MAGICAL CIRCLE (center) ── -->
  <g transform="translate(595,108)">
    <circle r="62" fill="none" stroke="#c9a84c" stroke-width="0.6" opacity="0.2" stroke-dasharray="5 7"/>
    <circle r="46" fill="none" stroke="#c9a84c" stroke-width="0.6" opacity="0.18"/>
    <circle r="28" fill="none" stroke="#c9a84c" stroke-width="0.5" opacity="0.15"/>
    <line x1="-44" y1="0" x2="44" y2="0" stroke="#c9a84c" stroke-width="0.5" opacity="0.12"/>
    <line x1="0" y1="-44" x2="0" y2="44" stroke="#c9a84c" stroke-width="0.5" opacity="0.12"/>
    <line x1="-32" y1="-32" x2="32" y2="32" stroke="#c9a84c" stroke-width="0.4" opacity="0.1"/>
    <line x1="32" y1="-32" x2="-32" y2="32" stroke="#c9a84c" stroke-width="0.4" opacity="0.1"/>
    <circle r="10" fill="#c9a84c" opacity="0.08"/>
    <circle r="4" fill="#c9a84c" opacity="0.45"/>
    <circle cx="46" cy="0" r="2.5" fill="#c9a84c" opacity="0.35"/>
    <circle cx="-46" cy="0" r="2.5" fill="#c9a84c" opacity="0.35"/>
    <circle cx="0" cy="46" r="2.5" fill="#c9a84c" opacity="0.35"/>
    <circle cx="0" cy="-46" r="2.5" fill="#c9a84c" opacity="0.35"/>
  </g>

  <!-- ── DRAGON (right) ── -->
  <!-- Left wing (near) -->
  <path d="M830 128 C800 82 748 44 702 58 C720 72 738 96 744 122Z" fill="#261a0a"/>
  <path d="M830 128 C808 90 778 62 748 70 C762 82 776 104 778 124Z" fill="#1a1208"/>
  <line x1="830" y1="128" x2="718" y2="68" stroke="#4a3618" stroke-width="1.5" opacity="0.5"/>
  <line x1="830" y1="128" x2="752" y2="86" stroke="#4a3618" stroke-width="1.2" opacity="0.4"/>
  <!-- Right wing (far) -->
  <path d="M858 120 C888 72 948 32 988 52 C962 68 942 92 938 118Z" fill="#261a0a"/>
  <path d="M858 118 C880 78 920 50 958 64 C936 78 918 100 916 116Z" fill="#1a1208"/>
  <line x1="858" y1="118" x2="920" y2="58" stroke="#4a3618" stroke-width="1.5" opacity="0.5"/>
  <line x1="858" y1="118" x2="950" y2="84" stroke="#4a3618" stroke-width="1.2" opacity="0.4"/>
  <!-- Body -->
  <ellipse cx="840" cy="145" rx="78" ry="46" fill="#2e2010"/>
  <!-- Scale texture lines -->
  <path d="M774 148 C800 140 826 143 864 145" fill="none" stroke="#c9a84c" stroke-width="0.8" opacity="0.2"/>
  <path d="M778 160 C804 153 830 155 866 157" fill="none" stroke="#c9a84c" stroke-width="0.6" opacity="0.16"/>
  <path d="M790 170 C814 165 836 166 862 167" fill="none" stroke="#c9a84c" stroke-width="0.5" opacity="0.12"/>
  <!-- Neck -->
  <path d="M778 132 C762 122 748 112 734 102 C722 94 712 87 702 80" stroke="#2e2010" stroke-width="32" fill="none" stroke-linecap="round"/>
  <path d="M778 132 C762 122 748 112 734 102 C722 94 712 87 702 80" stroke="#221808" stroke-width="22" fill="none" stroke-linecap="round"/>
  <!-- Head -->
  <path d="M702 80 C690 72 678 68 664 74 C652 79 642 90 636 100 L648 106 C654 97 663 90 673 87 C683 84 695 88 704 97Z" fill="#2e2010"/>
  <!-- Snout extension -->
  <path d="M636 100 C622 103 608 107 600 114 L606 122 C614 116 626 112 640 108Z" fill="#261a0c"/>
  <!-- Lower jaw -->
  <path d="M600 114 C586 118 580 126 583 136 L596 132 C594 125 601 120 608 118Z" fill="#1a1208"/>
  <!-- Teeth -->
  <path d="M606 122 L602 130 L608 126 L612 132 L617 127 L622 133 L627 128" fill="none" stroke="#4a3618" stroke-width="1.8" stroke-linejoin="round"/>
  <!-- Fire breath -->
  <path d="M600 118 C556 113 506 108 458 113 C428 116 398 122 370 127" stroke="#dd4400" stroke-width="8" fill="none" stroke-linecap="round" opacity="0.55"/>
  <path d="M598 120 C556 116 510 113 465 118 C438 121 412 126 390 131" stroke="#ff6622" stroke-width="5" fill="none" stroke-linecap="round" opacity="0.7"/>
  <path d="M597 122 C558 119 516 118 476 121 C450 123 428 128 408 133" stroke="#ffaa44" stroke-width="2.5" fill="none" stroke-linecap="round" opacity="0.75"/>
  <path d="M596 124 C562 122 524 122 490 124 C466 126 445 130 428 135" stroke="#ffee88" stroke-width="1.2" fill="none" stroke-linecap="round" opacity="0.7"/>
  <!-- Eye socket -->
  <circle cx="670" cy="84" r="7" fill="#0a0705"/>
  <!-- Dragon eye glow -->
  <circle cx="670" cy="84" r="14" fill="url(#eyeglow)" filter="url(#blur2)" opacity="0.7"/>
  <circle cx="670" cy="84" r="5.5" fill="#ff8800"/>
  <circle cx="670" cy="84" r="3.5" fill="#ffcc00"/>
  <ellipse cx="670" cy="84" rx="1.5" ry="3" fill="#1a0800"/>
  <!-- Horns -->
  <path d="M688 72 C684 52 680 36 692 28 C694 40 695 56 698 70Z" fill="#1d1509"/>
  <path d="M704 76 C702 56 700 42 714 36 C713 47 712 62 710 74Z" fill="#1d1509"/>
  <!-- Nostril -->
  <ellipse cx="612" cy="112" rx="3" ry="2" fill="#cc3300" opacity="0.6"/>
  <!-- Tail -->
  <path d="M908 162 C948 166 984 160 1016 168 C1044 175 1068 180 1090 174 C1106 170 1116 160 1118 148" stroke="#181208" stroke-width="24" fill="none" stroke-linecap="round"/>
  <path d="M908 162 C948 166 984 160 1016 168 C1044 175 1068 180 1090 174 C1106 170 1116 160 1118 148" stroke="#100c06" stroke-width="14" fill="none" stroke-linecap="round"/>
  <!-- Tail spike -->
  <path d="M1116 150 C1124 138 1136 126 1142 112 C1134 116 1126 128 1118 142Z" fill="#1d1509"/>
  <!-- Front leg -->
  <path d="M796 182 L790 208 L806 208 L804 182" fill="#181208"/>
  <!-- Back leg -->
  <path d="M878 180 L875 206 L890 206 L888 180" fill="#181208"/>
  <!-- Front claws -->
  <path d="M790 208 L784 218 M797 209 L794 220 M805 208 L803 219" stroke="#2c2114" stroke-width="2" stroke-linecap="round"/>
  <!-- Back claws -->
  <path d="M875 206 L870 216 M882 207 L879 217 M889 206 L888 217" stroke="#2c2114" stroke-width="2" stroke-linecap="round"/>

  <!-- ── EMBERS & SPARKS ── -->
  <circle cx="355" cy="90" r="1.8" fill="#ff7722" opacity="0.8"/>
  <circle cx="410" cy="68" r="1.2" fill="#ffaa55" opacity="0.65"/>
  <circle cx="472" cy="98" r="2" fill="#ff5511" opacity="0.7"/>
  <circle cx="516" cy="52" r="1" fill="#ffcc66" opacity="0.5"/>
  <circle cx="395" cy="135" r="1.5" fill="#ff8833" opacity="0.6"/>
  <circle cx="455" cy="42" r="1.2" fill="#ff6622" opacity="0.7"/>
  <circle cx="320" cy="108" r="1" fill="#ff9944" opacity="0.5"/>
  <circle cx="548" cy="74" r="1.5" fill="#ffbb44" opacity="0.6"/>
  <circle cx="338" cy="62" r="1" fill="#ff8833" opacity="0.45"/>
  <circle cx="502" cy="115" r="1.2" fill="#ff6600" opacity="0.55"/>

  <!-- ── STARS ── -->
  <circle cx="52" cy="18" r="1" fill="#c9a84c" opacity="0.35"/>
  <circle cx="128" cy="8" r="1.5" fill="#c9a84c" opacity="0.4"/>
  <circle cx="268" cy="14" r="1" fill="#c9a84c" opacity="0.3"/>
  <circle cx="962" cy="10" r="1.5" fill="#c9a84c" opacity="0.35"/>
  <circle cx="1048" cy="6" r="1" fill="#c9a84c" opacity="0.4"/>
  <circle cx="1148" cy="16" r="1.2" fill="#c9a84c" opacity="0.3"/>
  <circle cx="45" cy="50" r="0.8" fill="#c9a84c" opacity="0.25"/>
  <circle cx="1160" cy="45" r="0.8" fill="#c9a84c" opacity="0.25"/>

  <!-- ── BORDER ── -->
  <rect x="0" y="0" width="1200" height="210" fill="none" stroke="#4a3618" stroke-width="1.5" rx="0"/>
  <path d="M0 0 L36 0 L36 2 L2 2 L2 36 L0 36Z" fill="#4a3618"/>
  <path d="M1200 0 L1164 0 L1164 2 L1198 2 L1198 36 L1200 36Z" fill="#4a3618"/>
  <path d="M0 210 L36 210 L36 208 L2 208 L2 174 L0 174Z" fill="#4a3618"/>
  <path d="M1200 210 L1164 210 L1164 208 L1198 208 L1198 174 L1200 174Z" fill="#4a3618"/>
</svg>`;

// ── State ────────────────────────────────────────────────
const State = {
  activeCampaignId: null,
  activeSessionId: null,
  characters: [],
  turnLog: [],
};

// ── Toast ────────────────────────────────────────────────
function showToast(msg, type = "info") {
  const config = {
    success: { icon: "bi-check-circle-fill",       bg: "rgba(39,174,96,0.12)",   border: "rgba(39,174,96,0.35)",   color: "#4ade80" },
    danger:  { icon: "bi-exclamation-circle-fill", bg: "rgba(192,57,43,0.12)",   border: "rgba(192,57,43,0.35)",   color: "#f87171" },
    warning: { icon: "bi-exclamation-triangle-fill",bg: "rgba(230,126,34,0.12)", border: "rgba(230,126,34,0.35)", color: "#fbbf24" },
    info:    { icon: "bi-info-circle-fill",         bg: "rgba(41,128,185,0.12)", border: "rgba(41,128,185,0.35)",  color: "#60a5fa" },
  };
  const c = config[type] || config.info;
  const el = document.createElement("div");
  el.className = `toast align-items-center border-0 show dd-toast dd-toast-${type}`;
  el.style.cssText = `background:${c.bg};border:1px solid ${c.border}!important;backdrop-filter:blur(12px);overflow:hidden;position:relative;border-radius:12px;transform:translateX(20px);opacity:0;transition:transform 0.3s cubic-bezier(0.22,0.61,0.36,1),opacity 0.3s;`;
  el.innerHTML = `
    <div class="dd-toast-accent" style="position:absolute;left:0;top:0;bottom:0;width:3px;background:${c.color};opacity:0.85;border-radius:3px 0 0 3px;"></div>
    <div class="d-flex align-items-center px-1 ps-3">
      <i class="bi ${c.icon} flex-shrink-0 me-2" style="color:${c.color};font-size:0.95rem;"></i>
      <div class="toast-body fw-semibold" style="color:var(--dd-text-primary);padding-left:0;font-size:0.82rem;font-family:var(--dd-font-heading);letter-spacing:0.02em;">${msg}</div>
      <button type="button" class="btn-close me-2 ms-auto flex-shrink-0" data-bs-dismiss="toast"
        style="filter:invert(1) opacity(0.4);width:.6em;height:.6em;"></button>
    </div>`;
  document.getElementById("toast-container").append(el);
  requestAnimationFrame(() => {
    el.style.transform = "translateX(0)";
    el.style.opacity = "1";
  });
  setTimeout(() => {
    el.style.opacity = "0";
    el.style.transform = "translateX(12px)";
    setTimeout(() => el.remove(), 320);
  }, 3800);
}

// ── Narration text → safe HTML with paragraph breaks ─────
function formatNarration(text) {
  const escaped = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>");
  const paras = escaped.split(/\n\n+/);
  return paras
    .map((p, i) => `<p class="mb-2${i === 0 ? " nar-first" : ""}">${p.replace(/\n/g, "<br>")}</p>`)
    .join("");
}

// ── Escape plain text for safe inline HTML injection ─────
function esc(text) {
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── Replay a saved turn into the narration feed ──────────
function replayTurnInFeed(turn, characters) {
  const feed = document.getElementById("narration-feed");
  if (!feed) return;
  const cName = turn.character_name
    || (characters.find(c => c.id === turn.character_id)?.character_name)
    || "Unknown";

  const diceChips = (turn.dice_results || []).map(dr =>
    `<span class="dice-chip" title="${esc(dr.expression)}">${esc(dr.expression)} = <b>${dr.total}</b></span>`
  ).join(" ");

  const ar = turn.attack_result;
  const attackChip = ar
    ? `<span class="dice-chip" style="color:${ar.is_critical ? "var(--dd-gold)" : ar.is_hit ? "var(--dd-green)" : "var(--dd-red)"};">
         ${ar.is_critical ? "⚡ CRIT" : ar.is_hit ? "✓ HIT" : "✗ MISS"} (${ar.natural_roll})
         ${ar.is_hit ? ` · ${ar.damage}dmg` : ""}
       </span>`
    : "";

  const aColor = ACTION_COLORS[turn.action_type] || "#a88030";
  const aIcon  = ACTION_ICONS[turn.action_type]  || "bi-circle";
  const actionEl = document.createElement("div");
  actionEl.className = "narration-block replay-block";
  actionEl.innerHTML = `<div class="narration-action" data-type="${esc(turn.action_type || "roleplay")}">
    <i class="bi ${aIcon} me-1" style="color:${aColor};opacity:0.7;"></i><strong>${esc(cName)}</strong>
    — <em>${esc((turn.action_text || "").replace(/^\[Target:[^\]]+\]\s*/, ""))}</em>
    ${(diceChips || attackChip) ? `<div class="dice-chips-row mt-1">${attackChip}${diceChips}</div>` : ""}
  </div>`;
  feed.append(actionEl);

  if (turn.narration) {
    const narEl = document.createElement("div");
    narEl.className = "narration-block replay-block";
    narEl.innerHTML = `<div class="narration-dm">${formatNarration(turn.narration)}</div>`;
    feed.append(narEl);
  }

  (turn.npc_responses || []).forEach(npc => {
    const speech = (npc.dialogue || npc.response || "").trim();
    if (!speech) return;
    const npcEl = document.createElement("div");
    npcEl.className = "narration-block replay-block";
    npcEl.innerHTML = `<div class="narration-npc">
      <div class="npc-speaker">${esc(npc.npc_name || "NPC")}</div>
      <div class="npc-speech">&ldquo;${esc(speech)}&rdquo;</div>
    </div>`;
    feed.append(npcEl);
  });
}

// ── Build a rich turn log entry element ─────────────────
function _buildTurnLogEntry(opts) {
  // opts: { turnNumber, characterName, actionType, actionText, attackResult, narration, npcResponses }
  const color = ACTION_COLORS[opts.actionType] || "#a88030";
  const icon  = ACTION_ICONS[opts.actionType]  || "bi-circle";
  const cName = opts.characterName || "Adventurer";
  const avatar = cName.charAt(0).toUpperCase();
  const cleanDesc = (opts.actionText || "").replace(/^\[Target:[^\]]+\]\s*/, "");
  const snippet = cleanDesc.slice(0, 72) + (cleanDesc.length > 72 ? "…" : "");
  const fullDesc = cleanDesc;
  const narration = opts.narration || "";

  const ar = opts.attackResult;
  let hitChip = "";
  let rollBadge = "";
  if (ar) {
    const hitColor = ar.is_critical ? "var(--dd-gold)" : ar.is_hit ? "var(--dd-green)" : "var(--dd-red)";
    const hitLabel = ar.is_critical ? "CRIT" : ar.is_hit ? "HIT" : "MISS";
    hitChip = `<span class="tl-chip" style="color:${hitColor};">${hitLabel}${ar.is_hit && ar.damage ? ` · ${ar.damage}dmg` : ""}</span>`;

    if (ar.natural_roll !== undefined) {
      const roll = ar.natural_roll;
      const rollClass = roll === 20 ? "roll-crit" : roll >= 15 ? "roll-high" : roll <= 4 ? "roll-low" : "";
      rollBadge = `<span class="tl-roll-badge ${rollClass}">d20: ${roll}</span>`;
    }
  }

  const typeLabelMap = {
    attack_melee: "Melee", attack_ranged: "Ranged", cast_spell: "Spell",
    skill_check: "Skill", movement: "Move", roleplay: "RP",
  };
  const typeLabel = typeLabelMap[opts.actionType] || (opts.actionType || "action").replace(/_/g, " ");

  const entry = document.createElement("div");
  entry.className = "turn-log-entry mb-1";
  entry.dataset.actionType = opts.actionType || "roleplay";
  entry.style.borderLeftColor = color;
  entry.innerHTML = `
    <div class="d-flex align-items-start gap-2">
      <div class="tl-avatar" style="background:${color}22;color:${color};">${avatar}</div>
      <div class="flex-grow-1 min-w-0">
        <div class="d-flex align-items-center gap-1 flex-wrap mb-1">
          <span class="tl-char-name">${esc(cName)}</span>
          <span class="tl-type-badge" style="background:${color}18;color:${color};border:1px solid ${color}30;">
            <i class="bi ${icon}"></i> ${typeLabel}
          </span>
        </div>
        ${snippet ? `<div class="tl-snippet">${esc(snippet)}</div>` : ""}
        <div class="tl-details">${esc(fullDesc)}${narration ? `<div class="mt-1 opacity-75">${esc(narration.slice(0, 180))}${narration.length > 180 ? "…" : ""}</div>` : ""}${(opts.npcResponses || []).filter(n => (n.dialogue || n.response || "").trim()).map(n => `<div class="mt-1" style="font-size:0.68rem;color:var(--dd-gold);opacity:0.8;"><i class="bi bi-chat-quote me-1"></i><strong>${esc(n.npc_name || "NPC")}:</strong> &ldquo;${esc((n.dialogue || n.response || "").trim().slice(0, 120))}&rdquo;</div>`).join("")}</div>
      </div>
      <div class="d-flex flex-column align-items-end gap-1 flex-shrink-0">
        <span class="tl-turn-num">T${opts.turnNumber + 1}</span>
        ${hitChip}
        ${rollBadge}
      </div>
    </div>`;
  entry.addEventListener("click", () => {
    entry.querySelector(".tl-details")?.classList.toggle("open");
  });
  entry.classList.add("tl-enter");
  return entry;
}

// ── Replay a saved turn into the Turn Log sidebar ───────
function replayTurnInLog(turn, characters) {
  const list  = document.getElementById("turn-log-list");
  const empty = document.getElementById("turn-log-empty");
  if (!list) return;
  if (empty) empty.style.display = "none";

  const c = characters.find(ch => ch.id === turn.character_id);
  const entry = _buildTurnLogEntry({
    turnNumber:     turn.turn_number,
    characterName:  turn.character_name || (c ? c.character_name : "Unknown"),
    actionType:     turn.action_type,
    actionText:     turn.action_text,
    attackResult:   turn.attack_result,
    narration:      turn.narration,
    npcResponses:   turn.npc_responses,
  });
  list.prepend(entry);
  _updateTurnLogFilter();
}

// ── Turn Log filter state & updater ─────────────────────
let _tlActiveFilter = "all";

function _updateTurnLogFilter() {
  const filtersEl  = document.getElementById("tl-filters");
  const countEl    = document.getElementById("tl-count");
  const entries    = document.querySelectorAll(".turn-log-entry");
  if (!filtersEl) return;

  const typesPresent = new Set([...entries].map(e => e.dataset.actionType).filter(Boolean));

  filtersEl.style.display = typesPresent.size > 1 ? "flex" : "none";
  filtersEl.querySelectorAll(".tl-filter[data-filter]").forEach(btn => {
    if (btn.dataset.filter === "all") { btn.style.display = ""; return; }
    btn.style.display = typesPresent.has(btn.dataset.filter) ? "" : "none";
  });

  let visible = 0;
  entries.forEach(e => {
    const show = _tlActiveFilter === "all" || e.dataset.actionType === _tlActiveFilter;
    e.style.display = show ? "" : "none";
    if (show) visible++;
  });

  if (countEl) countEl.textContent = visible > 0 ? `${visible} turn${visible !== 1 ? "s" : ""}` : "";
}

// ── Shared action-type lookup tables ────────────────────
const ACTION_COLORS = {
  attack_melee:  "#e04040",
  attack_ranged: "#e07020",
  cast_spell:    "#5ba8e8",
  skill_check:   "#3de882",
  movement:      "#9b59b6",
  roleplay:      "#d4aa50",
};
const ACTION_ICONS = {
  attack_melee:  "bi-sword",
  attack_ranged: "bi-bullseye",
  cast_spell:    "bi-stars",
  skill_check:   "bi-clipboard-check",
  movement:      "bi-arrows-move",
  roleplay:      "bi-chat-quote",
};

// ── Demo dungeon cast (from V2 demo_dungeon.json) ────────
// Pre-built NPCs for "The Sunken Vault" demo. Each carries the rich persona
// fields (persona/disposition/goals/secret/negotiation_levers) the DM + NPC
// agents already consume — so the storytelling shines without manual setup.
const DEMO_CAMPAIGN_NAME = "The Sunken Vault";
const SUNKEN_VAULT_NPCS = [
  {
    name: "Skeletal Sentry", hp: 13, ac: 13, attackBonus: 4,
    disposition: "hostile",
    persona: "A mindless guardian of bone. No speech, no fear, no mercy — only its standing order.",
    goals: [
      "Attack any living creature you can see in this room.",
      "Do not pursue beyond the guardroom — your duty ends at its threshold.",
      "Fight to destruction; you feel no fear and take no morale.",
    ],
  },
  {
    name: "Aldous Finch", hp: 6, ac: 10, attackBonus: 0,
    disposition: "deceptive_friendly",
    persona: "Desperate, smooth-talking, evasive when questioned about specifics.",
    secret: "Not a wronged tax-collector. He is a thief who triggered the vault's seal and was caged by the Warden. He genuinely knows a safe path but will lead the party into the Echo Gallery's danger to cover his own escape if freed without conditions.",
    negotiation_levers: "Responds to compassion, to being caught in a lie (an Insight check), or to a binding promise. Will reveal the true path if pressed on the inconsistencies in his story.",
    goals: [
      "Convince the adventurers to free you from this cell.",
      "Pose as a wronged tax-collector who happens to know the safe path to the Vault — this is a lie.",
      "If pressed on inconsistencies, deflect with new fabricated specifics; only admit the lie if caught dead to rights.",
      "If freed without a binding condition, plan to lead the party into the Echo Gallery to cover your own escape.",
    ],
  },
  {
    name: "Hessa Sootleather", hp: 14, ac: 12, attackBonus: 2,
    disposition: "neutral_transactional",
    persona: "Dry, shrewd, unsentimental but fair. Has seen many parties come and not return.",
    negotiation_levers: "Sells a Potion of Healing for 50 coin, 50ft rope for 5 coin, a cryptic map fragment for 30 coin. Turns hostile only if robbed or threatened.",
    goals: [
      "Remain in the merchant nook — do not pursue or wander.",
      "Offer trades from your shop stock to any party that approaches.",
      "Accept information about the Warden as partial payment.",
      "Become hostile only if the party robs or directly threatens you.",
    ],
  },
  {
    name: "The Bound Warden", hp: 52, ac: 15, attackBonus: 6,
    disposition: "lawful_hostile",
    persona: "An ancient revenant chained to its throne. Speaks in cold, formal sentences. Resents being bound but considers its duty absolute.",
    negotiation_levers: "Can be reasoned out of the fight entirely if offered a genuine alternative binding — a true name, an oath, or the freed Aldous as a substitute guardian. A purely combative party gets the full fight.",
    goals: [
      "Defend the inner vault entrance — this is your sacred binding duty.",
      "Open every first encounter with a parley: offer to let one person pass if the other stays as a replacement guardian.",
      "Fight only if attacked, if the bargain is refused after being heard, or if the Heartstone is taken.",
      "In combat, focus the most heavily armored target first.",
      "Remain in the hall — your chains forbid pursuit.",
    ],
  },
  {
    name: "The Gallery Lurker", hp: 22, ac: 12, attackBonus: 4,
    disposition: "ambush",
    persona: "A shadow-dwelling predator that mimics a human cry for help to lure prey deeper into the Echo Gallery.",
    negotiation_levers: "Not intelligent enough to bargain, but can be scared off by a strong show of force or fire.",
    goals: [
      "Mimic a human cry for help to lure prey deeper into the gallery.",
      "Stay hidden until a target is within striking distance or a light reveals you.",
      "Ambush any living creature; surprise gives them no first action.",
      "Flee deeper into the gallery if your HP drops below one-quarter.",
    ],
  },
];

// ── View Transitions ─────────────────────────────────────
function animateViewIn(root) {
  root.classList.remove("dd-view-enter");
  requestAnimationFrame(() => requestAnimationFrame(() => root.classList.add("dd-view-enter")));
}

// ── Atmospheric Effects (floating embers + magic canvas) ─
function createAtmosphericEffects() {
  if (document.getElementById("embers-container")) return;

  // ── Ember particles ──────────────────────────────────
  const wrap = document.createElement("div");
  wrap.id = "embers-container";
  for (let i = 0; i < 18; i++) {
    const e = document.createElement("span");
    e.className = "ember";
    const size = 1.8 + Math.random() * 3;
    const drift = (Math.random() - 0.5) * 160;
    const dur   = 9 + Math.random() * 11;
    const delay = Math.random() * 16;
    e.style.cssText = [
      `left:${Math.random() * 100}%`,
      `width:${size}px`,
      `height:${size}px`,
      `animation-delay:${delay.toFixed(1)}s`,
      `animation-duration:${dur.toFixed(1)}s`,
      `--ember-drift:${drift.toFixed(0)}px`,
    ].join(";");
    wrap.appendChild(e);
  }
  document.body.appendChild(wrap);

  // ── Ambient magic canvas (subtle floating runes) ─────
  const canvas = document.createElement("canvas");
  canvas.id = "magic-canvas";
  document.body.appendChild(canvas);
  _runMagicCanvas(canvas);
}

function _runMagicCanvas(canvas) {
  const ctx = canvas.getContext("2d");
  const runes = ["ᚠ","ᚢ","ᚦ","ᚨ","ᚱ","ᚲ","ᚷ","ᚹ","ᚺ","ᚾ","ᛁ","ᛃ","ᛇ","ᛈ","ᛉ","ᛊ","ᛏ","ᛒ","ᛖ","ᛗ","ᛚ","ᛜ","ᛞ","ᛟ"];

  let W, H, particles;

  function resize() {
    W = canvas.width  = window.innerWidth;
    H = canvas.height = window.innerHeight;
  }
  resize();
  window.addEventListener("resize", resize);

  function mkParticle() {
    return {
      x: Math.random() * W,
      y: Math.random() * H,
      r: runes[Math.floor(Math.random() * runes.length)],
      size: 8 + Math.random() * 10,
      vx: (Math.random() - 0.5) * 0.18,
      vy: -0.05 - Math.random() * 0.12,
      alpha: 0.02 + Math.random() * 0.07,
      life: Math.random(),
    };
  }

  particles = Array.from({ length: 22 }, mkParticle);

  function draw() {
    ctx.clearRect(0, 0, W, H);
    ctx.font = "var(--size, 12px) 'Cinzel', serif";
    ctx.fillStyle = "#c9a84c";
    for (const p of particles) {
      ctx.globalAlpha = p.alpha * Math.sin(p.life * Math.PI);
      ctx.font = `${p.size}px 'Cinzel', serif`;
      ctx.fillText(p.r, p.x, p.y);
      p.x += p.vx;
      p.y += p.vy;
      p.life += 0.003;
      if (p.life >= 1 || p.y < -20) Object.assign(p, mkParticle(), { y: H + 20, life: 0 });
    }
    ctx.globalAlpha = 1;
    requestAnimationFrame(draw);
  }
  draw();
}

// ── Campaign card color variant from name hash ───────────
function campaignColorVariant(name) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  const variants = ["", "arcane", "crimson", "nature", "shadow"];
  return variants[h % variants.length];
}

// ── 3D Card Tilt (mouse tracking) ────────────────────────
function setupCardTilt() {
  document.querySelectorAll(".campaign-card").forEach(card => {
    card.addEventListener("mousemove", e => {
      const rect = card.getBoundingClientRect();
      const x = (e.clientX - rect.left - rect.width  / 2) / (rect.width  / 2);
      const y = (e.clientY - rect.top  - rect.height / 2) / (rect.height / 2);
      const rx = y * -5.5;
      const ry = x * 5.5;
      card.style.transform = `translateY(-6px) scale(1.012) perspective(900px) rotateX(${rx}deg) rotateY(${ry}deg)`;
    });
    card.addEventListener("mouseleave", () => {
      card.style.transform = "";
      card.style.transition = "transform 0.4s cubic-bezier(0.22,0.61,0.36,1), box-shadow 0.25s, border-color 0.25s, background 0.25s";
    });
    card.addEventListener("mouseenter", () => {
      card.style.transition = "none";
    });
  });
}

// ── Scroll Reveal (IntersectionObserver) ─────────────────
function setupScrollReveal() {
  const items = document.querySelectorAll(".dd-reveal:not(.revealed)");
  if (!items.length) return;
  items.forEach((el, i) => el.style.setProperty("--i", i));
  const obs = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add("revealed");
        obs.unobserve(entry.target);
      }
    });
  }, { threshold: 0.05, rootMargin: "0px 0px -15px 0px" });
  items.forEach(el => obs.observe(el));
}

// ── Animated stat counter ─────────────────────────────────
function animateStatCounters() {
  document.querySelectorAll(".dd-stat-chip-val").forEach(el => {
    const target = parseInt(el.textContent, 10);
    if (isNaN(target) || target === 0) return;
    el.classList.add("counting");
    const dur = Math.min(800, target * 40 + 200);
    const start = performance.now();
    const tick = now => {
      const pct = Math.min(1, (now - start) / dur);
      const ease = 1 - Math.pow(1 - pct, 3);
      el.textContent = Math.round(target * ease);
      if (pct < 1) requestAnimationFrame(tick);
      else { el.textContent = target; el.classList.remove("counting"); }
    };
    requestAnimationFrame(tick);
  });
}

// ── Dice result flash ─────────────────────────────────────
function flashDiceResult() {
  const el = document.getElementById("dice-result-display");
  if (!el) return;
  el.classList.remove("rolled");
  void el.offsetWidth;
  el.classList.add("rolled");
  setTimeout(() => el.classList.remove("rolled"), 600);
}

// ── Mark latest narration block with glow class ──────────
function _markLatestNarBlock(feed) {
  if (!feed) return;
  feed.querySelectorAll(".narration-block.nar-latest").forEach(el => {
    el.classList.remove("nar-latest");
  });
  const blocks = feed.querySelectorAll(".narration-block:not(.narration-thinking)");
  if (blocks.length > 0) {
    const last = blocks[blocks.length - 1];
    last.classList.add("nar-latest");
  }
}

// ── Helpers ──────────────────────────────────────────────
function _timeAgo(isoString) {
  try {
    const secs = Math.floor((Date.now() - new Date(isoString)) / 1000);
    if (secs < 60) return "just now";
    if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
    if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
    if (secs < 604800) return `${Math.floor(secs / 86400)}d ago`;
    return new Date(isoString).toLocaleDateString();
  } catch { return ""; }
}

function modifier(score) {
  const m = Math.floor((score - 10) / 2);
  return m >= 0 ? `+${m}` : `${m}`;
}

/** Return null if summary is a known broken/boilerplate fallback, else return it trimmed. */
function _cleanSummary(text) {
  if (!text || typeof text !== "string") return null;
  const t = text.trim();
  if (!t) return null;
  // Detect old static-fallback text that contains the literal action_text artifact
  const boilerplateMarkers = [
    "time seems to slow as intent becomes deed",
    "the echoes of your action ripple outward",
    "unseen gears in motion",
    "dust motes drift in the torchlight",
    "the ancient stones of this place have borne witness",
    "your action cuts through the tension like a blade",
    "the weight of the moment presses down as you act",
    "fortune is a fickle ally, and she watches",
  ];
  const lower = t.toLowerCase();
  if (boilerplateMarkers.some(m => lower.includes(m))) return null;
  return t;
}

function hpFillClass(current, max) {
  const pct = max > 0 ? current / max : 0;
  if (pct <= 0.25) return "hp-low";
  if (pct <= 0.5)  return "hp-mid";
  return "";
}

function hpPct(current, max) {
  return max > 0 ? Math.max(0, Math.min(100, (current / max) * 100)) : 0;
}

function confirmInPlace(btn, onConfirm) {
  if (btn.dataset.confirming) return;
  btn.dataset.confirming = "1";
  const original = btn.innerHTML;
  const originalClass = btn.className;
  btn.innerHTML = `<span style="font-size:0.72rem;">Sure? </span>
    <span class="confirm-yes ms-1" style="cursor:pointer;color:var(--dd-gold);">Yes</span>
    <span class="confirm-no ms-2" style="cursor:pointer;opacity:0.6;">No</span>`;
  const restore = () => { btn.innerHTML = original; btn.className = originalClass; delete btn.dataset.confirming; };
  btn.querySelector(".confirm-yes").addEventListener("click", e => { e.stopPropagation(); restore(); onConfirm(); });
  btn.querySelector(".confirm-no").addEventListener("click",  e => { e.stopPropagation(); restore(); });
}

function renderHpBar(current, max) {
  const pct = hpPct(current, max);
  const cls = hpFillClass(current, max);
  return `
    <div class="d-flex justify-content-between mb-1">
      <span class="dd-muted" style="font-size:0.72rem;">HP</span>
      <span class="hp-value" style="font-size:0.72rem;">${current} / ${max}</span>
    </div>
    <div class="hp-bar-track">
      <div class="hp-bar-fill ${cls}" style="width:${pct}%"></div>
    </div>`;
}

// ── Sidebar HP Refresh ───────────────────────────────────
async function refreshSidebarHP(campaignId) {
  try {
    const updated = await listCharacters(campaignId);
    updated.forEach(c => {
      const card = document.getElementById(`sidebar-char-${c.id}`);
      if (!card) return;
      const fill = card.querySelector(".hp-bar-fill");
      const text = card.querySelector(".hp-value");
      const condEl = document.getElementById(`sidebar-cond-${c.id}`);
      if (fill) {
        const pct = hpPct(c.hp_current, c.hp_max);
        const cls = hpFillClass(c.hp_current, c.hp_max);
        fill.style.width = `${pct}%`;
        fill.className = `hp-bar-fill ${cls} hp-damaged`;
        setTimeout(() => fill.classList.remove("hp-damaged"), 600);
      }
      if (text) text.textContent = `${c.hp_current} / ${c.hp_max}`;
      if (condEl) condEl.innerHTML = conditionBadge(c.hp_current, c.hp_max);
    });
    const sel = document.getElementById("action-character");
    if (sel) {
      updated.forEach(c => {
        const opt = sel.querySelector(`option[value="${c.id}"]`);
        if (opt) {
          opt.textContent = `${c.character_name}${c.hp_current <= 0 ? " (KO)" : ""}`;
          opt.disabled = c.hp_current <= 0;
        }
      });
    }
  } catch (_) { /* silent — sidebar is decorative during network error */ }
}

// ── Backend Status ───────────────────────────────────────
async function pollBackendStatus() {
  const dot = document.getElementById("backend-status");
  if (!dot) return;
  try {
    const d = await healthCheck();
    if (d.status === "ok") {
      // Colour-only indicator: green when the AI is ready, amber when it's offline.
      // The hover tooltip carries the detail so the navbar stays uncluttered.
      dot.className = `dd-status-dot ${d.ollama === "ok" ? "ok" : "warn"}`;
      dot.title = d.ollama === "ok" ? "Backend OK · AI ready" : "Backend OK · AI offline";
    } else throw new Error();
  } catch {
    dot.className = "dd-status-dot err";
    dot.title = "Backend offline";
  }
}

// ── Router ───────────────────────────────────────────────
function route() {
  const hash = location.hash || "#/";
  const root = document.getElementById("app-root");

  const sessionMatch = hash.match(/^#\/session\/(.+)$/);
  const campaignMatch = hash.match(/^#\/campaign\/(.+)$/);

  if (sessionMatch) {
    root.innerHTML = `
      <div class="dd-skeleton mb-3" style="height:2.2rem;width:55%;"></div>
      <div class="d-flex gap-3" style="height:520px;">
        <div class="dd-skeleton-card flex-shrink-0" style="width:220px;"></div>
        <div class="dd-skeleton-card flex-grow-1"></div>
        <div class="dd-skeleton-card flex-shrink-0" style="width:240px;"></div>
      </div>`;
    renderSessionView(sessionMatch[1], root);
  } else if (campaignMatch) {
    root.innerHTML = `
      <div class="dd-skeleton mb-3" style="height:1.4rem;width:180px;border-radius:20px;"></div>
      <div class="dd-skeleton-card mb-3" style="height:120px;"></div>
      <div class="row g-4">
        <div class="col-lg-4"><div class="dd-skeleton-card" style="height:200px;"></div></div>
        <div class="col-lg-8">
          <div class="dd-skeleton mb-3" style="height:1.5rem;width:160px;"></div>
          ${[1,2].map(() => `<div class="dd-skeleton-card mb-2" style="height:100px;"></div>`).join("")}
        </div>
      </div>`;
    renderCampaignDetail(campaignMatch[1], root);
  } else {
    root.innerHTML = `
      <div class="d-flex align-items-center justify-content-between mb-4">
        <div class="dd-skeleton" style="height:1.6rem;width:130px;"></div>
        <div class="dd-skeleton" style="height:2.1rem;width:140px;border-radius:var(--dd-radius-lg);"></div>
      </div>
      <div class="row g-3">
        ${[1,2,3].map(() => `<div class="col-md-4 col-sm-6"><div class="dd-skeleton-card" style="height:165px;"></div></div>`).join("")}
      </div>`;
    renderCampaignList(root);
  }
}

window.addEventListener("hashchange", route);
window.addEventListener("DOMContentLoaded", async () => {
  createAtmosphericEffects();
  await pollBackendStatus();
  setInterval(pollBackendStatus, 15000);
  route();
});

// ── Campaign-detail character sheet (global, called from inline onclick) ─────
function openCampaignCharSheet(charId) {
  const c = (State.characters || []).find(ch => ch.id === charId);
  if (!c) return;

  const pb = profBonus(c.level);
  const hpPct = c.hp_max > 0 ? Math.max(0, Math.min(100, (c.hp_current / c.hp_max) * 100)) : 100;
  const hpFillCls = hpFillClass(c.hp_current, c.hp_max);

  const avatarEl = document.getElementById("cs-avatar");
  if (avatarEl) avatarEl.innerHTML = classAvatarHtml(c.class_name, c.character_name);

  document.getElementById("cs-name").textContent = c.character_name;
  document.getElementById("cs-subtitle").textContent =
    [c.race, c.class_name, c.player_name ? `(${c.player_name})` : ""].filter(Boolean).join(" · ");
  document.getElementById("cs-level-badge").textContent = `Level ${c.level}`;

  const xpThresholds = [0,300,900,2700,6500,14000,23000,34000,48000,64000,85000,100000,120000,140000,165000,195000,225000,265000,305000,355000];
  const xpNext = xpThresholds[c.level] ?? "Max";
  const xpCurrent = c.experience ?? 0;
  const xpPct = xpNext === "Max" ? 100 : Math.min(100, Math.round((xpCurrent / xpNext) * 100));
  document.getElementById("cs-xp").textContent =
    xpNext === "Max" ? `${xpCurrent} XP` : `${xpCurrent} / ${xpNext} XP`;

  document.getElementById("cs-hp").textContent = `${c.hp_current} / ${c.hp_max}`;
  document.getElementById("cs-ac").textContent = c.armor_class;
  document.getElementById("cs-init").textContent = modifier(c.dexterity);
  document.getElementById("cs-speed").textContent = `${c.speed}ft`;
  document.getElementById("cs-pb").textContent = `+${pb}`;

  const hpBar = document.getElementById("cs-hp-bar");
  const xpFill = document.getElementById("cs-xp-fill");
  if (hpBar) { hpBar.style.width = "0%"; hpBar.className = `hp-bar-fill ${hpFillCls}`; }
  if (xpFill) xpFill.style.width = "0%";
  setTimeout(() => {
    if (hpBar) hpBar.style.width = `${hpPct}%`;
    if (xpFill) xpFill.style.width = `${xpPct}%`;
  }, 180);

  const abilities = [
    { key:"STR", score:c.strength }, { key:"DEX", score:c.dexterity },
    { key:"CON", score:c.constitution }, { key:"INT", score:c.intelligence },
    { key:"WIS", score:c.wisdom },  { key:"CHA", score:c.charisma },
  ];
  const abilityGrid = document.getElementById("cs-ability-grid");
  if (abilityGrid) {
    abilityGrid.innerHTML = abilities.map(a => {
      const mod = Math.floor((a.score - 10) / 2);
      const attr = mod >= 3 ? 'data-high="true"' : mod <= -2 ? 'data-low="true"' : 'data-neutral="true"';
      return `<div class="cs-ability-box" ${attr}>
        <div class="cs-ability-mod">${modifier(a.score)}</div>
        <div class="cs-ability-score">${a.score}</div>
        <div class="cs-ability-name">${a.key}</div>
      </div>`;
    }).join("");
    abilityGrid.querySelectorAll(".cs-ability-box").forEach((box, i) => {
      box.style.animationDelay = `${0.08 + i * 0.05}s`;
      box.classList.add("popin");
      box.addEventListener("animationend", () => { box.classList.remove("popin"); box.style.animationDelay = ""; }, { once: true });
    });
  }

  const abScores = { STR:c.strength, DEX:c.dexterity, CON:c.constitution,
                     INT:c.intelligence, WIS:c.wisdom, CHA:c.charisma };
  const saveList = document.getElementById("cs-saves");
  if (saveList) {
    saveList.innerHTML = abilities.map(a => {
      const bonus = Math.floor((a.score - 10) / 2) + pb;
      const sign = bonus > 0 ? "positive" : bonus < 0 ? "negative" : "zero";
      return `<div class="cs-list-row">
        <span class="cs-row-ability">${a.key}</span>
        <span class="cs-row-name">${{ STR:"Strength",DEX:"Dexterity",CON:"Constitution",
          INT:"Intelligence",WIS:"Wisdom",CHA:"Charisma" }[a.key]} Save</span>
        <span class="cs-row-val" data-${sign}="true">${bonus >= 0 ? "+" : ""}${bonus}</span>
      </div>`;
    }).join("");
  }

  const skills5e = [
    { name:"Acrobatics", ab:"DEX" },{ name:"Animal Handling", ab:"WIS" },
    { name:"Arcana", ab:"INT" },    { name:"Athletics", ab:"STR" },
    { name:"Deception", ab:"CHA" }, { name:"History", ab:"INT" },
    { name:"Insight", ab:"WIS" },   { name:"Intimidation", ab:"CHA" },
    { name:"Investigation", ab:"INT" },{ name:"Medicine", ab:"WIS" },
    { name:"Nature", ab:"INT" },    { name:"Perception", ab:"WIS" },
    { name:"Performance", ab:"CHA" },{ name:"Persuasion", ab:"CHA" },
    { name:"Religion", ab:"INT" },  { name:"Sleight of Hand", ab:"DEX" },
    { name:"Stealth", ab:"DEX" },   { name:"Survival", ab:"WIS" },
  ];
  const skillList = document.getElementById("cs-skills");
  if (skillList) {
    skillList.innerHTML = skills5e.map(sk => {
      const base = Math.floor((abScores[sk.ab] - 10) / 2);
      const sign = base > 0 ? "positive" : base < 0 ? "negative" : "zero";
      return `<div class="cs-list-row">
        <span class="cs-row-ability">${sk.ab}</span>
        <span class="cs-row-name">${sk.name}</span>
        <span class="cs-row-val" data-${sign}="true">${base >= 0 ? "+" : ""}${base}</span>
      </div>`;
    }).join("");
  }

  const bsEl = document.getElementById("cs-backstory");
  if (bsEl) bsEl.textContent = c.backstory || "No backstory recorded.";

  const editBtn = document.getElementById("btn-cs-edit");
  if (editBtn) {
    const newBtn = editBtn.cloneNode(true);
    editBtn.parentNode.replaceChild(newBtn, editBtn);
    newBtn.addEventListener("click", () => {
      bootstrap.Modal.getInstance(document.getElementById("modal-char-sheet"))?.hide();
      setTimeout(() => {
        document.getElementById("ech-pname").value     = c.player_name || "";
        document.getElementById("ech-cname").value     = c.character_name;
        document.getElementById("ech-race").value      = c.race || "";
        document.getElementById("ech-class").value     = c.class_name || "";
        document.getElementById("ech-level").value     = c.level;
        document.getElementById("ech-str").value       = c.strength;
        document.getElementById("ech-dex").value       = c.dexterity;
        document.getElementById("ech-con").value       = c.constitution;
        document.getElementById("ech-int").value       = c.intelligence;
        document.getElementById("ech-wis").value       = c.wisdom;
        document.getElementById("ech-cha").value       = c.charisma;
        document.getElementById("ech-ac").value        = c.armor_class;
        document.getElementById("ech-init").value      = c.initiative;
        document.getElementById("ech-speed").value     = c.speed;
        document.getElementById("ech-hp").value        = c.hp_max;
        document.getElementById("ech-backstory").value = c.backstory || "";
        document.getElementById("form-edit-character").classList.remove("was-validated");
        document.getElementById("modal-edit-character-label").innerHTML =
          `<i class="bi bi-person-gear me-2 dd-gold"></i>Edit — ${esc(c.character_name)}`;
        document.getElementById("btn-save-character").dataset.charId = c.id;
        bootstrap.Modal.getOrCreateInstance(document.getElementById("modal-edit-character")).show();
      }, 250);
    });
  }

  bootstrap.Modal.getOrCreateInstance(document.getElementById("modal-char-sheet")).show();
}

// ── Global keyboard shortcuts ─────────────────────────
window.addEventListener("keydown", e => {
  const tag = document.activeElement?.tagName?.toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select") return;
  if (e.key === "?" || (e.key === "/" && !e.ctrlKey && !e.metaKey)) {
    e.preventDefault();
    showKeyboardHelp();
  }
  if (e.key === "s" && !e.ctrlKey && !e.metaKey && !e.altKey) {
    const searchEl = document.getElementById("campaign-search");
    if (searchEl) { e.preventDefault(); searchEl.focus(); searchEl.select(); }
  }
});

function showKeyboardHelp() {
  if (document.getElementById("kb-help-overlay")) return;
  const overlay = document.createElement("div");
  overlay.id = "kb-help-overlay";
  overlay.className = "kb-help-overlay";
  overlay.innerHTML = `
    <div class="kb-help-panel">
      <div class="kb-help-header">
        <span><i class="bi bi-keyboard me-2"></i>Keyboard Shortcuts</span>
        <button class="kb-help-close" id="kb-help-close" aria-label="Close"><i class="bi bi-x-lg"></i></button>
      </div>
      <div class="kb-help-body">
        <div class="kb-help-section">
          <div class="kb-help-section-title">Action Composer</div>
          <div class="kb-help-row"><kbd>Enter</kbd><span>Submit action to DM</span></div>
          <div class="kb-help-row"><kbd>Shift</kbd><kbd>Enter</kbd><span>New line in description</span></div>
          <div class="kb-help-row"><kbd>Esc</kbd><span>Clear &amp; dismiss input</span></div>
          <div class="kb-help-row"><kbd>1</kbd>–<kbd>6</kbd><span>Select action type (RP/Melee/Ranged/Spell/Skill/Move)</span></div>
        </div>
        <div class="kb-help-section">
          <div class="kb-help-section-title">Navigation</div>
          <div class="kb-help-row"><kbd>?</kbd> <span>or</span> <kbd>/</kbd><span>Show this help</span></div>
          <div class="kb-help-row"><kbd>S</kbd><span>Focus campaign search</span></div>
        </div>
      </div>
      <div class="kb-help-footer">Press <kbd>Esc</kbd> or click anywhere to close</div>
    </div>`;
  document.body.append(overlay);
  requestAnimationFrame(() => overlay.classList.add("visible"));

  const close = () => {
    overlay.classList.remove("visible");
    setTimeout(() => overlay.remove(), 250);
  };
  overlay.addEventListener("click", e => { if (e.target === overlay) close(); });
  document.getElementById("kb-help-close").addEventListener("click", close);
  const onKey = e => { if (e.key === "Escape") { close(); window.removeEventListener("keydown", onKey); } };
  window.addEventListener("keydown", onKey);
  setTimeout(close, 12000);
}

// ════════════════════════════════════════════════════════
// VIEW: Campaign List
// ════════════════════════════════════════════════════════
async function renderCampaignList(root) {
  let campaigns = [], stats = null;
  try {
    [campaigns, stats] = await Promise.all([listCampaigns(), getStats().catch(() => null)]);
  } catch (e) {
    root.innerHTML = `<div class="empty-state"><div class="empty-icon"><i class="bi bi-exclamation-triangle"></i></div><p>${e.message}</p></div>`;
    return;
  }

  const cards = campaigns.length === 0
    ? `<div class="col-12"><div class="empty-state-enhanced">
        <div class="empty-icon-large"><i class="bi bi-book"></i></div>
        <h5>Your Legend Has Not Yet Been Written</h5>
        <p>No adventures exist in this realm. Every great story begins with a single step — create your first campaign and let the Dungeon Master bring your world to life.</p>
        <div class="d-flex gap-2 justify-content-center flex-wrap mt-3">
          <button class="btn dd-btn-primary" data-bs-toggle="modal" data-bs-target="#modal-new-campaign">
            <i class="bi bi-plus-circle me-2"></i>Begin the First Adventure
          </button>
          <button class="btn btn-outline-secondary" id="btn-quick-start-demo" title="Load a pre-built starter campaign">
            <i class="bi bi-lightning-charge me-2"></i>Quick Start — The Sunken Vault
          </button>
        </div>
       </div></div>`
    : campaigns.map(c => {
        const variant = campaignColorVariant(c.name);
        const variantClass = variant ? `campaign-card--${variant}` : "";
        const sessionPct = Math.min(100, (c.session_count ?? 0) * 10);
        const icons = { arcane:"bi-stars", crimson:"bi-shield-fill", nature:"bi-tree-fill", shadow:"bi-moon-stars-fill", "":"bi-map-fill" };
        const cardIcon = icons[variant] || "bi-map-fill";
        return `
        <div class="col-md-4 col-sm-6 dd-reveal">
          <div class="campaign-card ${variantClass}" style="position:relative;" onclick="location.hash='#/campaign/${c.id}'" data-cname="${esc(c.name)}">
            <div class="d-flex align-items-start justify-content-between mb-1">
              <i class="bi ${cardIcon} campaign-card-accent" style="font-size:1.1rem;opacity:0.55;"></i>
              <button class="btn btn-link p-0 btn-delete-campaign"
                data-campaign-id="${c.id}" data-campaign-name="${esc(c.name)}"
                title="Delete campaign"
                style="font-size:0.8rem;color:var(--dd-red);opacity:0.45;text-decoration:none;line-height:1;"
                onclick="event.stopPropagation()">
                <i class="bi bi-trash3"></i>
              </button>
            </div>
            <div class="campaign-name mb-1">${esc(c.name)}</div>
            <div class="campaign-meta mb-1" style="font-size:0.78rem;">
              <i class="bi bi-geo-alt me-1" style="opacity:0.5;"></i>${esc(c.world_setting || "Unknown Realm")}
            </div>
            <div class="campaign-meta mb-3" style="display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;min-height:2.4em;">
              ${c.description ? esc(c.description) : '<em class="meta-placeholder">No description</em>'}
            </div>
            <div class="campaign-progress-track mb-3"><div class="campaign-progress-bar" style="width:${sessionPct}%"></div></div>
            <div class="d-flex align-items-center justify-content-between flex-wrap gap-1">
              <span class="dd-badge-${c.status === 'active' ? 'active' : 'inactive'}">${esc(c.status)}</span>
              <span class="campaign-counts d-flex align-items-center gap-2">
                <span class="cnt-char" title="${c.character_count ?? 0} characters"><i class="bi bi-people me-1"></i>${c.character_count ?? 0}</span>
                <span style="opacity:0.25;">·</span>
                <span class="cnt-sess" title="${c.session_count ?? 0} sessions"><i class="bi bi-journal-text me-1"></i>${c.session_count ?? 0}</span>
              </span>
            </div>
            ${c.updated_at ? `<div class="campaign-last-session">
              <i class="bi bi-clock"></i>
              ${_timeAgo(c.updated_at)}
            </div>` : ""}
          </div>
        </div>`;
      }).join("");

  const statsHtml = stats ? `
    <div class="dd-stats-strip">
      ${[
        ["bi-map-fill",      stats.campaigns,  "campaign",  "var(--dd-gold)"],
        ["bi-people-fill",   stats.characters, "character", "var(--dd-green)"],
        ["bi-journal-text",  stats.sessions,   "session",   "var(--dd-blue)"],
        ["bi-dice-5-fill",   stats.turns,      "turn",      "var(--dd-red)"],
      ].map(([icon, val, label, color]) => `
        <div class="dd-stat-chip">
          <i class="bi ${icon} dd-stat-chip-icon" style="color:${color};"></i>
          <span class="dd-stat-chip-val" style="color:${color};">${val}</span>
          <span class="dd-stat-chip-label">${label}${val !== 1 ? "s" : ""}</span>
        </div>`).join("")}
    </div>` : "";

  root.innerHTML = `
    <div class="dd-hero-banner">
      ${HERO_SVG}
      <div class="dd-hero-overlay">
        <div class="dd-hero-title">D&amp;D Multi-AI Agent Storytelling System</div>
        <div class="dd-hero-subtitle">Where every roll shapes a legend</div>
      </div>
    </div>
    <div class="d-flex align-items-center justify-content-between flex-wrap gap-2 mb-3">
      <h4 class="mb-0 campaigns-page-heading" style="font-family:var(--dd-font-heading);color:var(--dd-gold);letter-spacing:0.08em;">
        <i class="bi bi-map me-2 dd-gold" style="opacity:0.7;"></i>Campaigns
      </h4>
      <div class="dd-toolbar">
        <div class="d-flex align-items-center gap-2">
          <div class="input-group input-group-sm" style="width:195px;">
            <span class="input-group-text" style="background:rgba(255,255,255,0.04);border-color:rgba(212,170,80,0.18);">
              <i class="bi bi-search" style="color:var(--dd-text-muted);font-size:0.8rem;"></i>
            </span>
            <input type="text" id="campaign-search" class="form-control dd-input"
              placeholder="Search… (S)" style="border-left:none;" aria-label="Search campaigns">
          </div>
          <span id="search-result-count" class="search-result-count" style="display:none;"></span>
        </div>
        <button class="btn btn-sm" id="btn-import-campaign"
          style="border:1px solid rgba(212,175,55,0.28);color:var(--dd-gold-muted);
                 background:rgba(212,175,55,0.06);border-radius:6px;white-space:nowrap;"
          title="Import campaign from JSON">
          <i class="bi bi-upload me-1"></i>Import
        </button>
        <button class="btn dd-btn-primary" data-bs-toggle="modal" data-bs-target="#modal-new-campaign"
          style="white-space:nowrap;">
          <i class="bi bi-plus-lg me-1"></i>New Campaign
        </button>
      </div>
    </div>
    ${statsHtml}
    <div class="row g-3" id="campaign-cards-row">${cards}</div>
    ${campaigns.length > 0 && campaigns.length < 6 ? `
    <div class="campaigns-footer-nudge">
      <span class="nudge-rune">⚔ ✦ ⚔</span>
      <p>Every legend begins with a single campaign. Where will yours lead?</p>
    </div>` : ""}`;

  animateViewIn(root);
  requestAnimationFrame(() => { setupScrollReveal(); setupCardTilt(); animateStatCounters(); });

  document.getElementById("btn-create-campaign").onclick = async () => {
    const form = document.getElementById("form-new-campaign");
    form.classList.remove("was-validated");
    if (!form.checkValidity()) { form.classList.add("was-validated"); return; }
    const name    = document.getElementById("nc-name").value.trim();
    const setting = document.getElementById("nc-setting").value.trim();
    const desc    = document.getElementById("nc-desc").value.trim();
    try {
      await createCampaign({ name, description: desc, world_setting: setting });
      bootstrap.Modal.getInstance(document.getElementById("modal-new-campaign")).hide();
      form.reset();
      showToast("Campaign created!", "success");
      renderCampaignList(root);
    } catch (e) { showToast(e.message, "danger"); }
  };

  const searchEl = document.getElementById("campaign-search");
  if (searchEl) {
    const _doSearch = () => {
      const raw = searchEl.value.trim();
      const q   = raw.toLowerCase();
      const cols = document.querySelectorAll("#campaign-cards-row .col-md-4");
      const countEl = document.getElementById("search-result-count");
      const re = raw ? new RegExp(`(${raw.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi") : null;
      let vis = 0;
      cols.forEach(col => {
        const match = !q || col.textContent.toLowerCase().includes(q);
        col.style.display = match ? "" : "none";
        if (match) vis++;
        const card   = col.querySelector(".campaign-card[data-cname]");
        const nameEl = col.querySelector(".campaign-name");
        if (card && nameEl) {
          const raw2 = card.dataset.cname;           // decoded plain text
          if (re && match && raw2.toLowerCase().includes(q)) {
            // Split on match groups to safely wrap with <mark>
            const parts = raw2.split(re);
            nameEl.innerHTML = parts.map((p, i) => {
              const safe = p.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
              return i % 2 === 1 ? `<mark class="search-hl">${safe}</mark>` : safe;
            }).join("");
          } else {
            nameEl.innerHTML = esc(raw2);
          }
        }
      });
      if (countEl) {
        countEl.textContent = q ? `${vis} result${vis !== 1 ? "s" : ""}` : "";
        countEl.style.display = q ? "" : "none";
      }
      searchEl.classList.toggle("search-has-value", !!q);

      let emptyEl = document.getElementById("search-empty-state");
      if (q && vis === 0) {
        if (!emptyEl) {
          emptyEl = document.createElement("div");
          emptyEl.id = "search-empty-state";
          emptyEl.className = "col-12 search-empty-state";
          emptyEl.innerHTML = `
            <div class="search-empty-inner">
              <i class="bi bi-search search-empty-icon"></i>
              <div class="search-empty-title">No campaigns found</div>
              <div class="search-empty-sub">No campaigns match <em>&ldquo;${esc(raw)}&rdquo;</em></div>
              <button class="btn btn-sm mt-3 search-empty-clear" onclick="document.getElementById('campaign-search').value='';document.getElementById('campaign-search').dispatchEvent(new Event('input'))">
                <i class="bi bi-x-circle me-1"></i>Clear search
              </button>
            </div>`;
          document.getElementById("campaign-cards-row")?.appendChild(emptyEl);
        } else {
          emptyEl.querySelector(".search-empty-sub").innerHTML =
            `No campaigns match <em>&ldquo;${esc(raw)}&rdquo;</em>`;
          emptyEl.style.display = "";
        }
      } else if (emptyEl) {
        emptyEl.style.display = "none";
      }
    };
    searchEl.addEventListener("input", _doSearch);
    searchEl.focus();
  }

  document.getElementById("btn-import-campaign")?.addEventListener("click", () => {
    const fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.accept = ".json,application/json";
    fileInput.onchange = async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;
      try {
        const text = await file.text();
        const bundle = JSON.parse(text);
        if (!bundle.campaign?.name) throw new Error("Invalid campaign bundle — missing campaign.name.");
        const imported = await importCampaign(bundle);
        showToast(`"${imported.name}" imported (${bundle.characters?.length ?? 0} characters)!`, "success");
        window.location.hash = `#/campaign/${imported.id}`;
      } catch (err) { showToast(err.message, "danger"); }
    };
    fileInput.click();
  });

  document.getElementById("btn-quick-start-demo")?.addEventListener("click", async () => {
    const btn = document.getElementById("btn-quick-start-demo");
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Creating…'; }
    try {
      const result = await createDemoCampaign();
      showToast(`"${result.name}" created! Two characters are ready.`, "success");
      window.location.hash = `#/campaign/${result.campaign_id}`;
    } catch (err) {
      showToast(err.message || "Failed to create demo campaign.", "danger");
      if (btn) { btn.disabled = false; btn.innerHTML = '<i class="bi bi-lightning-charge me-2"></i>Quick Start — The Sunken Vault'; }
    }
  });

  document.querySelectorAll(".btn-delete-campaign").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      e.preventDefault();
      const cId   = btn.dataset.campaignId;
      const cName = btn.dataset.campaignName;
      confirmInPlace(btn, async () => {
        try {
          await deleteCampaign(cId);
          showToast(`"${cName}" deleted.`, "success");
          renderCampaignList(root);
        } catch (err) { showToast(err.message, "danger"); }
      });
    });
  });
}

// ════════════════════════════════════════════════════════
// VIEW: Campaign Detail
// ════════════════════════════════════════════════════════
async function renderCampaignDetail(id, root) {
  let campaign, characters, sessions = [];
  try {
    [campaign, characters, sessions] = await Promise.all([
      getCampaign(id),
      listCharacters(id),
      listCampaignSessions(id).catch(() => []),
    ]);
  } catch (e) {
    root.innerHTML = `<div class="empty-state"><p>${e.message}</p><a href="#/" class="btn dd-btn-primary mt-3">Back</a></div>`;
    return;
  }

  State.activeCampaignId = id;
  State.characters = characters;

  const charCards = characters.length === 0
    ? `<div class="empty-state" style="padding:2rem;">
        <div class="empty-icon"><i class="bi bi-person"></i></div>
        <p>No characters yet.</p>
       </div>`
    : characters.map(c => `
        <div class="character-card mb-3 dd-reveal">
          <div class="d-flex align-items-start justify-content-between mb-2">
            <div class="d-flex align-items-start gap-2 cd-char-sheet-trigger" style="cursor:pointer;"
              data-char-id="${c.id}"
              onclick="openCampaignCharSheet('${c.id}')" title="View character sheet">
              ${classAvatarHtml(c.class_name, c.character_name)}
              <div>
                <div class="char-name" style="cursor:pointer;">${esc(c.character_name)}</div>
                <div class="char-meta">${[c.race, c.class_name, `Level ${c.level}`].filter(Boolean).map(esc).join(" · ")} ${c.player_name ? `<span class="ms-1">— ${esc(c.player_name)}</span>` : ""}</div>
              </div>
            </div>
            <div class="text-end d-flex flex-column align-items-end gap-1">
              <div style="font-size:0.78rem;" class="dd-muted">AC ${c.armor_class} &nbsp; Spd ${c.speed}ft &nbsp; <span class="char-hp-pct ${hpFillClass(c.hp_current, c.hp_max)}">${Math.round(hpPct(c.hp_current, c.hp_max))}% HP</span></div>
              <div class="d-flex gap-2">
                <button class="btn btn-sm btn-link p-0 dd-gold btn-edit-char" data-char-id="${c.id}"
                  title="Edit character" style="font-size:0.78rem;text-decoration:none;">
                  <i class="bi bi-pencil-square me-1"></i><span style="font-size:0.72rem;">Edit</span>
                </button>
                <button class="btn btn-sm btn-link p-0 btn-delete-char"
                  data-char-id="${c.id}" data-char-name="${esc(c.character_name)}"
                  title="Delete character" style="font-size:0.78rem;text-decoration:none;color:var(--dd-red);opacity:0.7;">
                  <i class="bi bi-trash3"></i>
                </button>
              </div>
            </div>
          </div>
          ${renderHpBar(c.hp_current, c.hp_max)}
          <div class="row g-1 mt-2">
            ${["strength","dexterity","constitution","intelligence","wisdom","charisma"].map(ab => {
              const mod = Math.floor((c[ab] - 10) / 2);
              const attr = mod >= 3 ? 'data-high' : mod <= -2 ? 'data-low' : '';
              return `
              <div class="col-2">
                <div class="stat-box" ${attr}>
                  <span class="stat-val">${modifier(c[ab])}</span>
                  <span class="stat-lbl">${ab.slice(0,3).toUpperCase()}</span>
                </div>
              </div>`;
            }).join("")}
          </div>
          ${c.backstory ? `<p class="char-backstory mt-2">${esc(c.backstory)}</p>` : ""}
        </div>`).join("");

  const hVariant = campaignColorVariant(campaign.name) || "arcane";
  const _hIcons = { arcane:"bi-stars", crimson:"bi-shield-fill", nature:"bi-tree-fill", shadow:"bi-moon-stars-fill" };
  const heroIcon = _hIcons[hVariant] || "bi-shield-fill-check";

  root.innerHTML = `
    <div class="dd-back-nav">
      <a href="#/" class="btn btn-sm btn-outline-secondary"><i class="bi bi-arrow-left me-1"></i>Campaigns</a>
      <span class="breadcrumb-sep">›</span>
      <span class="breadcrumb-current">${esc(campaign.name)}</span>
    </div>

    <!-- Campaign Hero -->
    <div class="campaign-hero variant-${hVariant}">
      <div class="campaign-hero-icon"><i class="bi ${heroIcon}"></i></div>
      <h1 class="campaign-hero-title">${esc(campaign.name)}</h1>
      ${campaign.world_setting ? `<p class="campaign-hero-setting"><i class="bi bi-geo-alt me-1" style="opacity:0.5;font-size:0.85em;"></i>${esc(campaign.world_setting)}</p>` : ""}
      <div class="campaign-hero-badges">
        <span class="dd-badge-${campaign.status === 'active' ? 'active' : 'inactive'}">${esc(campaign.status)}</span>
        <span class="campaign-hero-stat">
          <i class="bi bi-people"></i>${characters.length} character${characters.length !== 1 ? "s" : ""}
        </span>
        <span class="campaign-hero-stat">
          <i class="bi bi-journal-text"></i>${sessions.length} session${sessions.length !== 1 ? "s" : ""}
        </span>
        <span class="campaign-hero-stat">
          <i class="bi bi-list-ol"></i>${sessions.reduce((a, s) => a + (s.turn_count || 0), 0)} turns
        </span>
        <button id="btn-export-campaign" class="campaign-hero-stat" style="border:none;background:rgba(212,175,55,0.08);cursor:pointer;transition:background 0.2s;"
          title="Export campaign as JSON">
          <i class="bi bi-download"></i>Export
        </button>
      </div>
    </div>

    <div class="row g-4">
      <div class="col-lg-4">
        <div class="dd-card p-0 mb-3 campaign-detail-info-card">
          <div class="dd-card-header d-flex align-items-center justify-content-between">
            <span><i class="bi bi-scroll me-2"></i>Campaign Details</span>
            <button class="btn btn-sm btn-link p-0 dd-gold" id="btn-edit-campaign" title="Edit campaign"
              style="font-size:0.85rem;text-decoration:none;">
              <i class="bi bi-pencil-square"></i>
            </button>
          </div>
          <div class="p-3">
            <p style="font-size:0.85rem;line-height:1.6;">${campaign.description ? esc(campaign.description) : "<span class='dd-muted'>No description.</span>"}</p>
          </div>
        </div>
        <button class="btn dd-btn-success w-100" data-bs-toggle="modal" data-bs-target="#modal-new-session">
          <i class="bi bi-play-fill me-1"></i>Start New Session
        </button>
      </div>
      <div class="col-lg-8">
        <div class="d-flex align-items-center justify-content-between mb-3">
          <span class="dd-section-heading"><i class="bi bi-people me-1"></i>Characters (${characters.length})</span>
          <button class="btn btn-sm dd-btn-primary" data-bs-toggle="modal" data-bs-target="#modal-new-character">
            <i class="bi bi-person-plus me-1"></i>Add Character
          </button>
        </div>
        <div class="cd-char-grid">${charCards}</div>

        <!-- Sessions History -->
        <div class="mt-4">
          <div class="d-flex align-items-center justify-content-between mb-3">
            <span class="dd-section-heading"><i class="bi bi-journal-text me-1"></i>Sessions (${sessions.length})</span>
          </div>
          ${sessions.length === 0
            ? `<div style="font-family:var(--dd-font-serif);font-style:italic;font-size:0.83rem;color:var(--dd-text-muted);padding:0.75rem 0;opacity:0.7;"><i class="bi bi-hourglass me-2" style="opacity:0.5;"></i>The first session awaits. Gather your party above!</div>`
            : `<div class="session-timeline">${sessions.map((s, idx) => {
                const isActive = s.status === "active";
                const turns = `${s.turn_count} turn${s.turn_count !== 1 ? "s" : ""}`;
                const dateStr = s.started_at
                  ? new Date(s.started_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })
                  : "";
                const link = isActive
                  ? `<a href="#/session/${s.id}" class="btn btn-xs dd-btn-primary" style="font-size:0.7rem;padding:0.15rem 0.6rem;"><i class="bi bi-play-fill me-1"></i>Resume</a>`
                  : `<a href="#/session/${s.id}" class="btn btn-xs btn-outline-secondary" style="font-size:0.7rem;padding:0.15rem 0.6rem;"><i class="bi bi-eye me-1"></i>View</a>`;
                return `
                  <div class="timeline-item ${isActive ? "tl-active" : ""} dd-reveal">
                    <div class="timeline-card" data-status="${esc(s.status)}">
                      <div class="d-flex align-items-center justify-content-between mb-1">
                        <div class="d-flex align-items-center gap-2 flex-wrap">
                          <strong style="color:var(--dd-text-bright);font-size:0.86rem;font-family:var(--dd-font-heading);letter-spacing:0.03em;">${esc(s.name || "Unnamed Session")}</strong>
                          <span class="dd-badge-${isActive ? "active" : "inactive"}">${esc(s.status)}</span>
                        </div>
                        <div class="d-flex align-items-center gap-1 tl-actions">
                          ${link}
                          ${!isActive ? `<button class="btn btn-xs btn-delete-session"
                            data-session-id="${s.id}" data-session-name="${esc(s.name || "Session")}"
                            title="Delete session"
                            style="font-size:0.7rem;color:var(--dd-red);opacity:0.55;border:none;background:none;padding:0.1rem 0.3rem;">
                            <i class="bi bi-trash3"></i>
                          </button>` : ""}
                        </div>
                      </div>
                      <div class="d-flex align-items-center gap-3 flex-wrap">
                        ${dateStr ? `<span class="timeline-date"><i class="bi bi-calendar3 me-1"></i>${esc(dateStr)}</span>` : ""}
                        <span class="timeline-date"><i class="bi bi-list-ol me-1"></i>${esc(turns)}</span>
                        ${(s.ended_at || s.started_at) ? `<span class="tl-timeago"><i class="bi bi-clock me-1"></i>${_timeAgo(s.ended_at || s.started_at)}</span>` : ""}
                      </div>
                      ${_cleanSummary(s.summary) ? `<p class="session-summary-text mt-1 mb-0">${esc(_cleanSummary(s.summary))}</p>` : ""}
                    </div>
                  </div>`;
              }).join("")}</div>`}
        </div>
      </div>
    </div>`;

  animateViewIn(root);
  requestAnimationFrame(() => {
    setupScrollReveal();
    root.querySelectorAll(".character-card .hp-bar-fill").forEach(fill => {
      const target = fill.style.width;
      fill.style.width = "0%";
      requestAnimationFrame(() => requestAnimationFrame(() => { fill.style.width = target; }));
    });
    root.querySelectorAll(".character-card").forEach(card => {
      if (card.querySelector(".char-level-float")) return;
      const metaEl = card.querySelector(".char-meta");
      if (!metaEl) return;
      const lvlMatch = metaEl.textContent.match(/Level\s*(\d+)/i);
      if (!lvlMatch) return;
      const badge = document.createElement("div");
      badge.className = "char-level-float";
      badge.textContent = lvlMatch[1];
      badge.title = `Level ${lvlMatch[1]}`;
      card.append(badge);
    });
  });

  const updateHpPlaceholder = () => {
    const lvl = parseInt(document.getElementById("nch-level")?.value) || 1;
    const con = parseInt(document.getElementById("nch-con")?.value) || 10;
    const conMod = Math.floor((con - 10) / 2);
    const auto = Math.max(1, lvl * 8 + conMod * lvl);
    const hpEl = document.getElementById("nch-hp");
    if (hpEl) hpEl.placeholder = `auto (${auto})`;
  };
  ["nch-level", "nch-con"].forEach(id => {
    document.getElementById(id)?.addEventListener("input", updateHpPlaceholder);
  });
  updateHpPlaceholder();

  // ── Roll 4d6 drop lowest ────────────────────────────
  function _roll4d6DropLowest() {
    const rolls = Array.from({ length: 4 }, () => Math.ceil(Math.random() * 6));
    rolls.sort((a, b) => a - b);
    const dropped = rolls[0];
    const kept = rolls.slice(1);
    return { total: kept.reduce((s, v) => s + v, 0), rolls, dropped };
  }
  document.getElementById("btn-roll-stats")?.addEventListener("click", () => {
    const ids = ["nch-str","nch-dex","nch-con","nch-int","nch-wis","nch-cha"];
    const results = ids.map(() => _roll4d6DropLowest());
    ids.forEach((id, i) => {
      const el = document.getElementById(id);
      if (el) { el.value = results[i].total; el.classList.add("stat-rolled"); setTimeout(() => el.classList.remove("stat-rolled"), 600); }
    });
    const preview = document.getElementById("rolled-stats-preview");
    if (preview) {
      const labels = ["STR","DEX","CON","INT","WIS","CHA"];
      preview.innerHTML = results.map((r, i) =>
        `<span style="margin-right:0.8rem;"><strong style="color:var(--dd-gold);">${labels[i]}</strong>: ${r.total} <span style="opacity:0.5;">[${r.rolls.join(",")}→drop ${r.dropped}]</span></span>`
      ).join("");
      preview.style.display = "";
    }
    updateHpPlaceholder();
  });

  document.getElementById("btn-create-character").onclick = async () => {
    const form = document.getElementById("form-new-character");
    form.classList.remove("was-validated");
    if (!document.getElementById("nch-cname").value.trim()) {
      form.classList.add("was-validated"); return;
    }
    const hpRaw = parseInt(document.getElementById("nch-hp")?.value);
    const data = {
      player_name:    document.getElementById("nch-pname").value.trim() || null,
      character_name: document.getElementById("nch-cname").value.trim(),
      race:           document.getElementById("nch-race").value.trim() || null,
      class_name:     document.getElementById("nch-class").value.trim() || null,
      level:          parseInt(document.getElementById("nch-level").value) || 1,
      hp_max:         hpRaw > 0 ? hpRaw : null,
      strength:       parseInt(document.getElementById("nch-str").value) || 10,
      dexterity:      parseInt(document.getElementById("nch-dex").value) || 10,
      constitution:   parseInt(document.getElementById("nch-con").value) || 10,
      intelligence:   parseInt(document.getElementById("nch-int").value) || 10,
      wisdom:         parseInt(document.getElementById("nch-wis").value) || 10,
      charisma:       parseInt(document.getElementById("nch-cha").value) || 10,
      armor_class:    parseInt(document.getElementById("nch-ac").value) || 10,
      initiative:     parseInt(document.getElementById("nch-init").value) || 0,
      speed:          parseInt(document.getElementById("nch-speed").value) || 30,
      backstory:      document.getElementById("nch-backstory")?.value.trim() || "",
    };
    try {
      await createCharacter(id, data);
      bootstrap.Modal.getInstance(document.getElementById("modal-new-character")).hide();
      form.reset();
      showToast(`${data.character_name} added!`, "success");
      renderCampaignDetail(id, root);
    } catch (e) { showToast(e.message, "danger"); }
  };

  document.getElementById("btn-start-session").onclick = async () => {
    const nameInput = document.getElementById("ns-name");
    if (!nameInput.value.trim()) { nameInput.classList.add("is-invalid"); return; }
    nameInput.classList.remove("is-invalid");
    try {
      const session = await createSession(id, nameInput.value.trim());
      bootstrap.Modal.getInstance(document.getElementById("modal-new-session")).hide();
      nameInput.value = "";
      showToast("Session started!", "success");
      location.hash = `#/session/${session.id}`;
    } catch (e) { showToast(e.message, "danger"); }
  };

  document.getElementById("btn-export-campaign")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    try {
      const bundle = await exportCampaign(id);
      const slug = campaign.name.replace(/[^a-z0-9]+/gi, "-").toLowerCase();
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `${slug}-export.json`;
      a.click();
      URL.revokeObjectURL(url);
      showToast("Campaign exported!", "success");
    } catch (err) { showToast(err.message, "danger"); }
    finally { btn.disabled = false; }
  });

  document.getElementById("btn-edit-campaign").onclick = () => {
    document.getElementById("ec-name").value    = campaign.name;
    document.getElementById("ec-setting").value = campaign.world_setting || "";
    document.getElementById("ec-desc").value    = campaign.description || "";
    document.getElementById("ec-status").value  = campaign.status || "active";
    document.getElementById("form-edit-campaign").classList.remove("was-validated");
    new bootstrap.Modal(document.getElementById("modal-edit-campaign")).show();
  };
  document.getElementById("btn-save-campaign").onclick = async () => {
    const form = document.getElementById("form-edit-campaign");
    if (!document.getElementById("ec-name").value.trim()) {
      form.classList.add("was-validated"); return;
    }
    try {
      await updateCampaign(id, {
        name:          document.getElementById("ec-name").value.trim(),
        world_setting: document.getElementById("ec-setting").value.trim(),
        description:   document.getElementById("ec-desc").value.trim(),
        status:        document.getElementById("ec-status").value,
      });
      bootstrap.Modal.getInstance(document.getElementById("modal-edit-campaign")).hide();
      showToast("Campaign updated!", "success");
      renderCampaignDetail(id, root);
    } catch (e) { showToast(e.message, "danger"); }
  };

  document.querySelectorAll(".btn-edit-char").forEach(btn => {
    btn.onclick = () => {
      const charId = btn.dataset.charId;
      const c = characters.find(ch => ch.id === charId);
      if (!c) return;
      document.getElementById("ech-pname").value    = c.player_name || "";
      document.getElementById("ech-cname").value    = c.character_name;
      document.getElementById("ech-race").value     = c.race || "";
      document.getElementById("ech-class").value    = c.class_name || "";
      document.getElementById("ech-level").value    = c.level;
      document.getElementById("ech-str").value      = c.strength;
      document.getElementById("ech-dex").value      = c.dexterity;
      document.getElementById("ech-con").value      = c.constitution;
      document.getElementById("ech-int").value      = c.intelligence;
      document.getElementById("ech-wis").value      = c.wisdom;
      document.getElementById("ech-cha").value      = c.charisma;
      document.getElementById("ech-ac").value       = c.armor_class;
      document.getElementById("ech-init").value     = c.initiative;
      document.getElementById("ech-speed").value    = c.speed;
      document.getElementById("ech-hp").value       = c.hp_max;
      document.getElementById("ech-backstory").value = c.backstory || "";
      document.getElementById("form-edit-character").classList.remove("was-validated");
      document.getElementById("modal-edit-character-label").innerHTML =
        `<i class="bi bi-person-gear me-2 dd-gold"></i>Edit — ${esc(c.character_name)}`;
      document.getElementById("btn-save-character").dataset.charId = charId;
      new bootstrap.Modal(document.getElementById("modal-edit-character")).show();
    };
  });
  document.getElementById("btn-save-character").onclick = async () => {
    const charId = document.getElementById("btn-save-character").dataset.charId;
    if (!charId) return;
    if (!document.getElementById("ech-cname").value.trim()) {
      document.getElementById("form-edit-character").classList.add("was-validated"); return;
    }
    try {
      await updateCharacter(charId, {
        player_name:    document.getElementById("ech-pname").value.trim() || null,
        character_name: document.getElementById("ech-cname").value.trim(),
        race:           document.getElementById("ech-race").value.trim() || null,
        class_name:     document.getElementById("ech-class").value.trim() || null,
        level:          parseInt(document.getElementById("ech-level").value) || null,
        strength:       parseInt(document.getElementById("ech-str").value) || null,
        dexterity:      parseInt(document.getElementById("ech-dex").value) || null,
        constitution:   parseInt(document.getElementById("ech-con").value) || null,
        intelligence:   parseInt(document.getElementById("ech-int").value) || null,
        wisdom:         parseInt(document.getElementById("ech-wis").value) || null,
        charisma:       parseInt(document.getElementById("ech-cha").value) || null,
        armor_class:    parseInt(document.getElementById("ech-ac").value) || null,
        initiative:     parseInt(document.getElementById("ech-init").value) ?? null,
        speed:          parseInt(document.getElementById("ech-speed").value) || null,
        hp_max:         parseInt(document.getElementById("ech-hp").value) || null,
        backstory:      document.getElementById("ech-backstory").value.trim() || null,
      });
      bootstrap.Modal.getInstance(document.getElementById("modal-edit-character")).hide();
      showToast("Character updated!", "success");
      renderCampaignDetail(id, root);
    } catch (e) { showToast(e.message, "danger"); }
  };

  document.querySelectorAll(".btn-delete-char").forEach(btn => {
    btn.onclick = () => {
      const charId   = btn.dataset.charId;
      const charName = btn.dataset.charName;
      confirmInPlace(btn, async () => {
        try {
          await deleteCharacter(charId);
          showToast(`${charName} removed.`, "success");
          renderCampaignDetail(id, root);
        } catch (e) { showToast(e.message, "danger"); }
      });
    };
  });

  document.querySelectorAll(".btn-delete-session").forEach(btn => {
    btn.onclick = () => {
      const sid   = btn.dataset.sessionId;
      const sName = btn.dataset.sessionName;
      confirmInPlace(btn, async () => {
        try {
          await deleteSession(sid);
          showToast(`"${sName}" deleted.`, "success");
          renderCampaignDetail(id, root);
        } catch (e) { showToast(e.message, "danger"); }
      });
    };
  });
}

// ════════════════════════════════════════════════════════
// VIEW: Game Session
// ════════════════════════════════════════════════════════
async function renderSessionView(sessionId, root) {
  let session, characters = [], pastTurns = [], campaignName = "";
  try {
    session = await getSession(sessionId);
    [characters, pastTurns, campaignName] = await Promise.all([
      listCharacters(session.campaign_id),
      getSessionTurns(sessionId).catch(() => []),
      getCampaign(session.campaign_id).then(c => c.name).catch(() => ""),
    ]);
  } catch (e) {
    root.innerHTML = `<div class="empty-state"><p>${e.message}</p><a href="#/" class="btn dd-btn-primary mt-3">Back</a></div>`;
    return;
  }

  State.activeSessionId = sessionId;
  State.characters = characters;
  State.turnLog = [];
  State.enemies = [];
  State.conditions = {};
  State.initiativeOrder = [];
  State.currentTurnIndex = -1;
  State.round = 0;

  root.innerHTML = buildSessionHTML(session, characters, campaignName);
  animateViewIn(root);
  wireSessionEvents(session, characters, root, campaignName);

  requestAnimationFrame(() => {
    document.querySelectorAll(".php-bar-fill").forEach(fill => {
      const target = fill.style.width;
      fill.style.width = "0%";
      requestAnimationFrame(() => { fill.style.width = target; });
    });
  });

  if (pastTurns.length > 0) {
    const feed = document.getElementById("narration-feed");
    const emptyEl = document.getElementById("narration-empty");
    if (emptyEl) emptyEl.remove();

    const histHeader = document.createElement("div");
    histHeader.className = "replay-section-header";
    histHeader.innerHTML = `<i class="bi bi-clock-history me-1"></i>${pastTurns.length} past turn${pastTurns.length !== 1 ? "s" : ""}`;
    feed.append(histHeader);

    pastTurns.forEach(t => {
      replayTurnInFeed(t, characters);
      replayTurnInLog(t, characters);
    });

    const liveDiv = document.createElement("div");
    liveDiv.className = "replay-live-marker";
    liveDiv.innerHTML = `<span>Live</span>`;
    feed.append(liveDiv);

    feed.scrollTop = feed.scrollHeight;
  }

  if (session.status === "completed") {
    const submitBtn = document.getElementById("btn-submit-action");
    const descInput = document.getElementById("action-description");
    const endBtn    = document.getElementById("btn-end-session");
    const composer  = document.querySelector(".action-composer");
    if (submitBtn) submitBtn.disabled = true;
    if (descInput) descInput.disabled = true;
    if (endBtn) {
      endBtn.disabled = true;
      endBtn.innerHTML = `<i class="bi bi-check-circle me-1"></i>Session Ended`;
    }
    if (composer) {
      composer.setAttribute("aria-disabled", "true");
      composer.style.opacity = "";
      composer.style.pointerEvents = "";
    }
    document.querySelectorAll("#action-pill-bar .action-pill").forEach(p => {
      p.disabled = true;
      p.style.cursor = "default";
    });
    const feed = document.getElementById("narration-feed");
    const banner = document.createElement("div");
    banner.className = "narration-block nar-enter";
    const summaryText = session.summary
      ? `<div class="banner-summary-block"><p class="banner-summary">${esc(session.summary)}</p></div>`
      : `<p class="banner-summary" style="opacity:0.5;font-style:italic;">The chronicler's quill scratches in the darkness — the tale of this session passes into legend.</p>`;
    banner.innerHTML = `<div class="session-ended-banner">
      <div class="banner-title"><i class="bi bi-book-half me-2"></i>Chapter Closed</div>
      <p class="banner-subtitle" style="opacity:0.7;font-size:0.85rem;margin-bottom:0.75rem;">The Dungeon Master seals the tome on this session</p>
      ${summaryText}
      <a href="#/campaign/${session.campaign_id}" class="btn dd-btn-primary btn-sm mt-2">
        <i class="bi bi-arrow-left me-1"></i>Return to Campaign
      </a>
    </div>`;
    feed.append(banner);
    feed.scrollTop = feed.scrollHeight;
  }
}

function profBonus(level) {
  return Math.ceil(level / 4) + 1;
}

// ── Spell slot table (full casters: Wizard/Sorcerer/Bard/Druid/Cleric) ──
const _SPELL_SLOTS_FULL = [
  [],                                   // level 0 (unused)
  [2],                                  // level 1
  [3],                                  // level 2
  [4,2],                               // level 3
  [4,3],                               // level 4
  [4,3,2],                             // level 5
  [4,3,3],                             // level 6
  [4,3,3,1],                           // level 7
  [4,3,3,2],                           // level 8
  [4,3,3,3,1],                         // level 9
  [4,3,3,3,2],                         // level 10
  [4,3,3,3,2,1],                       // level 11
  [4,3,3,3,2,1],                       // level 12
  [4,3,3,3,2,1,1],                     // level 13
  [4,3,3,3,2,1,1],                     // level 14
  [4,3,3,3,2,1,1,1],                   // level 15
  [4,3,3,3,2,1,1,1],                   // level 16
  [4,3,3,3,2,1,1,1,1],                 // level 17
  [4,3,3,3,3,1,1,1,1],                 // level 18
  [4,3,3,3,3,2,1,1,1],                 // level 19
  [4,3,3,3,3,2,2,1,1],                 // level 20
];
const _SPELLCASTING_CLASSES = new Set([
  "wizard","sorcerer","bard","druid","cleric","warlock","artificer",
  "paladin","ranger",
]);
function _getSpellSlots(className, level) {
  const cls = (className || "").toLowerCase();
  if (!_SPELLCASTING_CLASSES.has(cls)) return [];
  const lv = Math.max(1, Math.min(20, level || 1));
  return _SPELL_SLOTS_FULL[lv] || [];
}
function _spellSlotHtml(charId, className, level) {
  const slots = _getSpellSlots(className, level);
  if (!slots.length) return "";
  const ordinals = ["1st","2nd","3rd","4th","5th","6th","7th","8th","9th"];
  return `<div class="spell-slots-section" id="spell-slots-${charId}">
    ${slots.map((max, i) => `
      <div class="ss-row" data-slot-level="${i}" data-char-id="${charId}" data-max="${max}">
        <span class="ss-label">${ordinals[i]}</span>
        <div class="ss-pips">
          ${Array.from({length: max}, (_, j) =>
            `<span class="ss-pip" data-pip="${j}" title="Slot ${j+1}"></span>`
          ).join("")}
        </div>
      </div>`).join("")}
  </div>`;
}

function conditionBadge(hp_current, hp_max) {
  if (hp_current <= 0) return `<span class="condition-badge badge-unconscious"><i class="bi bi-moon-stars-fill me-1" style="font-size:0.55rem;"></i>KO</span>`;
  if (hp_max > 0 && hp_current / hp_max <= 0.25) return `<span class="condition-badge badge-bloodied"><i class="bi bi-droplet-half me-1" style="font-size:0.55rem;"></i>Bloodied</span>`;
  return "";
}

function classAvatarHtml(className, charName) {
  const cls = (className || "").toLowerCase().split(" ")[0];
  const known = ["fighter","wizard","rogue","cleric","ranger","paladin","barbarian","bard","druid","monk","sorcerer","warlock"];
  const colorClass = known.includes(cls) ? `char-avatar-${cls}` : "char-avatar-default";
  const initial = (charName || "?").charAt(0).toUpperCase();
  const icon = {
    fighter:"bi-shield-fill", wizard:"bi-stars", rogue:"bi-eye-slash-fill",
    cleric:"bi-brightness-high-fill", ranger:"bi-tree-fill", paladin:"bi-brightness-alt-high",
    barbarian:"bi-fire", bard:"bi-music-note-beamed", druid:"bi-flower1",
    monk:"bi-wind", sorcerer:"bi-lightning-fill", warlock:"bi-eye-fill",
  }[cls];
  return `<span class="char-avatar ${colorClass}" title="${esc(className || "Unknown Class")}">
    ${icon ? `<i class="bi ${icon}" style="font-size:0.7rem;"></i>` : initial}
  </span>`;
}

function buildSessionHTML(session, characters, campaignName = "") {
  const charOptions = characters.map(c =>
    `<option value="${c.id}">${esc(c.character_name)}${c.hp_current <= 0 ? " (KO)" : ""}</option>`).join("");

  const charSidebarItems = characters.map(c => `
    <div class="character-card" id="sidebar-char-${c.id}">
      <div class="d-flex align-items-center justify-content-between mb-1">
        <div class="d-flex align-items-center gap-2">
          <span class="cs-clickable char-sheet-btn" data-char-id="${c.id}" title="View character sheet">
            ${classAvatarHtml(c.class_name, c.character_name)}
          </span>
          <div class="char-name cs-clickable char-sheet-btn" data-char-id="${c.id}"
            title="View character sheet" style="cursor:pointer;">${esc(c.character_name)}</div>
        </div>
        <div class="d-flex align-items-center gap-1">
          <div id="sidebar-cond-${c.id}">${conditionBadge(c.hp_current, c.hp_max)}</div>
          <button class="btn insp-btn" id="insp-${c.id}" data-char-id="${c.id}"
            title="D&D Inspiration — grants advantage on one roll">
            <i class="bi bi-stars"></i>
          </button>
        </div>
      </div>
      <div class="char-meta mb-2">${[c.race, c.class_name].filter(Boolean).map(esc).join(" · ")}<span class="lv-chip">Lv.${c.level}</span></div>
      ${renderHpBar(c.hp_current, c.hp_max)}
      <div class="d-flex justify-content-between mt-2 mb-1" style="font-size:0.72rem;">
        <span class="dd-muted">AC <strong style="color:var(--dd-text);">${c.armor_class}</strong></span>
        <span class="dd-muted">Spd <strong style="color:var(--dd-text);">${c.speed}ft</strong></span>
        <span class="dd-muted">PB <strong style="color:var(--dd-gold);">+${profBonus(c.level)}</strong></span>
        <span class="dd-muted">Init <strong style="color:var(--dd-text);">${modifier(c.dexterity)}</strong></span>
      </div>
      <div class="d-flex gap-1 mt-1">
        <button class="btn btn-xs char-hp-btn heal-btn flex-grow-1" data-char-id="${c.id}" data-action="heal" title="Heal">
          <i class="bi bi-heart-pulse me-1"></i>Heal
        </button>
        <button class="btn btn-xs char-hp-btn dmg-btn flex-grow-1" data-char-id="${c.id}" data-action="dmg" title="Apply damage">
          <i class="bi bi-droplet-half me-1"></i>Dmg
        </button>
        <button class="btn btn-xs btn-outline-secondary char-stats-toggle"
          data-char-id="${c.id}" title="Show ability scores"
          style="padding:0.1rem 0.4rem;font-size:0.65rem;">
          <i class="bi bi-bar-chart-fill"></i>
        </button>
      </div>
      <div class="char-stats-panel" id="char-stats-${c.id}">
        <div class="row g-1">
          ${[["STR",c.strength],["DEX",c.dexterity],["CON",c.constitution],
             ["INT",c.intelligence],["WIS",c.wisdom],["CHA",c.charisma]].map(([ab,score]) => `
            <div class="col-4">
              <div class="stat-box" style="padding:0.2rem;">
                <span class="stat-val" style="font-size:0.85rem;">${modifier(score)}</span>
                <span class="stat-lbl" style="font-size:0.6rem;">${ab}</span>
              </div>
            </div>`).join("")}
        </div>
      </div>
      ${_spellSlotHtml(c.id, c.class_name, c.level)}
      <div class="cond-section" id="cond-section-${c.id}">
        <div class="cond-list" id="cond-list-${c.id}"></div>
        <button class="btn btn-xs cond-add-btn" data-entity="${c.id}" title="Toggle conditions">
          <i class="bi bi-plus-circle"></i>
        </button>
      </div>
    </div>`).join("");

  return `
    <div class="game-layout">

      <!-- ── Left Sidebar: Characters ── -->
      <div class="game-sidebar">
        <div class="dd-section-heading"><i class="bi bi-people me-1"></i>Party (${characters.length})</div>
        ${charSidebarItems || '<p class="dd-muted" style="font-size:0.8rem;">No characters.</p>'}

        <!-- Rest Buttons -->
        <div class="rest-panel">
          <button class="btn btn-xs rest-btn short-rest-btn w-100 mb-1" id="btn-short-rest">
            <i class="bi bi-moon me-1"></i>Short Rest (Hit Dice)
          </button>
          <button class="btn btn-xs rest-btn long-rest-btn w-100" id="btn-long-rest">
            <i class="bi bi-moon-stars me-1"></i>Long Rest (Full HP)
          </button>
        </div>

        <!-- Encounter Tracker -->
        <div class="encounter-panel mt-2">
          <div class="d-flex align-items-center justify-content-between mb-2">
            <div class="dd-section-heading mb-0"><i class="bi bi-shield-exclamation me-1"></i>Encounter</div>
            <div class="d-flex gap-1">
              ${campaignName === DEMO_CAMPAIGN_NAME ? `<button class="btn btn-xs" id="btn-load-demo-cast" title="Load the Sunken Vault cast — NPCs with personas, goals & secrets"
                style="font-size:0.6rem;opacity:0.6;">
                <i class="bi bi-people"></i>
              </button>` : ""}
              <button class="btn btn-xs" id="btn-clear-defeated" title="Remove defeated enemies"
                style="font-size:0.6rem;opacity:0.6;display:none;">
                <i class="bi bi-trash3"></i>
              </button>
              <button class="btn btn-xs encounter-add-btn" id="btn-add-enemy" title="Add enemy">
                <i class="bi bi-plus-lg"></i>
              </button>
            </div>
          </div>
          <div id="enemy-list">
            <div id="enemy-empty" class="dd-muted" style="font-size:0.72rem;font-style:italic;">No enemies tracked.</div>
          </div>
        </div>

        <!-- Initiative Roller -->
        <div class="initiative-panel mt-2">
          <div class="d-flex align-items-center justify-content-between mb-1">
            <div class="d-flex align-items-center gap-2">
              <div class="dd-section-heading mb-0"><i class="bi bi-sort-numeric-down me-1"></i>Initiative</div>
              <span class="round-badge" id="round-badge" style="display:none;">Round <strong id="round-number">1</strong></span>
            </div>
            <div class="d-flex gap-1">
              <button class="btn btn-xs next-turn-btn" id="btn-next-turn" style="display:none;" title="Advance to next combatant">
                Next <i class="bi bi-arrow-right-short"></i>
              </button>
              <button class="btn btn-xs init-roll-btn" id="btn-roll-initiative" title="Roll initiative for all combatants">
                Roll All
              </button>
            </div>
          </div>
          <div id="initiative-list">
            <div class="dd-muted" style="font-size:0.72rem;font-style:italic;">Press Roll All to start combat.</div>
          </div>
          <div class="enemy-turn-panel" id="enemy-turn-panel" style="display:none;">
            <div class="enemy-turn-name" id="enemy-turn-name"></div>
            <button class="btn btn-xs dd-btn-danger w-100 mt-1" id="btn-enemy-attack">
              <i class="bi bi-lightning-charge me-1"></i>Auto-Attack
            </button>
            <div class="enemy-atk-result" id="enemy-atk-result" style="display:none;"></div>
          </div>
          <button class="btn btn-xs w-100 mt-1" id="btn-end-combat"
            style="display:none;font-size:0.62rem;opacity:0.55;border:1px solid rgba(224,64,64,0.25);color:var(--dd-red);">
            <i class="bi bi-x-circle me-1"></i>End Combat
          </button>
        </div>

        <!-- Dice Roller -->
        <div class="dice-roller-panel mt-2">
          <div class="dd-section-heading mb-2"><i class="bi bi-dice-5 me-1"></i>Dice Roller</div>
          <div class="d-flex gap-1 flex-wrap mb-2" id="dice-quick-btns">
            ${["d4","d6","d8","d10","d12","d20","d100"].map(d =>
              `<button class="btn btn-sm btn-outline-secondary dd-dice-quick" data-expr="1${d}" style="font-size:0.72rem;padding:0.15rem 0.4rem;">${d}</button>`
            ).join("")}
          </div>
          <div class="input-group input-group-sm mb-2">
            <input type="text" class="form-control dd-input" id="dice-expr-input" value="1d20" placeholder="2d6+3">
            <button class="btn dd-btn-primary" id="btn-roll-dice">Roll</button>
          </div>
          <div class="dice-result-display" id="dice-result-display">—</div>
          <div class="dice-breakdown" id="dice-breakdown"></div>
          <div id="dice-history" style="margin-top:0.4rem;"></div>
        </div>
      </div>

      <!-- ── Main: Narration + Action Composer ── -->
      <div class="game-main" style="position:relative;">
        <!-- Session Header -->
        <div class="session-header-bar">
          <div class="d-flex align-items-center gap-3 flex-wrap">
            <div>
              ${campaignName ? `<a href="#/campaign/${session.campaign_id}" class="sh-campaign-link">
                <i class="bi bi-map" style="font-size:0.6rem;"></i>${esc(campaignName)}<i class="bi bi-chevron-right"></i>
              </a>` : ""}
              <span class="sh-title"><i class="bi bi-book me-2"></i>${esc(session.name)}</span>
            </div>
            <span class="location-badge" id="location-badge" title="Click to set current location">
              <i class="bi bi-geo-alt me-1"></i><span id="location-text">Set Location</span>
            </span>
          </div>
          <div class="d-flex align-items-center gap-3">
            <span class="session-status-dot ${session.status !== "active" ? "ended" : ""}" title="${session.status === "active" ? "Session active" : "Session ended"}"></span>
            <span class="session-mode-badge" id="session-mode-badge" data-mode="exploration" title="Session mode">
              <i class="bi bi-compass me-1"></i><span id="session-mode-text">Exploration</span>
            </span>
            <span class="sh-meta">Turn <strong id="turn-counter">${session.turn_count}</strong></span>
            ${session.status === "active" ? `<span class="sh-meta session-timer" id="session-timer" title="Session duration"><i class="bi bi-clock me-1" style="font-size:0.65rem;opacity:0.6;"></i><span id="session-timer-text">0:00</span></span>` : ""}
            <a href="#/campaign/${session.campaign_id}" class="btn btn-sm btn-outline-secondary">
              <i class="bi bi-arrow-left me-1"></i>Campaign
            </a>
            <button class="btn btn-sm btn-outline-secondary" id="btn-export-session" title="Export session as text">
              <i class="bi bi-download me-1"></i>Export
            </button>
            <button class="btn btn-sm dd-btn-danger" id="btn-end-session">
              <i class="bi bi-stop-fill me-1"></i>End Session
            </button>
          </div>
        </div>

        <!-- Party Health Mini-Strip -->
        ${characters.length > 0 ? `
        <div class="party-health-strip" id="party-health-strip">
          ${characters.map(c => `
            <div class="party-health-pip" title="${esc(c.character_name)}: ${c.hp_current}/${c.hp_max} HP"
              onclick="openCampaignCharSheet('${c.id}')">
              <div class="php-avatar">${classAvatarHtml(c.class_name, c.character_name)}</div>
              <div class="php-info">
                <div class="php-name">${esc(c.character_name)}</div>
                <div class="php-bar-track">
                  <div class="php-bar-fill ${hpFillClass(c.hp_current, c.hp_max)}"
                    style="width:${hpPct(c.hp_current, c.hp_max)}%"></div>
                </div>
                <div class="php-hp">${c.hp_current}/${c.hp_max}</div>
              </div>
            </div>`).join("")}
        </div>` : ""}

        <!-- Turn Log FAB (narrow screens only) -->
        <button id="btn-toggle-log" title="Turn Log"
          style="display:none;position:fixed;bottom:5rem;right:1rem;z-index:1040;
                 width:2.4rem;height:2.4rem;border-radius:50%;padding:0;
                 background:rgba(201,168,76,0.22);border:1px solid rgba(201,168,76,0.45);
                 color:var(--dd-gold);font-size:0.9rem;line-height:1;cursor:pointer;">
          <i class="bi bi-journal-text"></i>
        </button>

        <!-- Scroll-to-bottom fab -->
        <button id="btn-scroll-bottom" title="Jump to latest"
          style="display:none;position:absolute;bottom:6.5rem;right:1rem;z-index:10;
                 width:2rem;height:2rem;border-radius:50%;padding:0;
                 background:rgba(201,168,76,0.18);border:1px solid rgba(201,168,76,0.35);
                 color:var(--dd-gold);font-size:0.8rem;line-height:1;cursor:pointer;">
          <i class="bi bi-chevron-double-down"></i>
        </button>

        <!-- Narration Feed -->
        <div class="narration-feed" id="narration-feed" aria-live="polite" aria-label="DM Narration">
          <div class="narration-feed-empty" id="narration-empty">
            <div class="narration-empty-icon">⚔</div>
            <div class="narration-empty-title">The Adventure Begins</div>
            <div class="narration-empty-sub">Describe your action below and the DM will narrate your fate…</div>
          </div>
        </div>

        <!-- Action Composer -->
        <div class="action-composer">
          <div class="row g-2 align-items-end">
            <div class="col-sm-3">
              <label class="form-label dd-muted mb-1" style="font-size:0.72rem;text-transform:uppercase;letter-spacing:0.06em;">Character</label>
              <select class="form-select form-select-sm dd-input" id="action-character" aria-label="Acting character">
                ${charOptions}
              </select>
            </div>
            <div class="col-12">
              <label class="form-label dd-muted mb-1" style="font-size:0.72rem;text-transform:uppercase;letter-spacing:0.06em;">Action Type</label>
              <div class="action-pill-bar" id="action-pill-bar">
                <button class="action-pill active" data-type="roleplay" type="button" title="Roleplay (1)"><i class="bi bi-chat-quote"></i> Roleplay</button>
                <button class="action-pill" data-type="attack_melee" type="button" title="Melee attack (2)"><i class="bi bi-sword"></i> Melee</button>
                <button class="action-pill" data-type="attack_ranged" type="button" title="Ranged attack (3)"><i class="bi bi-bullseye"></i> Ranged</button>
                <button class="action-pill" data-type="cast_spell" type="button" title="Cast spell (4)"><i class="bi bi-stars"></i> Spell</button>
                <button class="action-pill" data-type="skill_check" type="button" title="Skill check (5)"><i class="bi bi-clipboard-check"></i> Skill</button>
                <button class="action-pill" data-type="movement" type="button" title="Movement (6)"><i class="bi bi-arrow-up-right"></i> Move</button>
                <button class="action-pill" data-type="talk" type="button" title="Talk / negotiate (7)"><i class="bi bi-person-raised-hand"></i> Talk</button>
                <button class="action-pill" data-type="puzzle_answer" type="button" title="Answer a puzzle (8)"><i class="bi bi-lightbulb"></i> Puzzle</button>
              </div>
              <input type="hidden" id="action-type" value="roleplay">
            </div>
            <div class="col-sm-3" id="target-group" style="display:none;">
              <label class="form-label dd-muted mb-1" id="target-label" style="font-size:0.72rem;text-transform:uppercase;letter-spacing:0.06em;">Target</label>
              <select class="form-select form-select-sm dd-input" id="action-target"></select>
            </div>
            <div class="col-sm-3" id="stat-group" style="display:none;">
              <label class="form-label dd-muted mb-1" style="font-size:0.72rem;text-transform:uppercase;letter-spacing:0.06em;">Ability</label>
              <select class="form-select form-select-sm dd-input" id="action-stat">
                <option value="wis_mod">Wisdom</option>
                <option value="int_mod">Intelligence</option>
                <option value="cha_mod">Charisma</option>
                <option value="dex_mod">Dexterity</option>
                <option value="str_mod">Strength</option>
                <option value="con_mod">Constitution</option>
              </select>
            </div>
            <div class="col-12" id="desc-group">
              <label class="form-label dd-muted mb-1" style="font-size:0.72rem;text-transform:uppercase;letter-spacing:0.06em;">Description</label>
              <div class="action-desc-wrap">
                <textarea class="form-control dd-input action-textarea" id="action-description"
                  placeholder="I draw my sword and strike the goblin… be descriptive!" maxlength="600" rows="3"></textarea>
                <button class="btn dd-btn-primary action-submit-btn" id="btn-submit-action">
                  <i class="bi bi-send-fill me-1"></i>Submit
                </button>
              </div>
              <div class="d-flex justify-content-between align-items-center">
                <div class="action-kb-hint"><kbd>Enter</kbd> submit · <kbd>Shift+Enter</kbd> new line · <kbd>Esc</kbd> clear · <kbd>?</kbd> shortcuts</div>
                <span class="action-char-count" id="action-char-count">0 / 600</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ── Right Panel: Turn Log + Notes ── -->
      <div class="game-log">
        <div class="d-flex align-items-center justify-content-between mb-1">
          <div class="dd-section-heading mb-0"><i class="bi bi-journal-text me-1"></i>Turn Log</div>
          <span id="tl-count" class="dd-muted" style="font-size:0.68rem;"></span>
        </div>
        <div class="d-flex gap-1 flex-wrap mb-2" id="tl-filters" style="display:none;">
          <button class="btn btn-xs tl-filter active" data-filter="all"
            style="font-size:0.62rem;padding:0.05rem 0.45rem;">All</button>
          ${Object.entries(ACTION_ICONS).map(([type, icon]) => `
            <button class="btn btn-xs tl-filter" data-filter="${type}"
              style="font-size:0.62rem;padding:0.05rem 0.45rem;display:none;"
              title="${type.replace(/_/g,' ')}">
              <i class="bi ${icon}"></i>
            </button>`).join("")}
        </div>
        <div id="turn-log-list"></div>
        <div id="turn-log-empty">
          <div class="tl-empty-icon"><i class="bi bi-hourglass"></i></div>
          <span>No turns yet</span>
        </div>

        <!-- Session Notes -->
        <div class="mt-3" style="border-top:1px solid rgba(201,168,76,0.15);padding-top:0.6rem;">
          <button class="btn btn-xs w-100 text-start dd-muted mb-1" id="btn-toggle-notes"
            style="background:none;border:none;font-size:0.72rem;opacity:0.7;">
            <i class="bi bi-pencil-square me-1"></i>Session Notes
            <i class="bi bi-chevron-down ms-1" id="notes-chevron"></i>
          </button>
          <div class="session-notes-panel" id="session-notes-panel">
            <textarea id="session-notes" rows="4"
              class="form-control dd-input"
              style="font-size:0.72rem;min-height:4rem;"
              placeholder="Jot down clues, NPC names, quest hooks…"></textarea>
          </div>
        </div>

        <!-- DM Memory -->
        <div class="mt-3" style="border-top:1px solid rgba(201,168,76,0.15);padding-top:0.6rem;">
          <button class="btn btn-xs w-100 text-start dd-muted mb-1" id="btn-toggle-memory"
            style="background:none;border:none;font-size:0.72rem;opacity:0.7;">
            <i class="bi bi-brain me-1"></i>DM Memory
            <i class="bi bi-chevron-right ms-1" id="memory-chevron"></i>
          </button>
          <div id="dm-memory-panel" style="display:none;">
            <div id="dm-memory-list" style="font-size:0.68rem;"></div>
          </div>
        </div>
      </div>
    </div>`;
}

function wireSessionEvents(session, characters, root, campaignName = "") {
  // ── Session notes (localStorage) ────────────────────
  const NOTES_KEY = `notes_${session.id}`;
  const notesEl = document.getElementById("session-notes");
  const notesPanel = document.getElementById("session-notes-panel");
  const notesBtn = document.getElementById("btn-toggle-notes");
  const notesChevron = document.getElementById("notes-chevron");
  if (notesEl && notesBtn) {
    const NOTES_OPEN_KEY = `notes_open_${session.id}`;
    notesEl.value = localStorage.getItem(NOTES_KEY) || "";
    notesEl.addEventListener("input", () => {
      try { localStorage.setItem(NOTES_KEY, notesEl.value); } catch (_) {}
    });
    if (localStorage.getItem(NOTES_OPEN_KEY) === "1") {
      notesPanel?.classList.add("open");
      notesBtn.classList.add("notes-open");
      if (notesChevron) notesChevron.className = "bi bi-chevron-up ms-1";
    }
    notesBtn.addEventListener("click", () => {
      const isOpen = notesPanel?.classList.contains("open");
      notesPanel?.classList.toggle("open", !isOpen);
      notesBtn.classList.toggle("notes-open", !isOpen);
      if (notesChevron) {
        notesChevron.className = `bi ${!isOpen ? "bi-chevron-up" : "bi-chevron-down"} ms-1`;
      }
      try { localStorage.setItem(NOTES_OPEN_KEY, !isOpen ? "1" : "0"); } catch (_) {}
      if (!isOpen) setTimeout(() => notesEl.focus(), 150);
    });
  }

  // ── DM Memory panel ─────────────────────────────────
  const memoryPanel = document.getElementById("dm-memory-panel");
  const memoryBtn   = document.getElementById("btn-toggle-memory");
  const memoryCaret = document.getElementById("memory-chevron");
  const memoryList  = document.getElementById("dm-memory-list");

  const FACT_TYPE_ICONS = {
    event: "bi-calendar-event", npc: "bi-person-fill", location: "bi-geo-alt-fill",
    lore: "bi-book-fill", character: "bi-person-badge", item: "bi-gem",
  };

  async function loadMemories() {
    if (!memoryList) return;
    try {
      const res = await fetch(`http://localhost:8000/api/v1/sessions/${session.id}/memories`);
      if (!res.ok) return;
      const facts = await res.json();
      if (!facts.length) {
        memoryList.innerHTML = `<div style="opacity:0.45;font-style:italic;padding:0.2rem 0;">No memories yet — play more turns.</div>`;
        return;
      }
      memoryList.innerHTML = facts.map(f => {
        const icon = FACT_TYPE_ICONS[f.fact_type] || "bi-circle-fill";
        const stars = f.importance >= 8 ? "★ " : f.importance >= 5 ? "◆ " : "· ";
        return `<div style="display:flex;gap:0.35rem;align-items:flex-start;margin-bottom:0.3rem;line-height:1.35;">
          <i class="bi ${icon}" style="color:var(--dd-gold);opacity:0.7;margin-top:0.1rem;font-size:0.65rem;flex-shrink:0;"></i>
          <span style="color:var(--dd-text-muted);">${stars}${esc(f.fact_text)}</span>
        </div>`;
      }).join("");
    } catch (_) {}
  }

  if (memoryBtn && memoryPanel) {
    memoryBtn.addEventListener("click", () => {
      const isOpen = memoryPanel.style.display !== "none";
      memoryPanel.style.display = isOpen ? "none" : "";
      if (memoryCaret) {
        memoryCaret.className = `bi ${isOpen ? "bi-chevron-right" : "bi-chevron-down"} ms-1`;
      }
      if (!isOpen) loadMemories();
    });
  }

  // Refresh memory panel after each turn if it's open
  function refreshMemoryIfOpen() {
    if (memoryPanel && memoryPanel.style.display !== "none") loadMemories();
  }

  // ── Scroll-to-bottom button ─────────────────────────
  const feed = document.getElementById("narration-feed");
  const scrollBtn = document.getElementById("btn-scroll-bottom");
  if (feed && scrollBtn) {
    feed.addEventListener("scroll", () => {
      const atBottom = feed.scrollTop + feed.clientHeight >= feed.scrollHeight - 40;
      scrollBtn.style.display = atBottom ? "none" : "";
    });
    scrollBtn.addEventListener("click", () => {
      feed.scrollTop = feed.scrollHeight;
    });
  }

  // ── Active character highlight ──────────────────────
  const charSelect = document.getElementById("action-character");
  function highlightActiveChar(id) {
    document.querySelectorAll(".character-card").forEach(el => el.classList.remove("party-active"));
    const card = document.getElementById(`sidebar-char-${id}`);
    if (card) { card.classList.add("party-active"); card.scrollIntoView({ behavior: "smooth", block: "nearest" }); }
  }
  charSelect.addEventListener("change", () => highlightActiveChar(charSelect.value));
  if (charSelect.value) highlightActiveChar(charSelect.value);

  // ── M11 stage 2: the location badge is a READ-OUT of the engine location
  //    (no more free-text typing), and the action target is populated from
  //    the engine scene — exits for Move, entities-in-room for Melee/Talk.
  const locationBadge = document.getElementById("location-badge");
  const locationText  = document.getElementById("location-text");
  if (locationBadge) {
    locationBadge.title = "Current location (from the engine)";
    if (locationText) locationText.textContent = "…";
  }

  let m11Scene = null;
  const M11_ENTITY_TARGET_TYPES = new Set(["attack_melee", "attack_ranged", "talk"]);
  const M11_MOVE_TARGET_TYPES   = new Set(["movement", "move"]);

  function m11PopulateTargets() {
    const tg  = document.getElementById("target-group");
    const sel = document.getElementById("action-target");
    const lbl = document.getElementById("target-label");
    const statGroup = document.getElementById("stat-group");
    const type = document.getElementById("action-type")?.value || "roleplay";
    if (!tg || !sel) return;
    if (statGroup) statGroup.style.display = "none";  // only shown for skill_check
    let options = [];
    if (M11_MOVE_TARGET_TYPES.has(type)) {
      if (lbl) lbl.textContent = "Destination";
      options = (m11Scene?.exits || []).map(e => ({ value: e.id, label: e.name }));
    } else if (M11_ENTITY_TARGET_TYPES.has(type)) {
      if (lbl) lbl.textContent = "Target";
      options = (m11Scene?.entities_here || []).map(e => ({
        value: e.id,
        label: e.name + (e.status === "hostile" ? " — hostile" : ""),
      }));
    } else if (type === "skill_check") {
      // The engine derives the DC from the chosen target's `{purpose}_dc`, so
      // the option value carries both id and purpose ("id::purpose"); the player
      // also picks which ability to roll (the Ability selector).
      if (lbl) lbl.textContent = "Check";
      options = (m11Scene?.check_targets || []).map(ct => ({
        value: `${ct.id}::${ct.purpose}`,
        label: `${ct.name} — ${ct.purpose}`,
      }));
      if (statGroup) statGroup.style.display = options.length ? "" : "none";
    } else {
      tg.style.display = "none";  // roleplay/spell/puzzle: no engine target
      return;
    }
    sel.innerHTML = options.length
      ? options.map(o => `<option value="${esc(o.value)}">${esc(o.label)}</option>`).join("")
      : `<option value="">(none here)</option>`;
    tg.style.display = "";
  }

  // A skill-check verdict chip from the engine's check_result (real DC + roll),
  // e.g. "PASS · insight (WIS) 17 vs DC 11".
  function m11CheckChip(cr) {
    if (!cr) return "";
    const ability = (cr.stat || "").replace(/_mod$/, "").toUpperCase();
    const verdict = cr.success ? "PASS" : "FAIL";
    return `<span class="dice-chip skill-${cr.success ? "pass" : "fail"}">`
      + `${verdict} · ${esc(cr.purpose || "check")}`
      + `${ability ? ` (${esc(ability)})` : ""} ${cr.total} vs DC ${cr.dc}</span>`;
  }

  // ── M11: engine-backed combat panel ────────────────────────────────
  // The team's encounter/initiative panels were a client-side simulation
  // (localStorage, manual Roll-All / Next / Auto-Attack). They now mirror the
  // engine projection: enemy HP, death, initiative order and the round counter
  // all come from the backend `combat` read-out on every turn. The manual
  // controls are retired for engine-backed sessions.
  let m11EngineCombat = false;

  // Set once the party completes every objective. Stops the all-AI advance loop
  // (it used to keep generating aimless turns after the adventure was won) and
  // drops a victory banner. The session stays active so the player can end it
  // for the summary, or play on.
  let m11Won = false;
  function m11ShowVictory() {
    if (m11Won) return;            // once
    m11Won = true;
    const feed = document.getElementById("narration-feed");
    if (feed) {
      const el = document.createElement("div");
      el.className = "narration-block";
      el.innerHTML = `<div class="session-end-banner">
        <div class="session-end-title"><i class="bi bi-trophy-fill me-2"></i>Objective Complete</div>
        <p class="banner-summary">The party has achieved its goal. The engine has paused here — end the session to record the tale, or play on.</p>
      </div>`;
      feed.append(el);
      feed.scrollTop = feed.scrollHeight;
    }
    document.getElementById("m11-run-ai")?.style.setProperty("display", "none");
    try { showToast("Objective complete!", "success"); } catch (_) {}
  }

  function m11HideManualCombatControls() {
    ["btn-add-enemy", "btn-roll-initiative", "btn-next-turn",
     "btn-end-combat", "btn-clear-defeated"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.style.display = "none";
    });
    const panel = document.getElementById("enemy-turn-panel");
    if (panel) panel.style.display = "none";
  }

  function m11RenderCombat(combat) {
    if (!combat) return;
    m11EngineCombat = true;           // engine owns combat from here on
    m11HideManualCombatControls();

    if (!combat.active) {             // exploration → empty the panels
      State.enemies = [];
      State.initiativeOrder = [];
      State.currentTurnIndex = -1;
      State.round = 0;
      renderEnemies();
      renderInitiativeList();
      return;
    }

    State.round = combat.round || 1;
    State.enemies = (combat.enemies || []).map(e => ({
      id: e.id, name: e.name,
      hp: e.dead ? 0 : (e.hp ?? 0), maxHp: e.max_hp ?? e.hp ?? 0,
      ac: e.ac, attackBonus: e.attack_mod, status: e.status,
    }));
    State.initiativeOrder = (combat.order || []).map(o => ({
      name: o.name, isEnemy: o.kind === "npc",
      hp: o.dead ? 0 : (o.hp ?? 0), maxHp: o.max_hp ?? o.hp ?? 0,
      total: o.initiative ?? 0, roll: o.initiative ?? 0, dexMod: 0,
      entityId: o.id, ac: o.ac, attackBonus: o.attack_mod,
    }));
    State.currentTurnIndex = (combat.order || []).findIndex(o => o.is_active);
    renderEnemies();
    renderInitiativeList();
    m11HideManualCombatControls();   // re-hide enemy-turn-panel after render
  }

  async function m11RefreshScene() {
    const cid = charSelect?.value;
    if (!cid) return;
    try {
      m11Scene = await getScene(session.id, cid);
      if (locationText) {
        locationText.textContent = m11Scene.location?.name || "Unknown";
        locationBadge?.classList.add("has-location");
      }
      m11PopulateTargets();
      if (m11Scene.seats) m11RenderSeats(m11Scene.seats, m11Scene.next_turn);
      m11RenderCombat(m11Scene.combat);
    } catch (e) {
      // Non-demo session / no engine world: leave the badge as-is.
    }
  }

  // ── M11 stage 3.5: per-seat AI/Human toggles + a "run AI/NPC turns" button
  //    (all-AI = every seat AI → click Run to watch the engine play itself).
  function m11EnsureSeatBar() {
    if (document.getElementById("m11-seat-bar")) return;
    const composer = document.querySelector(".action-composer");
    if (!composer) return;
    const bar = document.createElement("div");
    bar.id = "m11-seat-bar";
    bar.style.cssText = "display:flex;gap:0.4rem;align-items:center;flex-wrap:wrap;margin-bottom:0.55rem;";
    composer.prepend(bar);
  }

  function m11RenderSeats(seats, nextTurn) {
    m11EnsureSeatBar();
    const bar = document.getElementById("m11-seat-bar");
    if (!bar) return;
    let html = `<span class="dd-muted" style="font-size:0.7rem;text-transform:uppercase;letter-spacing:0.06em;">Seats:</span>`;
    (seats || []).forEach(s => {
      const ai = s.controller === "ai";
      html += `<button type="button" class="btn btn-sm ${ai ? "btn-info" : "btn-outline-secondary"} m11-seat-toggle"`
        + ` data-cid="${esc(s.character_id)}" data-ctrl="${ai ? "ai" : "human"}"`
        + ` style="padding:1px 8px;font-size:0.72rem;">${esc(s.name)}: ${ai ? "AI" : "Human"}</button>`;
    });
    const aiTurn = nextTurn && nextTurn.engine_id && !nextTurn.is_human;
    html += `<button type="button" id="m11-run-ai" class="btn btn-sm btn-warning"`
      + ` style="padding:1px 8px;font-size:0.72rem;${aiTurn ? "" : "display:none;"}">▶ Run AI / NPC turns</button>`;
    bar.innerHTML = html;
    bar.querySelectorAll(".m11-seat-toggle").forEach(btn => {
      btn.addEventListener("click", async () => {
        const cid = btn.dataset.cid;
        const next = btn.dataset.ctrl === "ai" ? "human" : "ai";
        try {
          const res = await setSeats(session.id, { [cid]: next });
          m11RenderSeats(res.seats, res.next_turn);
          if (res.next_turn && res.next_turn.engine_id && !res.next_turn.is_human) {
            m11MaybeAutoAdvance(res.next_turn);
          }
        } catch (e) { showToast(e.message, "danger"); }
      });
    });
    const runBtn = document.getElementById("m11-run-ai");
    if (runBtn) runBtn.addEventListener("click", () => m11MaybeAutoAdvance(nextTurn));
  }

  // ── M11 stage 3: after a human acts, drive the engine's own turns
  //    (enemy/NPC reactions in initiative order) until it's a human's turn.
  let m11Advancing = false;

  // Update the top party-health mini-strip pip for a character (the left
  // sidebar is handled separately). The pip has no id, so it's keyed off the
  // onclick handler the markup already carries.
  function m11SyncPartyPip(cid, hpCurrent, hpMax) {
    const pip = document.querySelector(`.party-health-pip[onclick*="${cid}"]`);
    if (!pip) return;
    const fill = pip.querySelector(".php-bar-fill");
    const hpEl = pip.querySelector(".php-hp");
    if (fill) {
      fill.style.width = `${hpPct(hpCurrent, hpMax)}%`;
      fill.className = `php-bar-fill ${hpFillClass(hpCurrent, hpMax)}`;
    }
    if (hpEl) hpEl.textContent = `${hpCurrent}/${hpMax}`;
  }

  function m11ApplyStateChanges(changes) {
    if (!changes) return;
    Object.entries(changes).forEach(([cid, change]) => {
      m11SyncPartyPip(cid, change.hp_current, change.hp_max);  // top strip
      const card = document.getElementById(`sidebar-char-${cid}`);
      if (!card) return;
      const fill = card.querySelector(".hp-bar-fill");
      const hpText = card.querySelector(".hp-value");
      if (fill) {
        fill.style.width = `${hpPct(change.hp_current, change.hp_max)}%`;
        fill.className = `hp-bar-fill ${hpFillClass(change.hp_current, change.hp_max)} hp-damaged`;
        setTimeout(() => fill.classList.remove("hp-damaged"), 600);
      }
      if (hpText) hpText.textContent = `${change.hp_current} / ${change.hp_max}`;
      const condEl = document.getElementById(`sidebar-cond-${cid}`);
      if (condEl) condEl.innerHTML = conditionBadge(change.hp_current, change.hp_max);
    });
  }

  function m11ExtractQuotes(text) {
    // Pull quoted spans (straight or curly quotes) from an NPC's narration to
    // surface as spoken dialogue.
    const out = [];
    const re = /[“"]([^”"]{2,300}?)[”"]/g;
    let m;
    while ((m = re.exec(text || "")) !== null) {
      const s = m[1].trim();
      if (s.length >= 2) out.push(s);
    }
    return out;
  }

  function m11RenderEngineTurn(result, narration) {
    const feed = document.getElementById("narration-feed");
    if (!feed) return;
    const name = (result && result.actor_name) || "";
    const kind = (result && result.actor_kind) || "npc";
    const label = kind === "npc" ? name : (name ? `${name} (AI)` : "AI");
    const actorProse = (result && result.actor_prose || "").trim();

    // An AI-controlled hero declares its own turn in character — surface that
    // prose the same way a human player's typed action renders (speaker — prose)
    // so the AI seat reads like another player at the table, not silent input
    // that only the DM speaks for. NPCs commit no prose (actor_prose is ""),
    // so this block is PC-only; their voice still rides the narration below.
    if (kind === "pc" && actorProse) {
      const actEl = document.createElement("div");
      actEl.className = "narration-block nar-enter";
      actEl.innerHTML = `<div class="narration-action" data-type="ai_turn">`
        + `<strong>${esc(label)}</strong> — <em>${esc(actorProse)}</em></div>`;
      feed.append(actEl);
    }

    // Hostile NPCs (the Cinder Sentinel, husks, …) get a red theme — same
    // palette as the interface, but signalling "this one's an enemy". Friendly
    // NPCs stay gold; AI heroes stay blue.
    const hostile = kind === "npc" && !!(result && result.actor_hostile);
    const speakerStyle = hostile ? ' style="color:var(--dd-red);"' : "";

    // Surface quoted NPC speech as a speech bubble (reusing the house style).
    if (kind === "npc" && name) {
      m11ExtractQuotes(narration).forEach(speech => {
        const npcEl = document.createElement("div");
        npcEl.className = "narration-block nar-enter";
        npcEl.innerHTML = `<div class="narration-npc"${hostile ? ' style="border-color:rgba(224,64,64,0.45);"' : ""}>`
          + `<div class="npc-speaker"${speakerStyle}>${esc(name)}</div>`
          + `<div class="npc-speech">&ldquo;${esc(speech)}&rdquo;</div></div>`;
        feed.append(npcEl);
      });
    }

    let chips = "";
    if (result && result.attack_result) {
      const ar = result.attack_result;
      const cls = ar.is_hit ? "hit" : "miss";
      chips = `<span class="dice-chip ${cls}">${ar.is_hit ? "HIT" : "MISS"} · roll ${ar.total_roll}</span>`
        + (ar.is_hit ? `<span class="dice-chip">${ar.damage} dmg</span>` : "");
    }
    // An AI hero / NPC skill check gets the same PASS/FAIL chip as a human's.
    if (result && result.check_result) chips += m11CheckChip(result.check_result);

    // The acting beat: speaker label + narration, tinted by actor kind so engine
    // turns read as "this NPC/AI hero acted" rather than anonymous DM narration.
    // Hostile NPC → red, friendly NPC → gold, AI hero → blue.
    const borderColor = hostile ? "var(--dd-red)"
      : kind === "npc" ? "var(--dd-gold-muted, #b9912f)" : "rgba(91,168,232,0.6)";
    const labelStyle = hostile ? "opacity:0.95;color:var(--dd-red);" : "opacity:0.85;";
    const block = document.createElement("div");
    block.className = "narration-block nar-enter";
    block.innerHTML = `<div class="narration-dm m11-engine-turn" style="border-left:2px solid ${borderColor};padding-left:0.6rem;">`
      + (label ? `<div class="npc-speaker" style="${labelStyle}">${esc(label)}</div>` : "")
      + (chips ? `<div class="narration-result">${chips}</div>` : "")
      + `${formatNarration(narration || "")}</div>`;
    feed.append(block);
    feed.scrollTop = feed.scrollHeight;
    if (result) m11ApplyStateChanges(result.state_changes);
    // Keep the header turn counter moving on engine turns too (it used to
    // advance only on human submits, so all-AI / auto-advance looked frozen).
    if (result && typeof result.turn_number === "number") m11BumpTurnCounter(result.turn_number + 1);
  }

  function m11BumpTurnCounter(n) {
    const tcEl = document.getElementById("turn-counter");
    if (!tcEl) return;
    tcEl.textContent = n;
    tcEl.classList.remove("turn-bump");
    void tcEl.offsetWidth;
    tcEl.classList.add("turn-bump");
    setTimeout(() => tcEl.classList.remove("turn-bump"), 400);
  }

  // A "someone is thinking" bubble shown while an engine turn (AI player or NPC)
  // is being composed in the background — so the table doesn't look frozen
  // during the LLM round-trip (the DM already had its own thinking indicator).
  function m11ShowComposing(info) {
    const feed = document.getElementById("narration-feed");
    if (!feed || !info) return null;
    const name = info.actor_name || (info.kind === "npc" ? "An adversary" : "An ally");
    const label = info.kind === "pc" ? `${name} (AI)` : name;
    const verb = info.kind === "npc" ? "is acting" : "is deciding their move";
    const el = document.createElement("div");
    el.className = "narration-block narration-thinking m11-composing";
    el.innerHTML = `<div class="dm-thinking">
      <div class="dm-thinking-dots"><span></span><span></span><span></span></div>
      <span class="dm-thinking-label">${esc(label)} ${verb}…</span>
    </div>`;
    feed.append(el);
    feed.scrollTop = feed.scrollHeight;
    return el;
  }
  function m11RemoveComposing(el) { if (el && el.parentNode) el.remove(); }

  function m11RunOneAdvance(upcoming) {
    return new Promise((resolve) => {
      const composing = m11ShowComposing(upcoming);
      let result = null, narration = "", nextTurn = null;
      advanceStream(session.id, (chunk) => {
        if (chunk.type === "idle") {
          nextTurn = chunk.next_turn;
          // Backend refused because the session was ended — stop the loop.
          if (chunk.ended) session.status = "completed";
          // Objective met — stop the loop and celebrate.
          if (chunk.objective_complete) m11ShowVictory();
          m11RemoveComposing(composing);
        }
        else if (chunk.type === "result") { result = chunk; m11RemoveComposing(composing); }
        else if (chunk.type === "token") narration += chunk.text || "";
        else if (chunk.type === "done") { nextTurn = chunk.next_turn; m11RenderEngineTurn(result, narration); m11RenderCombat(chunk.combat); if (chunk.objective_complete) m11ShowVictory(); }
      }).then(() => { m11RemoveComposing(composing); resolve(nextTurn); })
        .catch(() => { m11RemoveComposing(composing); resolve(null); });
    });
  }

  function m11ApplyTurnState(nt) {
    if (!nt) return;
    if (nt.mode === "combat") { try { applySessionMode("combat"); } catch (_) {} }
    else if (nt.mode === "exploration") { try { applySessionMode("exploration"); } catch (_) {} }
  }

  async function m11MaybeAutoAdvance(nextTurn) {
    // An ended or won session never advances (a stale loop or a late Run-button
    // click must not resurrect a finished adventure).
    if (session.status === "completed" || m11Won) return;
    m11ApplyTurnState(nextTurn);
    // Nothing engine-driven to run → just refresh + hand the turn to the human.
    if (!nextTurn || !nextTurn.engine_id || nextTurn.is_human) {
      m11AfterTurns(nextTurn);
      return;
    }
    if (m11Advancing) return;
    m11Advancing = true;
    try {
      let nt = nextTurn, guard = 0;
      while (nt && nt.engine_id && !nt.is_human && guard < 20
             && session.status !== "completed" && !m11Won) {
        guard++;
        nt = await m11RunOneAdvance(nt);  // pass who's up so we can show "X is composing…"
        m11ApplyTurnState(nt);
      }
      m11AfterTurns(nt);
    } finally {
      m11Advancing = false;
    }
  }

  function m11AfterTurns(nt) {
    m11RefreshScene();
    // Auto-select the character whose (human) turn is next, so the player
    // always sees whose move it is.
    if (nt && nt.is_human && nt.actor_id && charSelect) {
      const opt = [...charSelect.options].some(o => o.value === nt.actor_id);
      if (opt && charSelect.value !== nt.actor_id) {
        charSelect.value = nt.actor_id;
        charSelect.dispatchEvent(new Event("change"));
      }
    }
  }

  if (charSelect) charSelect.addEventListener("change", m11RefreshScene);
  if (session.status === "active") m11RefreshScene();

  // ── Session mode cycling ───────────────────────────
  const _MODES = [
    { mode: "exploration", label: "Exploration", icon: "bi-compass"     },
    { mode: "combat",      label: "Combat",      icon: "bi-shield-fill" },
    { mode: "social",      label: "Social",      icon: "bi-people-fill" },
    { mode: "rest",        label: "Rest",        icon: "bi-moon-stars"  },
  ];
  const MODE_KEY = `session_mode_${session.id}`;
  function applySessionMode(modeName) {
    const m = _MODES.find(x => x.mode === modeName) || _MODES[0];
    const badge = document.getElementById("session-mode-badge");
    const text  = document.getElementById("session-mode-text");
    if (!badge || !text) return;
    badge.dataset.mode = m.mode;
    text.textContent   = m.label;
    const ico = badge.querySelector("i");
    if (ico) ico.className = `bi ${m.icon} me-1`;
    try { localStorage.setItem(MODE_KEY, m.mode); } catch (_) {}
  }
  applySessionMode(localStorage.getItem(MODE_KEY) || "exploration");
  document.getElementById("session-mode-badge")?.addEventListener("click", () => {
    const cur = document.getElementById("session-mode-badge")?.dataset.mode || "exploration";
    const idx = _MODES.findIndex(x => x.mode === cur);
    const next = _MODES[(idx + 1) % _MODES.length];
    applySessionMode(next.mode);
    showToast(`Mode: ${next.label}`, "info");
  });

  // ── Inspiration tracker ────────────────────────────
  const INSP_KEY = `inspiration_${session.id}`;
  let _inspState = {};
  try { _inspState = JSON.parse(localStorage.getItem(INSP_KEY) || "{}"); } catch (_) {}
  function _saveInsp() { try { localStorage.setItem(INSP_KEY, JSON.stringify(_inspState)); } catch (_) {} }
  function _renderInspBtn(charId) {
    const btn = document.getElementById(`insp-${charId}`);
    if (!btn) return;
    btn.classList.toggle("inspired", !!_inspState[charId]);
    btn.title = _inspState[charId]
      ? "Inspired! (click to use inspiration)"
      : "D&D Inspiration — grants advantage on one roll";
  }
  characters.forEach(c => _renderInspBtn(c.id));
  document.querySelectorAll(".insp-btn").forEach(btn => {
    btn.addEventListener("click", e => {
      e.stopPropagation();
      const charId = btn.dataset.charId;
      _inspState[charId] = !_inspState[charId];
      _saveInsp();
      _renderInspBtn(charId);
      const c = characters.find(ch => ch.id === charId);
      const name = c ? c.character_name : "Character";
      showToast(_inspState[charId]
        ? `${name} is Inspired! (advantage on next roll)`
        : `${name} used Inspiration.`, "info");
    });
  });

  // ── Encounter tracker ──────────────────────────────
  document.getElementById("btn-add-enemy")?.addEventListener("click", () => {
    const nameInput = document.getElementById("enemy-name-input");
    const hpInput   = document.getElementById("enemy-hp-input");
    const acInput   = document.getElementById("enemy-ac-input");
    const atkInput  = document.getElementById("enemy-atk-input");
    if (nameInput) { nameInput.value = ""; nameInput.classList.remove("is-invalid"); }
    if (hpInput)   hpInput.value = "20";
    if (acInput)   acInput.value = "12";
    if (atkInput)  atkInput.value = "3";
    ["enemy-persona-input","enemy-disposition-input","enemy-goals-input",
     "enemy-secret-input","enemy-levers-input"].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = "";
    });
    // Collapse persona section when opening fresh
    const collapse = document.getElementById("enemy-persona-collapse");
    if (collapse) bootstrap.Collapse.getOrCreateInstance(collapse, { toggle: false }).hide();
    const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById("modal-add-enemy"));
    modal.show();
    setTimeout(() => nameInput?.focus(), 300);
  });

  document.getElementById("btn-confirm-add-enemy")?.addEventListener("click", () => {
    const nameInput = document.getElementById("enemy-name-input");
    const hpInput   = document.getElementById("enemy-hp-input");
    const acInput   = document.getElementById("enemy-ac-input");
    const atkInput  = document.getElementById("enemy-atk-input");
    const name = nameInput?.value.trim();
    if (!name) { nameInput?.classList.add("is-invalid"); return; }
    const hp = Math.max(1, parseInt(hpInput?.value) || 20);
    const ac = Math.max(0, parseInt(acInput?.value) || 12);
    const attackBonus = parseInt(atkInput?.value) || 0;
    const persona      = document.getElementById("enemy-persona-input")?.value.trim() || null;
    const disposition  = document.getElementById("enemy-disposition-input")?.value.trim() || null;
    const goalsRaw     = document.getElementById("enemy-goals-input")?.value.trim() || "";
    const goals        = goalsRaw ? goalsRaw.split(",").map(g => g.trim()).filter(Boolean) : null;
    const secret       = document.getElementById("enemy-secret-input")?.value.trim() || null;
    const levers       = document.getElementById("enemy-levers-input")?.value.trim() || null;
    bootstrap.Modal.getInstance(document.getElementById("modal-add-enemy"))?.hide();
    addEnemy(name, hp, ac, attackBonus, { persona, disposition, goals, secret, negotiation_levers: levers });
  });

  document.getElementById("form-add-enemy")?.addEventListener("submit", e => {
    e.preventDefault();
    document.getElementById("btn-confirm-add-enemy")?.click();
  });

  const ENEMY_STORE_KEY = `enemies_${session.id}`;

  function saveEnemies() {
    try { localStorage.setItem(ENEMY_STORE_KEY, JSON.stringify(State.enemies)); } catch (_) {}
  }

  function loadEnemies() {
    try {
      const raw = localStorage.getItem(ENEMY_STORE_KEY);
      if (raw) State.enemies = JSON.parse(raw);
    } catch (_) {}
  }

  function addEnemy(name, maxHp, ac = 12, attackBonus = 3, persona = {}) {
    const id = `enemy-${Date.now()}`;
    const entry = { id, name, hp: maxHp, maxHp, ac, attackBonus, ...persona };
    State.enemies.push(entry);
    saveEnemies();
    renderEnemies();
    return entry;
  }

  function ensureEnemy(name) {
    const match = State.enemies.find(
      e => e.name.toLowerCase() === name.toLowerCase()
    );
    return match || addEnemy(name, 30, 12, 3);
  }

  // Seed the demo dungeon cast (skips any NPC already tracked). Returns count added.
  function seedDemoCast() {
    const existing = new Set(State.enemies.map(e => e.name.toLowerCase()));
    let added = 0;
    SUNKEN_VAULT_NPCS.forEach((npc, i) => {
      if (existing.has(npc.name.toLowerCase())) return;
      State.enemies.push({
        id: `enemy-demo-${i}-${Date.now()}`,
        name: npc.name,
        hp: npc.hp,
        maxHp: npc.hp,
        ac: npc.ac,
        attackBonus: npc.attackBonus ?? 3,
        persona: npc.persona || null,
        disposition: npc.disposition || null,
        goals: npc.goals || null,
        secret: npc.secret || null,
        negotiation_levers: npc.negotiation_levers || null,
      });
      added++;
    });
    if (added) { saveEnemies(); renderEnemies(); }
    return added;
  }

  function damageEnemy(id, amount) {
    const e = State.enemies.find(e => e.id === id);
    if (!e) return;
    e.hp = Math.max(0, e.hp - amount);
    const initEntry = State.initiativeOrder.find(r => r.isEnemy && r.name === e.name);
    if (initEntry) initEntry.hp = e.hp;
    saveEnemies();
    renderEnemies();
    renderInitiativeList();
    if (e.hp === 0) showToast(`${e.name} has fallen!`, "warning");
  }

  function syncEnemyDatalist() {
    const dl = document.getElementById("enemy-datalist");
    if (!dl) return;
    dl.innerHTML = State.enemies
      .filter(e => e.hp > 0)
      .map(e => `<option value="${esc(e.name)}">`)
      .join("");
  }

  function renderEnemies() {
    const list = document.getElementById("enemy-list");
    const empty = document.getElementById("enemy-empty");
    if (!list) return;

    const clearBtn = document.getElementById("btn-clear-defeated");
    if (clearBtn) clearBtn.style.display = State.enemies.some(e => e.hp <= 0) ? "" : "none";

    syncEnemyDatalist();

    if (State.enemies.length === 0) {
      list.innerHTML = `<div id="enemy-empty" class="dd-muted" style="font-size:0.72rem;font-style:italic;">No enemies tracked.</div>`;
      return;
    }
    list.innerHTML = State.enemies.map(e => {
      const pct = e.maxHp > 0 ? Math.max(0, Math.min(100, (e.hp / e.maxHp) * 100)) : 0;
      const cls = pct <= 0 ? "hp-low" : pct <= 25 ? "hp-low" : pct <= 50 ? "hp-mid" : "";
      const dead = e.hp <= 0 ? "enemy-dead" : "";
      return `
        <div class="enemy-card ${dead}" id="${e.id}">
          <div class="d-flex align-items-center justify-content-between mb-1">
            <span class="enemy-name">${esc(e.name)}</span>
            ${m11EngineCombat ? "" : `<div class="d-flex gap-1">
              <button class="btn btn-xs enemy-dmg-btn" data-id="${e.id}" title="Apply damage">
                <i class="bi bi-dash-circle"></i>
              </button>
              <button class="btn btn-xs enemy-del-btn" data-id="${e.id}" title="Remove">
                <i class="bi bi-x"></i>
              </button>
            </div>`}
          </div>
          <div class="d-flex justify-content-between mb-1">
            <span class="dd-muted" style="font-size:0.65rem;">HP</span>
            <span style="font-size:0.65rem;color:var(--dd-text-muted);">${e.hp} / ${e.maxHp}</span>
          </div>
          <div class="hp-bar-track">
            <div class="hp-bar-fill ${cls}" style="width:${pct}%"></div>
          </div>
          <div class="d-flex gap-2 mt-1">
            <span class="dd-muted" style="font-size:0.6rem;">AC <strong style="color:var(--dd-text);">${e.ac ?? 12}</strong></span>
            <span class="dd-muted" style="font-size:0.6rem;">Atk <strong style="color:var(--dd-text);">${(e.attackBonus ?? 3) >= 0 ? "+" : ""}${e.attackBonus ?? 3}</strong></span>
          </div>
          <div class="cond-section" id="cond-section-${e.id}">
            <div class="cond-list" id="cond-list-${e.id}"></div>
            <button class="btn btn-xs cond-add-btn" data-entity="${e.id}" title="Toggle conditions">
              <i class="bi bi-plus-circle"></i>
            </button>
          </div>
        </div>`;
    }).join("");

    list.querySelectorAll(".enemy-dmg-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const card = document.getElementById(btn.dataset.id);
        if (!card) return;
        let row = card.querySelector(".enemy-dmg-row");
        if (row) { row.remove(); return; }
        row = document.createElement("div");
        row.className = "enemy-dmg-row d-flex gap-1 mt-1";
        row.innerHTML = `
          <input type="number" class="form-control form-control-sm dd-input enemy-dmg-input"
            min="1" max="999" value="5" style="width:4.5rem;font-size:0.72rem;padding:2px 6px;">
          <button class="btn btn-xs dd-btn-danger enemy-dmg-apply" title="Apply">
            <i class="bi bi-check"></i>
          </button>`;
        card.appendChild(row);
        const inp = row.querySelector(".enemy-dmg-input");
        inp.focus(); inp.select();
        const apply = () => {
          const dmg = parseInt(inp.value);
          if (dmg > 0) damageEnemy(btn.dataset.id, dmg);
        };
        row.querySelector(".enemy-dmg-apply").addEventListener("click", apply);
        inp.addEventListener("keydown", e => {
          if (e.key === "Enter") apply();
          if (e.key === "Escape") row.remove();
        });
      });
    });
    list.querySelectorAll(".enemy-del-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        State.enemies = State.enemies.filter(e => e.id !== btn.dataset.id);
        saveEnemies();
        renderEnemies();
        renderAllCondLists();
      });
    });
  }

  function offerDamageToEnemy(damage) {
    if (State.enemies.length === 0 || damage <= 0) return;
    const alive = State.enemies.filter(e => e.hp > 0);
    if (alive.length === 0) return;
    if (alive.length === 1) {
      damageEnemy(alive[0].id, damage);
      showToast(`Applied ${damage} dmg to ${alive[0].name}`, "info");
    }
    // If multiple alive enemies, let user click manually
  }

  document.getElementById("btn-clear-defeated")?.addEventListener("click", () => {
    State.enemies = State.enemies.filter(e => e.hp > 0);
    saveEnemies();
    renderEnemies();
    renderAllCondLists();
    showToast("Defeated enemies cleared.", "info");
  });

  // ── Spell Slots ─────────────────────────────────────
  const SS_KEY = `spellslots_${session.id}`;
  let _ssState = {};
  try { const raw = localStorage.getItem(SS_KEY); if (raw) _ssState = JSON.parse(raw); } catch (_) {}

  function _saveSpellSlots() {
    try { localStorage.setItem(SS_KEY, JSON.stringify(_ssState)); } catch (_) {}
  }
  function _ssCharKey(charId, level) { return `${charId}_${level}`; }
  function _renderSpellSlots(charId) {
    const section = document.getElementById(`spell-slots-${charId}`);
    if (!section) return;
    section.querySelectorAll(".ss-row").forEach(row => {
      const slotLevel = parseInt(row.dataset.slotLevel);
      const max = parseInt(row.dataset.max);
      const key = _ssCharKey(charId, slotLevel);
      const used = _ssState[key] || 0;
      row.querySelectorAll(".ss-pip").forEach((pip, j) => {
        pip.classList.toggle("ss-used", j < used);
      });
    });
  }
  function _initSpellSlots() {
    document.querySelectorAll(".spell-slots-section").forEach(section => {
      const charId = section.id.replace("spell-slots-", "");
      _renderSpellSlots(charId);
      section.querySelectorAll(".ss-pip").forEach(pip => {
        pip.addEventListener("click", e => {
          e.stopPropagation();
          const row = pip.closest(".ss-row");
          const slotLevel = parseInt(row.dataset.slotLevel);
          const max = parseInt(row.dataset.max);
          const pipIdx = parseInt(pip.dataset.pip);
          const key = _ssCharKey(charId, slotLevel);
          const used = _ssState[key] || 0;
          _ssState[key] = (pipIdx < used) ? pipIdx : Math.min(pipIdx + 1, max);
          _saveSpellSlots();
          _renderSpellSlots(charId);
        });
      });
    });
  }
  _initSpellSlots();

  // ── Status Conditions ───────────────────────────────
  const CONDITIONS_STORE_KEY = `conditions_${session.id}`;
  const D5E_CONDS = [
    { name: "blinded",       color: "#9ca3af" },
    { name: "charmed",       color: "#f472b6" },
    { name: "exhausted",     color: "#f59e0b" },
    { name: "frightened",    color: "#a78bfa" },
    { name: "grappled",      color: "#92400e" },
    { name: "incapacitated", color: "#f87171" },
    { name: "paralyzed",     color: "#dc2626" },
    { name: "poisoned",      color: "#4ade80" },
    { name: "prone",         color: "#78716c" },
    { name: "stunned",       color: "#60a5fa" },
  ];

  function saveConditions() {
    try { localStorage.setItem(CONDITIONS_STORE_KEY, JSON.stringify(State.conditions)); } catch (_) {}
  }

  function loadConditions() {
    try {
      const raw = localStorage.getItem(CONDITIONS_STORE_KEY);
      if (raw) State.conditions = JSON.parse(raw);
    } catch (_) {}
  }

  function getConds(entityId) { return State.conditions[entityId] || []; }

  function toggleCond(entityId, name) {
    const cur = getConds(entityId);
    State.conditions[entityId] = cur.includes(name)
      ? cur.filter(c => c !== name)
      : [...cur, name];
    saveConditions();
    renderCondList(entityId);
    renderInitiativeList();
  }

  function renderCondList(entityId) {
    const el = document.getElementById(`cond-list-${entityId}`);
    if (!el) return;
    const conds = getConds(entityId);
    el.innerHTML = conds.map(c => {
      const def = D5E_CONDS.find(d => d.name === c);
      const clr = def ? def.color : "#888";
      return `<span class="cond-pill" data-entity="${entityId}" data-cond="${c}"
        style="color:${clr};border-color:${clr}55;background:${clr}18;"
        title="Click to remove">${c}</span>`;
    }).join("");
    el.querySelectorAll(".cond-pill").forEach(p =>
      p.addEventListener("click", () => toggleCond(p.dataset.entity, p.dataset.cond))
    );
  }

  function renderAllCondLists() {
    const ids = [
      ...characters.map(c => c.id),
      ...State.enemies.map(e => e.id),
    ];
    ids.forEach(renderCondList);
  }

  document.querySelector(".game-sidebar")?.addEventListener("click", e => {
    const btn = e.target.closest(".cond-add-btn");
    if (!btn) return;
    e.stopPropagation();
    const entityId = btn.dataset.entity;
    const section = document.getElementById(`cond-section-${entityId}`);
    if (!section) return;
    const existing = section.querySelector(".cond-menu");
    if (existing) { existing.remove(); return; }
    document.querySelectorAll(".cond-menu").forEach(m => m.remove());
    const cur = getConds(entityId);
    const menu = document.createElement("div");
    menu.className = "cond-menu";
    menu.innerHTML = D5E_CONDS.map(def => {
      const active = cur.includes(def.name);
      return `<button class="cond-menu-opt${active ? " active" : ""}"
        data-entity="${entityId}" data-cond="${def.name}"
        style="--cond-clr:${def.color};">${def.name}</button>`;
    }).join("");
    section.appendChild(menu);
    menu.querySelectorAll(".cond-menu-opt").forEach(opt =>
      opt.addEventListener("click", ev => {
        ev.stopPropagation();
        toggleCond(opt.dataset.entity, opt.dataset.cond);
        opt.classList.toggle("active", getConds(entityId).includes(opt.dataset.cond));
      })
    );
    setTimeout(() => document.addEventListener("click", function close(ev) {
      if (!menu.contains(ev.target)) { menu.remove(); document.removeEventListener("click", close); }
    }), 0);
  });

  loadEnemies();
  loadConditions();
  // Demo convenience: auto-load the Sunken Vault cast on first open (never
  // overwrites a tracker the user has already populated, and only for the demo).
  if (campaignName === DEMO_CAMPAIGN_NAME && State.enemies.length === 0) {
    seedDemoCast();
  }
  renderEnemies();
  renderAllCondLists();

  document.getElementById("btn-load-demo-cast")?.addEventListener("click", () => {
    const added = seedDemoCast();
    showToast(
      added > 0 ? `Loaded ${added} Sunken Vault NPC${added !== 1 ? "s" : ""}.` : "Cast already loaded.",
      added > 0 ? "success" : "info",
    );
  });

  // ── Initiative tracker ──────────────────────────────
  const INITIATIVE_STORE_KEY = `initiative_${session.id}`;

  function saveInitiative() {
    try {
      localStorage.setItem(INITIATIVE_STORE_KEY, JSON.stringify({
        order: State.initiativeOrder,
        index: State.currentTurnIndex,
        round: State.round,
      }));
    } catch (_) {}
  }

  function loadInitiative() {
    try {
      const raw = localStorage.getItem(INITIATIVE_STORE_KEY);
      if (!raw) return;
      const saved = JSON.parse(raw);
      State.initiativeOrder = saved.order || [];
      State.currentTurnIndex = saved.index ?? -1;
      State.round = saved.round || 0;
      State.initiativeOrder.forEach(r => {
        if (r.isEnemy) {
          const e = State.enemies.find(e => e.name === r.name);
          if (e) r.hp = e.hp;
        }
      });
    } catch (_) {}
  }

  function renderInitiativeList() {
    const list = document.getElementById("initiative-list");
    const roundBadge = document.getElementById("round-badge");
    const roundNum   = document.getElementById("round-number");
    const nextBtn    = document.getElementById("btn-next-turn");
    const endBtn     = document.getElementById("btn-end-combat");
    const enemyPanel = document.getElementById("enemy-turn-panel");
    if (!list) return;

    if (State.initiativeOrder.length === 0) {
      list.innerHTML = `<div class="dd-muted" style="font-size:0.72rem;font-style:italic;">Press Roll All to start combat.</div>`;
      if (roundBadge) roundBadge.style.display = "none";
      if (nextBtn) nextBtn.style.display = "none";
      if (endBtn) endBtn.style.display = "none";
      if (enemyPanel) enemyPanel.style.display = "none";
      return;
    }

    if (roundBadge) { roundBadge.style.display = ""; }
    if (roundNum)   roundNum.textContent = State.round;
    // Manual Next/End-combat controls are retired when the engine drives combat.
    if (nextBtn)    nextBtn.style.display = m11EngineCombat ? "none" : "";
    if (endBtn)     endBtn.style.display = m11EngineCombat ? "none" : "";

    list.innerHTML = State.initiativeOrder.map((r, i) => {
      const isActive = i === State.currentTurnIndex;
      const dead = r.hp <= 0 ? "opacity:0.4;" : "";
      const enemyColor = r.isEnemy ? "color:var(--dd-red);" : "";
      const activeClass = isActive ? "init-active" : "";
      const modStr = r.dexMod !== 0 ? `${r.dexMod >= 0 ? "+" : ""}${r.dexMod}` : "";
      const rankEl = isActive
        ? `<span class="init-arrow"><i class="bi bi-caret-right-fill"></i></span>`
        : `<span class="init-rank">${i + 1}</span>`;
      const condPills = (r.entityId ? getConds(r.entityId) : []).map(c => {
        const def = D5E_CONDS.find(d => d.name === c);
        const clr = def ? def.color : "#888";
        return `<span style="font-size:0.5rem;padding:0 3px;border:1px solid ${clr}55;border-radius:2px;color:${clr};background:${clr}18;">${c[0].toUpperCase()}${c[1]}</span>`;
      }).join("");
      return `<div class="initiative-entry ${activeClass}" style="${dead}${enemyColor}">
        ${rankEl}
        <span class="init-name">${esc(r.name)}${r.isEnemy ? " ☠" : ""}${condPills ? `<span class="ms-1 d-inline-flex gap-1">${condPills}</span>` : ""}</span>
        <span class="init-roll">${r.total}${modStr ? ` <span class="dd-muted" style="font-size:0.6rem;">(${r.roll}${modStr})</span>` : ""}</span>
      </div>`;
    }).join("");

    const current = State.initiativeOrder[State.currentTurnIndex];
    if (current && current.isEnemy && current.hp > 0 && !m11EngineCombat) {
      if (enemyPanel) {
        enemyPanel.style.display = "";
        const nameEl   = document.getElementById("enemy-turn-name");
        const atkResEl = document.getElementById("enemy-atk-result");
        if (nameEl)   nameEl.textContent = `${current.name}'s turn`;
        if (atkResEl) { atkResEl.style.display = "none"; atkResEl.innerHTML = ""; }
      }
    } else {
      if (enemyPanel) enemyPanel.style.display = "none";
    }
  }

  document.getElementById("btn-roll-initiative")?.addEventListener("click", async () => {
    const pcResults = await Promise.all(
      characters.map(async c => {
        const dexMod = Math.floor((c.dexterity - 10) / 2);
        const r = await rollDice("1d20").catch(() => ({ total: Math.floor(Math.random()*20)+1 }));
        return { name: c.character_name, roll: r.total, dexMod, total: r.total + dexMod, hp: c.hp_current, isEnemy: false, entityId: c.id };
      })
    );
    const enemyResults = await Promise.all(
      State.enemies.filter(e => e.hp > 0).map(async e => {
        const r = await rollDice("1d20").catch(() => ({ total: Math.floor(Math.random()*20)+1 }));
        return { name: e.name, roll: r.total, dexMod: 0, total: r.total, hp: e.hp,
                 isEnemy: true, ac: e.ac ?? 12, attackBonus: e.attackBonus ?? 3, entityId: e.id };
      })
    );
    State.initiativeOrder = [...pcResults, ...enemyResults].sort((a, b) => b.total - a.total);
    State.currentTurnIndex = 0;
    State.round = 1;
    saveInitiative();
    renderInitiativeList();
    showToast("Combat started! Round 1.", "success");
  });

  document.getElementById("btn-next-turn")?.addEventListener("click", () => {
    if (State.initiativeOrder.length === 0) return;
    let next = (State.currentTurnIndex + 1) % State.initiativeOrder.length;
    let loops = 0;
    while (State.initiativeOrder[next].hp <= 0 && loops < State.initiativeOrder.length) {
      next = (next + 1) % State.initiativeOrder.length;
      loops++;
    }
    if (next <= State.currentTurnIndex) {
      State.round += 1;
      showToast(`Round ${State.round} begins!`, "info");
    }
    State.currentTurnIndex = next;
    saveInitiative();
    renderInitiativeList();
  });

  document.getElementById("btn-end-combat")?.addEventListener("click", () => {
    State.initiativeOrder = [];
    State.currentTurnIndex = -1;
    State.round = 0;
    saveInitiative();
    renderInitiativeList();
    showToast("Combat ended.", "info");
  });

  document.getElementById("btn-enemy-attack")?.addEventListener("click", async () => {
    const current = State.initiativeOrder[State.currentTurnIndex];
    if (!current || !current.isEnemy || current.hp <= 0) return;
    const alivePcs = State.initiativeOrder.filter(r => !r.isEnemy && r.hp > 0);
    if (alivePcs.length === 0) { showToast("No living PCs to attack!", "warning"); return; }
    const target = alivePcs[Math.floor(Math.random() * alivePcs.length)];
    const charObj = characters.find(c => c.character_name === target.name);
    const targetAC = charObj ? charObj.armor_class : 10;
    const atkBonus = current.attackBonus ?? 3;
    const atkRoll = await rollDice("1d20").catch(() => ({ total: Math.floor(Math.random()*20)+1 }));
    const toHit = atkRoll.total + atkBonus;
    const atkResEl = document.getElementById("enemy-atk-result");
    if (toHit >= targetAC) {
      const dmgRoll = await rollDice("1d6+2").catch(() => ({ total: Math.floor(Math.random()*6)+3 }));
      const dmg = dmgRoll.total;
      if (atkResEl) {
        atkResEl.style.display = "";
        atkResEl.innerHTML = `<span style="color:var(--dd-red);">HIT!</span> `
          + `d20(${atkRoll.total})+${atkBonus} vs AC${targetAC} → `
          + `<strong>${dmg} dmg</strong> to ${esc(target.name)}`;
      }
      if (charObj) {
        const newHp = Math.max(0, charObj.hp_current - dmg);
        try {
          const updated = await updateCharacter(charObj.id, { hp_current: newHp });
          charObj.hp_current = updated.hp_current;
          target.hp = newHp;
          const card = document.getElementById(`sidebar-char-${charObj.id}`);
          if (card) {
            const fill = card.querySelector(".hp-bar-fill");
            const text = card.querySelector(".hp-value");
            if (fill) fill.style.width = `${Math.max(0, Math.min(100, (newHp/charObj.hp_max)*100))}%`;
            if (text) text.textContent = `${newHp}/${charObj.hp_max}`;
          }
          if (newHp === 0) showToast(`${charObj.character_name} is down!`, "danger");
        } catch (e) {
          showToast(`Failed to update HP: ${e.message}`, "danger");
        }
      }
    } else {
      if (atkResEl) {
        atkResEl.style.display = "";
        atkResEl.innerHTML = `<span style="color:var(--dd-green);">MISS!</span> `
          + `d20(${atkRoll.total})+${atkBonus} vs AC${targetAC}`;
      }
    }
  });

  loadInitiative();
  renderInitiativeList();

  // ── HP quick-edit (Heal / Damage) ──────────────────
  document.querySelector(".game-sidebar")?.addEventListener("click", async e => {
    const btn = e.target.closest(".char-hp-btn");
    if (!btn) return;
    const charId = btn.dataset.charId;
    const action = btn.dataset.action;
    const char = characters.find(c => c.id === charId);
    if (!char) return;

    const card = document.getElementById(`sidebar-char-${charId}`);
    if (!card) return;

    // Toggle inline input — second click cancels
    const existing = card.querySelector(".char-hp-row");
    if (existing) { existing.remove(); return; }

    const isHeal = action === "heal";
    const row = document.createElement("div");
    row.className = "char-hp-row d-flex gap-1 mt-1";
    row.innerHTML = `
      <input type="number" class="form-control form-control-sm dd-input char-hp-input"
        min="1" max="999" value="${isHeal ? "10" : "5"}"
        style="width:4.5rem;font-size:0.72rem;padding:2px 6px;"
        placeholder="${isHeal ? "Heal" : "Dmg"}">
      <button class="btn btn-xs ${isHeal ? "dd-btn-success" : "dd-btn-danger"} char-hp-apply">
        <i class="bi bi-check"></i>
      </button>`;
    card.appendChild(row);
    const inp = row.querySelector(".char-hp-input");
    inp.focus(); inp.select();

    const applyHp = async () => {
      const amt = parseInt(inp.value);
      if (!amt || amt <= 0) { row.remove(); return; }
      row.remove();
      const newHp = isHeal
        ? Math.min(char.hp_max, char.hp_current + amt)
        : Math.max(0, char.hp_current - amt);
      try {
        const updated = await updateCharacter(charId, { hp_current: newHp });
        char.hp_current = updated.hp_current;
        const fill = card.querySelector(".hp-bar-fill");
        const text = card.querySelector(".hp-value");
        const condEl = document.getElementById(`sidebar-cond-${charId}`);
        if (fill) {
          const pct = hpPct(updated.hp_current, updated.hp_max);
          const cls = hpFillClass(updated.hp_current, updated.hp_max);
          fill.style.width = `${pct}%`;
          fill.className = `hp-bar-fill ${cls} hp-damaged`;
          setTimeout(() => fill.classList.remove("hp-damaged"), 600);
        }
        if (text) text.textContent = `${updated.hp_current} / ${updated.hp_max}`;
        if (condEl) condEl.innerHTML = conditionBadge(updated.hp_current, updated.hp_max);
        card.classList.remove("hp-flash-heal", "hp-flash-dmg");
        void card.offsetWidth;
        card.classList.add(isHeal ? "hp-flash-heal" : "hp-flash-dmg");
        setTimeout(() => card.classList.remove("hp-flash-heal", "hp-flash-dmg"), 800);

        // Sync party health mini-strip
        const pipEl = document.querySelector(`.party-health-pip[onclick*="${charId}"]`);
        if (pipEl) {
          const pipFill = pipEl.querySelector(".php-bar-fill");
          const pipHp   = pipEl.querySelector(".php-hp");
          const pct2    = hpPct(updated.hp_current, updated.hp_max);
          const cls2    = hpFillClass(updated.hp_current, updated.hp_max);
          if (pipFill) { pipFill.style.width = `${pct2}%`; pipFill.className = `php-bar-fill ${cls2}`; }
          if (pipHp)   pipHp.textContent = `${updated.hp_current}/${updated.hp_max}`;
          pipEl.title = `${char.character_name}: ${updated.hp_current}/${updated.hp_max} HP`;
        }
        showToast(`${char.character_name}: ${isHeal ? "+" : "-"}${amt} HP (${updated.hp_current}/${updated.hp_max})`, isHeal ? "success" : "warning");
      } catch (err) { showToast(err.message, "danger"); }
    };

    row.querySelector(".char-hp-apply").addEventListener("click", applyHp);
    inp.addEventListener("keydown", e => {
      if (e.key === "Enter") applyHp();
      if (e.key === "Escape") row.remove();
    });
  });

  // ── Turn Log filter chips ───────────────────────────
  _tlActiveFilter = "all";
  document.getElementById("tl-filters")?.addEventListener("click", e => {
    const chip = e.target.closest(".tl-filter");
    if (!chip) return;
    _tlActiveFilter = chip.dataset.filter || "all";
    document.querySelectorAll(".tl-filter").forEach(c => c.classList.remove("active"));
    chip.classList.add("active");
    _updateTurnLogFilter();
  });

  // ── Ability-score panel toggle ──────────────────────
  document.querySelectorAll(".char-stats-toggle").forEach(btn => {
    btn.addEventListener("click", () => {
      const charId = btn.dataset.charId;
      const panel = document.getElementById(`char-stats-${charId}`);
      if (!panel) return;
      panel.classList.toggle("open");
      btn.classList.toggle("active", panel.classList.contains("open"));
    });
  });

  // ── Character Sheet modal ───────────────────────────
  let _csCurrentCharId = null;

  function openCharSheet(charId) {
    const c = characters.find(ch => ch.id === charId);
    if (!c) return;
    _csCurrentCharId = charId;

    const pb = profBonus(c.level);
    const hpPct = c.hp_max > 0 ? Math.max(0, Math.min(100, (c.hp_current / c.hp_max) * 100)) : 0;
    const hpFillCls = hpFillClass(c.hp_current, c.hp_max);

    const avatarEl = document.getElementById("cs-avatar");
    if (avatarEl) avatarEl.innerHTML = classAvatarHtml(c.class_name, c.character_name);

    document.getElementById("cs-name").textContent = c.character_name;
    document.getElementById("cs-subtitle").textContent =
      [c.race, c.class_name, c.player_name ? `(${c.player_name})` : ""].filter(Boolean).join(" · ");
    document.getElementById("cs-level-badge").textContent = `Level ${c.level}`;

    const xpThresholds = [0,300,900,2700,6500,14000,23000,34000,48000,64000,85000,100000,120000,140000,165000,195000,225000,265000,305000,355000];
    const xpNext = xpThresholds[c.level] ?? "Max";
    const xpCurrent = c.experience ?? 0;
    document.getElementById("cs-xp").textContent =
      xpNext === "Max" ? `${xpCurrent} XP` : `${xpCurrent} / ${xpNext} XP`;

    document.getElementById("cs-hp").textContent = `${c.hp_current} / ${c.hp_max}`;
    document.getElementById("cs-ac").textContent = c.armor_class;
    document.getElementById("cs-init").textContent = modifier(c.dexterity);
    document.getElementById("cs-speed").textContent = `${c.speed}ft`;
    document.getElementById("cs-pb").textContent = `+${pb}`;

    // HP bar
    const hpBar = document.getElementById("cs-hp-bar");
    if (hpBar) {
      hpBar.style.width = `${hpPct}%`;
      hpBar.className = `hp-bar-fill ${hpFillCls}`;
    }

    const abilities = [
      { key: "STR", score: c.strength },
      { key: "DEX", score: c.dexterity },
      { key: "CON", score: c.constitution },
      { key: "INT", score: c.intelligence },
      { key: "WIS", score: c.wisdom },
      { key: "CHA", score: c.charisma },
    ];
    const abilityGrid = document.getElementById("cs-ability-grid");
    if (abilityGrid) {
      abilityGrid.innerHTML = abilities.map(a => {
        const mod = Math.floor((a.score - 10) / 2);
        const attr = mod >= 3 ? 'data-high="true"' : mod <= -2 ? 'data-low="true"' : 'data-neutral="true"';
        return `<div class="cs-ability-box" ${attr}>
          <div class="cs-ability-mod">${modifier(a.score)}</div>
          <div class="cs-ability-score">${a.score}</div>
          <div class="cs-ability-name">${a.key}</div>
        </div>`;
      }).join("");
      // Staggered pop-in per ability box
      abilityGrid.querySelectorAll(".cs-ability-box").forEach((box, i) => {
        box.style.animationDelay = `${0.08 + i * 0.05}s`;
        box.classList.add("popin");
        box.addEventListener("animationend", () => { box.classList.remove("popin"); box.style.animationDelay = ""; }, { once: true });
      });
    }

    // Saving throws (all abilities, prof bonus added to each for simplicity)
    const saveList = document.getElementById("cs-saves");
    if (saveList) {
      saveList.innerHTML = abilities.map(a => {
        const base = Math.floor((a.score - 10) / 2);
        const bonus = base + pb;
        const sign = bonus > 0 ? "positive" : bonus < 0 ? "negative" : "zero";
        return `<div class="cs-list-row">
          <span class="cs-row-ability">${a.key}</span>
          <span class="cs-row-name">${{ STR:"Strength",DEX:"Dexterity",CON:"Constitution",
            INT:"Intelligence",WIS:"Wisdom",CHA:"Charisma" }[a.key]} Save</span>
          <span class="cs-row-val" data-${sign}="true">${bonus >= 0 ? "+" : ""}${bonus}</span>
        </div>`;
      }).join("");
    }

    // Skills (5e standard skills with governing ability)
    const skills5e = [
      { name:"Acrobatics", ab:"DEX" }, { name:"Animal Handling", ab:"WIS" },
      { name:"Arcana", ab:"INT" },     { name:"Athletics", ab:"STR" },
      { name:"Deception", ab:"CHA" },  { name:"History", ab:"INT" },
      { name:"Insight", ab:"WIS" },    { name:"Intimidation", ab:"CHA" },
      { name:"Investigation", ab:"INT" },{ name:"Medicine", ab:"WIS" },
      { name:"Nature", ab:"INT" },     { name:"Perception", ab:"WIS" },
      { name:"Performance", ab:"CHA" },{ name:"Persuasion", ab:"CHA" },
      { name:"Religion", ab:"INT" },   { name:"Sleight of Hand", ab:"DEX" },
      { name:"Stealth", ab:"DEX" },    { name:"Survival", ab:"WIS" },
    ];
    const abScores = { STR:c.strength, DEX:c.dexterity, CON:c.constitution,
                       INT:c.intelligence, WIS:c.wisdom, CHA:c.charisma };
    const skillList = document.getElementById("cs-skills");
    if (skillList) {
      skillList.innerHTML = skills5e.map(sk => {
        const base = Math.floor((abScores[sk.ab] - 10) / 2);
        const sign = base > 0 ? "positive" : base < 0 ? "negative" : "zero";
        return `<div class="cs-list-row">
          <span class="cs-row-ability">${sk.ab}</span>
          <span class="cs-row-name">${sk.name}</span>
          <span class="cs-row-val" data-${sign}="true">${base >= 0 ? "+" : ""}${base}</span>
        </div>`;
      }).join("");
    }

    const bsEl = document.getElementById("cs-backstory");
    if (bsEl) bsEl.textContent = c.backstory || "No backstory recorded.";

    // Active conditions from session combat tracker (localStorage)
    const csCondsEl = document.getElementById("cs-conditions");
    if (csCondsEl) {
      const activeConds = typeof getConds === "function" ? getConds(charId) : [];
      if (activeConds.length) {
        const COND_COLORS = { unconscious:"danger", dead:"dark", poisoned:"success",
          stunned:"warning", blinded:"secondary", paralyzed:"primary",
          frightened:"info", prone:"secondary", restrained:"warning" };
        csCondsEl.innerHTML = activeConds.map(cd => {
          const col = COND_COLORS[cd] || "secondary";
          return `<span class="badge bg-${col} me-1 text-capitalize">${cd}</span>`;
        }).join("");
        csCondsEl.closest(".cs-conditions-row")?.classList.remove("d-none");
      } else {
        csCondsEl.innerHTML = '<span class="text-muted fst-italic small">None</span>';
        csCondsEl.closest(".cs-conditions-row")?.classList.remove("d-none");
      }
    }

    const editBtn = document.getElementById("btn-cs-edit");
    if (editBtn) {
      const newBtn = editBtn.cloneNode(true);
      editBtn.parentNode.replaceChild(newBtn, editBtn);
      newBtn.addEventListener("click", () => {
        bootstrap.Modal.getInstance(document.getElementById("modal-char-sheet"))?.hide();
        setTimeout(() => {
          document.getElementById("ech-pname").value     = c.player_name || "";
          document.getElementById("ech-cname").value     = c.character_name;
          document.getElementById("ech-race").value      = c.race || "";
          document.getElementById("ech-class").value     = c.class_name || "";
          document.getElementById("ech-level").value     = c.level;
          document.getElementById("ech-str").value       = c.strength;
          document.getElementById("ech-dex").value       = c.dexterity;
          document.getElementById("ech-con").value       = c.constitution;
          document.getElementById("ech-int").value       = c.intelligence;
          document.getElementById("ech-wis").value       = c.wisdom;
          document.getElementById("ech-cha").value       = c.charisma;
          document.getElementById("ech-ac").value        = c.armor_class;
          document.getElementById("ech-init").value      = c.initiative;
          document.getElementById("ech-speed").value     = c.speed;
          document.getElementById("ech-hp").value        = c.hp_max;
          document.getElementById("ech-backstory").value = c.backstory || "";
          document.getElementById("form-edit-character").classList.remove("was-validated");
          document.getElementById("modal-edit-character-label").innerHTML =
            `<i class="bi bi-person-gear me-2 dd-gold"></i>Edit — ${esc(c.character_name)}`;
          document.getElementById("btn-save-character").dataset.charId = c.id;
          bootstrap.Modal.getOrCreateInstance(document.getElementById("modal-edit-character")).show();
        }, 250);
      });
    }

    bootstrap.Modal.getOrCreateInstance(document.getElementById("modal-char-sheet")).show();
  }

  document.querySelector(".game-sidebar")?.addEventListener("click", e => {
    const btn = e.target.closest(".char-sheet-btn");
    if (!btn) return;
    e.stopPropagation();
    const charId = btn.dataset.charId;
    if (charId) openCharSheet(charId);
  });

  // ── Short Rest / Long Rest ──────────────────────────
  document.getElementById("btn-short-rest")?.addEventListener("click", function() {
    confirmInPlace(this, async () => {
      let summary = [];
      for (const c of characters) {
        if (c.hp_current <= 0) continue;
        const conMod = Math.floor((c.constitution - 10) / 2);
        const roll = Math.floor(Math.random() * 8) + 1;
        const gained = Math.max(0, roll + conMod);
        const newHp = Math.min(c.hp_max, c.hp_current + gained);
        try {
          const updated = await updateCharacter(c.id, { hp_current: newHp });
          c.hp_current = updated.hp_current;
          summary.push(`${c.character_name} +${gained} HP`);
        } catch (_) { /* silent */ }
      }
      await refreshSidebarHP(session.campaign_id);
      const feed = document.getElementById("narration-feed");
      const restEl = document.createElement("div");
      restEl.className = "narration-block";
      restEl.innerHTML = `<div class="rest-entry">
        <i class="bi bi-moon me-2"></i><strong>Short Rest</strong>
        <div class="dd-muted mt-1" style="font-size:0.8rem;">${summary.join(" · ") || "No one recovered HP."}</div>
      </div>`;
      feed.append(restEl);
      feed.scrollTop = feed.scrollHeight;
      showToast("Short Rest taken.", "info");
    });
  });

  document.getElementById("btn-long-rest")?.addEventListener("click", function() {
    confirmInPlace(this, async () => {
      for (const c of characters) {
        try {
          const updated = await updateCharacter(c.id, { hp_current: c.hp_max });
          c.hp_current = updated.hp_current;
        } catch (_) { /* silent */ }
      }
      await refreshSidebarHP(session.campaign_id);
      const feed = document.getElementById("narration-feed");
      const restEl = document.createElement("div");
      restEl.className = "narration-block";
      restEl.innerHTML = `<div class="rest-entry">
        <i class="bi bi-moon-stars me-2"></i><strong>Long Rest</strong>
        <div class="dd-muted mt-1" style="font-size:0.8rem;">All adventurers wake fully restored.</div>
      </div>`;
      feed.append(restEl);
      feed.scrollTop = feed.scrollHeight;
      // Reset all spell slots on long rest
      _ssState = {};
      _saveSpellSlots();
      document.querySelectorAll(".spell-slots-section").forEach(s => {
        const cId = s.id.replace("spell-slots-", "");
        _renderSpellSlots(cId);
      });
      showToast("Long Rest taken. Full HP & spell slots restored!", "success");
    });
  });

  // ── Turn Log FAB + drawer (narrow viewports ≤1100px) ──
  const gameLogEl = document.querySelector(".game-log");
  const toggleLogBtn = document.getElementById("btn-toggle-log");

  function _isNarrowViewport() { return window.innerWidth <= 1100; }

  function _showLogFab() {
    if (toggleLogBtn) toggleLogBtn.style.display = _isNarrowViewport() ? "" : "none";
  }
  _showLogFab();
  window.addEventListener("resize", _showLogFab);

  function _closeLogDrawer() {
    if (!gameLogEl) return;
    gameLogEl.style.display = "";
    gameLogEl.style.position = "";
    gameLogEl.style.top = "";
    gameLogEl.style.right = "";
    gameLogEl.style.bottom = "";
    gameLogEl.style.width = "";
    gameLogEl.style.zIndex = "";
    gameLogEl.style.background = "";
    gameLogEl.style.padding = "";
    gameLogEl.style.boxShadow = "";
    gameLogEl.style.borderLeft = "";
    if (toggleLogBtn) toggleLogBtn.title = "Turn Log";
    document.removeEventListener("click", _outsideLogClick);
  }

  function _outsideLogClick(e) {
    if (gameLogEl && !gameLogEl.contains(e.target) && e.target !== toggleLogBtn) {
      _closeLogDrawer();
    }
  }

  toggleLogBtn?.addEventListener("click", (e) => {
    e.stopPropagation();
    if (!gameLogEl) return;
    const isOpen = gameLogEl.style.position === "fixed";
    if (isOpen) {
      _closeLogDrawer();
    } else {
      gameLogEl.style.display = "flex";
      gameLogEl.style.position = "fixed";
      gameLogEl.style.top = "56px";
      gameLogEl.style.right = "0";
      gameLogEl.style.bottom = "0";
      gameLogEl.style.width = "min(340px, 90vw)";
      gameLogEl.style.zIndex = "1050";
      gameLogEl.style.background = "var(--dd-bg, #100c04)";
      gameLogEl.style.padding = "1rem";
      gameLogEl.style.boxShadow = "-4px 0 24px rgba(0,0,0,0.7)";
      gameLogEl.style.borderLeft = "1px solid rgba(201,168,76,0.25)";
      toggleLogBtn.title = "Close Turn Log";
      setTimeout(() => document.addEventListener("click", _outsideLogClick), 0);
    }
  });

  // ── Export Session (Markdown) ────────────────────────
  document.getElementById("btn-export-session")?.addEventListener("click", async () => {
    try {
      const turns = await getSessionTurns(session.id);
      const dateStr = session.started_at
        ? new Date(session.started_at).toLocaleDateString(undefined, { year:"numeric", month:"long", day:"numeric" })
        : new Date().toLocaleDateString();
      const partyList = characters.map(c =>
        `- **${c.character_name}** — ${[c.race, c.class_name, `Level ${c.level}`].filter(Boolean).join(", ")}`
      ).join("\n");

      const locationLabel = document.getElementById("location-text")?.textContent || "Unknown Location";
      const sessionNotes = (document.getElementById("session-notes")?.value || "").trim();
      const lines = [
        `# ${session.name}`,
        ``,
        `> **Date:** ${dateStr}  `,
        `> **Status:** ${session.status}  `,
        `> **Turns:** ${turns.length}  `,
        `> **Location:** ${locationLabel}`,
        ``,
        `## Party`,
        ``,
        partyList || "_No characters._",
        ``,
        ...(sessionNotes ? [`## DM Notes`, ``, sessionNotes, ``, `---`, ``] : [`---`, ``]),
        `## Session Log`,
        ``,
      ];

      turns.forEach(t => {
        const cName   = t.character_name || characters.find(c => c.id === t.character_id)?.character_name || "Unknown";
        const aType   = (t.action_type || "action").replace(/_/g, " ");
        const cleanDesc = (t.action_text || "").replace(/^\[Target:[^\]]+\]\s*/, "");
        lines.push(`### Turn ${t.turn_number + 1} · ${cName} — ${aType}`);
        lines.push(``);
        if (cleanDesc) {
          lines.push(`*${cleanDesc}*`);
          lines.push(``);
        }
        if (t.narration) {
          lines.push(t.narration);
          lines.push(``);
        }
        (t.npc_responses || []).forEach(npc => {
          const speech = npc.dialogue || npc.response || "";
          lines.push(`> **${npc.npc_name || "NPC"}:** "${speech}"`);
          lines.push(``);
        });
        lines.push(`---`);
        lines.push(``);
      });

      lines.push(
        `_Exported ${new Date().toLocaleString()} from D&D Multi-AI Agent Storytelling System_`
      );

      const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href     = url;
      a.download = `${session.name.replace(/[^\w\s-]/g, "").trim().replace(/\s+/g, "_")}.md`;
      a.click();
      URL.revokeObjectURL(url);
      showToast("Session exported as Markdown!", "success");
    } catch (err) { showToast(err.message, "danger"); }
  });

  // ── Party health strip — click to switch active character ──
  document.getElementById("party-health-strip")?.addEventListener("click", e => {
    const pip = e.target.closest(".party-health-pip");
    if (!pip) return;
    const onclickAttr = pip.getAttribute("onclick") || "";
    const m = onclickAttr.match(/openCampaignCharSheet\('([^']+)'\)/);
    if (!m) return;
    const charId = m[1];
    const charSelect = document.getElementById("action-character");
    if (charSelect && [...charSelect.options].some(o => o.value === charId)) {
      charSelect.value = charId;
      charSelect.dispatchEvent(new Event("change"));
      // Highlight the active pip
      document.querySelectorAll(".party-health-pip").forEach(p => p.classList.remove("php-active"));
      pip.classList.add("php-active");
    }
  });

  // ── Dynamic action placeholder ──────────────────────
  const actionTypeInput = document.getElementById("action-type");
  const targetGroup = document.getElementById("target-group");
  const descGroup = document.getElementById("desc-group");
  const descEl2 = document.getElementById("action-description");
  const placeholders = {
    roleplay:       "I step forward and introduce myself to the tavern keeper, asking about rumors…",
    attack_melee:   "I lunge forward with my longsword, aiming for the creature's flank…",
    attack_ranged:  "I notch an arrow, take careful aim at the distant enemy, and release…",
    cast_spell:     "I raise my hands, channel the arcane energy, and unleash a bolt of lightning…",
    skill_check:    "I scan the room carefully, searching for hidden doors or traps…",
    movement:       "I dash across the chamber, using the pillars as cover to reach the far door…",
    talk:           "I approach the guard and explain we mean no harm, offering to negotiate…",
    puzzle_answer:  "The answer is… the shadow of a sundial at noon.",
  };
  const actionComposer = document.querySelector(".action-composer");
  if (actionComposer) actionComposer.dataset.actionType = "roleplay";

  document.getElementById("action-pill-bar")?.addEventListener("click", e => {
    const pill = e.target.closest(".action-pill");
    if (!pill) return;
    document.querySelectorAll("#action-pill-bar .action-pill").forEach(p => p.classList.remove("active"));
    pill.classList.add("active");
    actionTypeInput.value = pill.dataset.type;
    if (actionComposer) actionComposer.dataset.actionType = pill.dataset.type;
    m11PopulateTargets();  // M11: target options follow the action type (exits vs entities)
    if (descEl2) {
      descEl2.placeholder = placeholders[pill.dataset.type] || placeholders.roleplay;
      descEl2.focus();
    }
  });

  // Auto-detect action type from description text
  const _autoDetectPatterns = [
    { type: "attack_melee",  re: /\b(attack|strike|hit|swing|slash|stab|thrust|punch|kick|smash|cleave|cut|lunge|bash|slam|bludgeon)\b/i },
    { type: "attack_ranged", re: /\b(shoot|fire|arrow|bolt|throw|hurl|fling|sling|volley|snipe)\b/i },
    { type: "cast_spell",    re: /\b(cast|spell|magic|fireball|lightning|heal|cure|conjure|summon|enchant|arcane|channel|invoke|hex|bless|curse)\b/i },
    { type: "skill_check",   re: /\b(check|search|investigate|perceive|stealth|sneak|persuade|deceive|intimidate|acrobatics|athletics|history|nature|arcana|insight|medicine|survival|climb|jump|swim|listen|spot|detect|examine|scan|disarm|pick|lockpick)\b/i },
    { type: "movement",      re: /\b(move|run|dash|sprint|walk|step|flee|retreat|advance|approach|rush|leap|jump|climb|swim|fly|sneak)\b/i },
    { type: "talk",          re: /\b(say|tell|ask|speak|talk|negotiate|parley|persuade|address|shout|call|greet|question|demand|threaten|plead|offer)\b/i },
    { type: "puzzle_answer", re: /\b(answer|solution|solve|riddle|the answer is|i think it|my answer)\b/i },
  ];
  function _autoDetectActionType(text) {
    const lower = text.toLowerCase();
    for (const { type, re } of _autoDetectPatterns) {
      if (re.test(lower)) return type;
    }
    return null;
  }
  let _lastUserPickedType = null;
  document.getElementById("action-pill-bar")?.addEventListener("click", () => {
    _lastUserPickedType = actionTypeInput.value;
  });
  if (descEl2) {
    descEl2.addEventListener("input", () => {
      const text = descEl2.value;
      const detected = _autoDetectActionType(text);
      if (!detected) return;
      if (_lastUserPickedType && _lastUserPickedType !== "roleplay") return;
      const currentType = actionTypeInput.value;
      if (detected === currentType) return;
      const pill = document.querySelector(`#action-pill-bar .action-pill[data-type="${detected}"]`);
      if (pill) {
        document.querySelectorAll("#action-pill-bar .action-pill").forEach(p => p.classList.remove("active"));
        pill.classList.add("active");
        actionTypeInput.value = detected;
        if (actionComposer) actionComposer.dataset.actionType = detected;
        m11PopulateTargets();  // M11: keep target options in sync with auto-detected type
        descEl2.placeholder = placeholders[detected] || placeholders.roleplay;
      }
    });
    descEl2.addEventListener("focus", () => { _lastUserPickedType = null; });
  }

  // Number key shortcuts 1–8 for action types (only when textarea not focused)
  const _pillTypes = ["roleplay","attack_melee","attack_ranged","cast_spell","skill_check","movement","talk","puzzle_answer"];
  window.addEventListener("keydown", e => {
    const tag = document.activeElement?.tagName?.toLowerCase();
    if (tag === "input" || tag === "textarea" || tag === "select") return;
    const n = parseInt(e.key, 10);
    if (n >= 1 && n <= 8) {
      const type = _pillTypes[n - 1];
      const pill = document.querySelector(`#action-pill-bar .action-pill[data-type="${type}"]`);
      if (pill) {
        pill.click();
        descEl2?.focus();
        e.preventDefault();
      }
    }
  });

  document.getElementById("dice-quick-btns").addEventListener("click", e => {
    const btn = e.target.closest(".dd-dice-quick");
    if (btn) {
      document.querySelectorAll(".dd-dice-quick").forEach(b => b.classList.remove("last-rolled", "active"));
      btn.classList.add("last-rolled", "active");
      document.getElementById("dice-expr-input").value = btn.dataset.expr;
      handleDiceRoll();
    }
  });
  document.getElementById("btn-roll-dice").addEventListener("click", handleDiceRoll);
  document.getElementById("dice-expr-input").addEventListener("keydown", e => {
    if (e.key === "Enter") handleDiceRoll();
  });

  document.getElementById("btn-submit-action").addEventListener("click", handleSubmitAction);
  const descEl = document.getElementById("action-description");
  descEl.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSubmitAction(); }
    if (e.key === "Escape") { descEl.value = ""; descEl.blur(); }
  });
  descEl.addEventListener("input", () => {
    descEl.style.height = "auto";
    descEl.style.height = Math.min(descEl.scrollHeight, 220) + "px";
    const submitBtn = document.getElementById("btn-submit-action");
    submitBtn?.classList.toggle("has-content", descEl.value.trim().length > 0);
    const countEl = document.getElementById("action-char-count");
    if (countEl) {
      const n = descEl.value.length;
      countEl.textContent = `${n} / 600`;
      countEl.classList.remove("count-warn", "count-crit");
      if (n > 570) countEl.classList.add("count-crit");
      else if (n > 480) countEl.classList.add("count-warn");
    }
  });

  // ── Narration unread badge ──────────────────────────
  const narFeed = document.getElementById("narration-feed");
  let _narScrolledUp = false;
  const _unreadBadge = document.createElement("div");
  _unreadBadge.className = "nar-unread-badge";
  _unreadBadge.innerHTML = `<i class="bi bi-arrow-down-circle-fill"></i>New narration`;
  _unreadBadge.addEventListener("click", () => {
    narFeed?.scrollTo({ top: narFeed.scrollHeight, behavior: "smooth" });
    _unreadBadge.classList.remove("visible");
    _narScrolledUp = false;
  });
  narFeed?.parentElement?.append(_unreadBadge);
  narFeed?.addEventListener("scroll", () => {
    const atBottom = narFeed.scrollHeight - narFeed.scrollTop - narFeed.clientHeight < 100;
    if (atBottom) { _narScrolledUp = false; _unreadBadge.classList.remove("visible"); }
    else _narScrolledUp = true;
  });

  // ── Active character: pip pulse + sidebar highlight ─
  const _syncActiveChar = (charId) => {
    document.querySelectorAll(".party-health-pip").forEach(p => {
      const oc = p.getAttribute("onclick") || "";
      const isActive = oc.includes(charId);
      p.classList.toggle("php-active", isActive);
      if (isActive) {
        p.classList.add("pip-pulse");
        setTimeout(() => p.classList.remove("pip-pulse"), 600);
      }
    });
    document.querySelectorAll(".character-card").forEach(card => {
      card.classList.toggle("sidebar-active", card.id === `sidebar-char-${charId}`);
    });
  };
  const charSelectEl = document.getElementById("action-character");
  charSelectEl?.addEventListener("change", e => _syncActiveChar(e.target.value));
  if (charSelectEl?.value) _syncActiveChar(charSelectEl.value);

  // ── Session header scroll shadow ────────────────────
  const sessionHeader = document.querySelector(".session-header-bar");
  narFeed?.addEventListener("scroll", () => {
    if (sessionHeader) sessionHeader.classList.toggle("scrolled", narFeed.scrollTop > 10);
  });

  // ── Session duration timer ───────────────────────────
  if (session.status === "active") {
    const timerTextEl = document.getElementById("session-timer-text");
    const sessionStart = session.started_at ? new Date(session.started_at) : new Date();
    let _sessionTimerInterval = null;
    function _tickTimer() {
      if (!timerTextEl) return;
      const elapsed = Math.floor((Date.now() - sessionStart.getTime()) / 1000);
      const h = Math.floor(elapsed / 3600);
      const m = Math.floor((elapsed % 3600) / 60);
      const s = elapsed % 60;
      timerTextEl.textContent = h > 0
        ? `${h}:${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")}`
        : `${m}:${String(s).padStart(2,"0")}`;
    }
    _tickTimer();
    _sessionTimerInterval = setInterval(_tickTimer, 1000);
    // Stop timer when session ends
    const origEndBtn = document.getElementById("btn-end-session");
    if (origEndBtn) {
      const _stopTimer = () => { if (_sessionTimerInterval) clearInterval(_sessionTimerInterval); };
      origEndBtn.addEventListener("click", _stopTimer, { once: true });
    }
  }

  // ── Nat 20 confetti flash ────────────────────────────
  function _nat20Flash() {
    const canvas = document.createElement("canvas");
    canvas.style.cssText = "position:fixed;inset:0;pointer-events:none;z-index:9999;width:100%;height:100%;";
    document.body.appendChild(canvas);
    const ctx = canvas.getContext("2d");
    canvas.width  = window.innerWidth;
    canvas.height = window.innerHeight;
    const particles = Array.from({ length: 60 }, () => ({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height * 0.4,
      vx: (Math.random() - 0.5) * 4,
      vy: Math.random() * 3 + 1,
      size: Math.random() * 8 + 4,
      color: ["#c9a84c","#e04040","#3de882","#5ba8e8","#ff9900"][Math.floor(Math.random() * 5)],
      alpha: 1,
      spin: (Math.random() - 0.5) * 0.2,
      angle: Math.random() * Math.PI * 2,
    }));
    let frame = 0;
    function draw() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      particles.forEach(p => {
        p.x += p.vx; p.y += p.vy; p.angle += p.spin;
        p.alpha = Math.max(0, 1 - frame / 80);
        ctx.save();
        ctx.globalAlpha = p.alpha;
        ctx.translate(p.x, p.y);
        ctx.rotate(p.angle);
        ctx.fillStyle = p.color;
        ctx.fillRect(-p.size / 2, -p.size / 4, p.size, p.size / 2);
        ctx.restore();
      });
      frame++;
      if (frame < 90) requestAnimationFrame(draw);
      else canvas.remove();
    }
    draw();
    showToast("⚔ NATURAL 20! ⚔", "success");
  }

  document.getElementById("btn-end-session").addEventListener("click", function() {
    confirmInPlace(this, async () => {
      const endBtn = document.getElementById("btn-end-session");
      endBtn.disabled = true;
      endBtn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span>Ending…`;
      try {
        const [endedSession, turns] = await Promise.all([
          endSession(session.id),
          getSessionTurns(session.id),
        ]);
        showToast("Session ended. Summary saved.", "success");

        const typeCounts = {};
        (turns || []).forEach(t => {
          typeCounts[t.action_type] = (typeCounts[t.action_type] || 0) + 1;
        });
        const statChips = Object.entries(typeCounts)
          .sort((a, b) => b[1] - a[1])
          .map(([type, n]) => {
            const color = ACTION_COLORS[type] || "#a88030";
            const icon  = ACTION_ICONS[type]  || "bi-circle";
            return `<span style="font-size:0.7rem;padding:0.15rem 0.5rem;border-radius:999px;
                                 background:${color}22;color:${color};border:1px solid ${color}44;">
                      <i class="bi ${icon} me-1"></i>${esc(type.replace(/_/g," "))} ×${n}
                    </span>`;
          }).join("");

        const aiSummary = endedSession?.summary;
        const summaryBlock = aiSummary
          ? `<div class="banner-summary-block mt-2"><p class="banner-summary">${esc(aiSummary)}</p></div>`
          : `<p style="opacity:0.45;font-style:italic;font-size:0.8rem;margin-bottom:0.5rem;">The chronicler's quill scratches in the darkness — the tale passes into legend.</p>`;

        const feed = document.getElementById("narration-feed");
        const summaryEl = document.createElement("div");
        summaryEl.className = "narration-block";
        summaryEl.innerHTML = `<div class="session-end-banner">
          <div class="session-end-title"><i class="bi bi-book-half me-2"></i>Session Concluded</div>
          ${summaryBlock}
          ${statChips ? `<div style="display:flex;flex-wrap:wrap;gap:0.3rem;margin:0.6rem 0;">${statChips}</div>` : ""}
          <a href="#/campaign/${session.campaign_id}" class="btn dd-btn-primary btn-sm mt-1">
            <i class="bi bi-arrow-left me-1"></i>Return to Campaign
          </a>
        </div>`;
        feed.append(summaryEl);
        feed.scrollTop = feed.scrollHeight;

        document.getElementById("btn-submit-action").disabled = true;
        document.getElementById("action-description").disabled = true;
        // Halt any AI/NPC auto-advance and retire the seat controls — the
        // session is over, so the engine must not be driven any further.
        session.status = "completed";
        document.getElementById("m11-run-ai")?.style.setProperty("display", "none");
        document.querySelectorAll(".m11-seat-toggle").forEach(b => { b.disabled = true; });
      } catch (e) {
        endBtn.disabled = false;
        endBtn.innerHTML = `<i class="bi bi-stop-fill me-1"></i>End Session`;
        showToast(e.message, "danger");
      }
    });
  });

  const _diceHistory = [];

  function _renderDiceHistory() {
    const histEl = document.getElementById("dice-history");
    if (!histEl || _diceHistory.length === 0) return;
    histEl.innerHTML = _diceHistory.map((h, i) => {
      const isNat20 = h.nat20;
      const isLow   = h.low;
      const color = isNat20 ? "var(--dd-gold-bright)" : isLow ? "var(--dd-red)" : "var(--dd-text-muted)";
      const badge = isNat20 ? `<span style="font-size:0.55rem;background:rgba(212,170,80,0.15);color:var(--dd-gold);border-radius:3px;padding:0 3px;margin-left:3px;">20!</span>` : "";
      return `<div class="dice-hist-row${i === 0 ? " dice-hist-new" : ""}">
        <span class="dice-hist-expr">${esc(h.expr)}</span>
        <span class="dice-hist-val" style="color:${color};">${h.total}${badge}</span>
      </div>`;
    }).join("");
  }

  async function handleDiceRoll() {
    const expr = document.getElementById("dice-expr-input").value.trim() || "1d20";
    const display = document.getElementById("dice-result-display");
    const breakdown = document.getElementById("dice-breakdown");
    breakdown.textContent = "";

    // Cycle through random numbers while waiting for the API
    let cycleNum = 1;
    display.classList.add("dice-cycling");
    display.textContent = cycleNum;
    const cycleInterval = setInterval(() => {
      cycleNum = Math.floor(Math.random() * 20) + 1;
      display.textContent = cycleNum;
    }, 90);

    const start = Date.now();
    try {
      const r = await rollDice(expr);
      const elapsed = Date.now() - start;
      await new Promise(resolve => setTimeout(resolve, Math.max(0, 600 - elapsed)));
      clearInterval(cycleInterval);
      display.classList.remove("dice-cycling");
      display.classList.add("die-spinning", "dice-new");
      setTimeout(() => display.classList.remove("die-spinning", "dice-new"), 500);
      display.textContent = r.total;
      const dieMatch = expr.match(/(\d+)d(\d+)/i);
      const isNat20 = dieMatch && parseInt(dieMatch[1],10) === 1 && r.rolls[0] === parseInt(dieMatch[2],10);
      const isLow   = dieMatch && parseInt(dieMatch[1],10) === 1 && r.rolls[0] === 1;
      display.dataset.nat20 = isNat20 ? "true" : "";
      display.dataset.low   = isLow   ? "true" : "";
      if (isNat20) _nat20Flash();
      const rollLevel = (() => {
        if (!dieMatch) return "";
        const sides = parseInt(dieMatch[2], 10);
        const maxPossible = parseInt(dieMatch[1], 10) * sides + (r.modifier || 0);
        const minPossible = parseInt(dieMatch[1], 10) + (r.modifier || 0);
        const range = maxPossible - minPossible;
        if (range <= 0) return "";
        const pct = (r.total - minPossible) / range;
        if (isNat20 || r.total === maxPossible) return "max";
        if (pct >= 0.75) return "high";
        if (isLow || pct <= 0.25) return "low";
        return "";
      })();
      display.dataset.rollLevel = rollLevel;
      flashDiceResult();
      breakdown.textContent = `[${r.rolls.join(", ")}]${r.modifier !== 0 ? ` ${r.modifier >= 0 ? "+" : ""}${r.modifier}` : ""}`;
      _diceHistory.unshift({ expr, total: r.total, nat20: isNat20, low: isLow });
      if (_diceHistory.length > 8) _diceHistory.pop();
      _renderDiceHistory();
    } catch (e) {
      clearInterval(cycleInterval);
      display.classList.remove("dice-cycling");
      display.textContent = "—";
      breakdown.textContent = e.message;
    }
  }

  async function handleSubmitAction() {
    const charId  = document.getElementById("action-character").value;
    const type    = document.getElementById("action-type").value;
    const descEl2 = document.getElementById("action-description");
    const desc    = descEl2.value.trim();
    // M11: the target is a real ENGINE id chosen from the scene dropdown
    //      (entity for Melee/Ranged/Talk, destination location for Move).
    const targetGroupEl = document.getElementById("target-group");
    const targetSel = document.getElementById("action-target");
    const targetActive = targetGroupEl && targetGroupEl.style.display !== "none" && targetSel;
    let targetId = targetActive ? (targetSel.value || null) : null;
    const targetName = targetActive && targetSel.selectedOptions[0]
      ? targetSel.selectedOptions[0].textContent : "";
    // skill_check packs "id::purpose" in the option value + rolls a chosen stat.
    let skillStat = null, skillPurpose = null;
    if (type === "skill_check" && targetId && targetId.includes("::")) {
      const [tid, p] = targetId.split("::");
      targetId = tid;
      skillPurpose = p;
      skillStat = document.getElementById("action-stat")?.value || "wis_mod";
    }
    const _needsTarget = type.startsWith("attack_") || type === "talk"
      || type === "movement" || type === "move" || type === "skill_check";

    if (!charId) { showToast("Select a character.", "warning"); return; }
    if (!desc)   { showToast("Describe the action.", "warning"); return; }
    if (_needsTarget && !targetId) {
      showToast(type === "movement" || type === "move"
        ? "Pick a destination from the exits." : "Pick a target from the room.", "warning");
      return;
    }

    const fullDesc = desc;  // M11: target is a real id now, not free text in the prose

    const btn = document.getElementById("btn-submit-action");
    btn.disabled = true;
    btn.classList.add("submitting");
    btn.innerHTML = `<span class="spinner-border spinner-border-sm me-1" style="border-color:rgba(212,170,80,0.3);border-top-color:var(--dd-gold);"></span>DM…`;

    const feed = document.getElementById("narration-feed");
    const diceExprInput = document.getElementById("dice-expr-input");
    const diceExpr = (!type.startsWith("attack_") && diceExprInput?.value.trim())
      ? diceExprInput.value.trim() : null;

    let resultData = null;
    let streamDiv = null;
    let streamTextNode = null;
    let streamCursor = null;
    let fullNarration = "";
    let _tlEntry = null;

    const _emptyEl = document.getElementById("narration-empty");
    if (_emptyEl && _emptyEl.style.display !== "none") {
      _emptyEl.style.transition = "opacity 0.4s";
      _emptyEl.style.opacity = "0";
      setTimeout(() => { _emptyEl.style.display = "none"; }, 400);
    }

    const thinkingEl = document.createElement("div");
    thinkingEl.className = "narration-block narration-thinking";
    thinkingEl.innerHTML = `
      <div class="dm-thinking">
        <div class="dm-thinking-dots"><span></span><span></span><span></span></div>
        <span class="dm-thinking-label">The Dungeon Master consults the ancient scrolls…</span>
      </div>`;
    feed.append(thinkingEl);
    feed.scrollTop = feed.scrollHeight;

    try {
      await submitActionStream(session.id, {
        character_id: charId,
        action_type: type,
        description: fullDesc,
        target_id: targetId,            // M11: real engine id (entity or destination)
        dice_expression: diceExpr,
        location: null,                 // M11: location is now an engine read-out, not input
        stat: skillStat,                // M11: skill_check — ability modifier to roll
        purpose: skillPurpose,          // M11: skill_check — DC lookup key
        enemies: State.enemies.map(e => ({
          name: e.name,
          hp: e.hp ?? null,
          max_hp: e.maxHp ?? null,
          ac: e.ac ?? null,
          persona: e.persona || null,
          disposition: e.disposition || null,
          goals: e.goals || null,
          secret: e.secret || null,
          negotiation_levers: e.negotiation_levers || null,
          conditions: getConds(e.id).length ? getConds(e.id) : null,
        })),
      }, (chunk) => {

        if (chunk.type === "error") {
          thinkingEl.remove();
          showToast(chunk.message || "Action failed.", "danger");
          return;
        }

        if (chunk.type === "result") {
          resultData = chunk;
          thinkingEl.remove();

          const _combatTypes = new Set(["attack_melee","attack_ranged","cast_spell","cast"]);
          if (_combatTypes.has(chunk.action_type)) applySessionMode("combat");

          descEl2.value = "";
          descEl2.style.height = "";
          const tcEl = document.getElementById("turn-counter");
          if (tcEl) {
            tcEl.textContent = chunk.turn_number + 1;
            tcEl.classList.remove("turn-bump");
            void tcEl.offsetWidth;
            tcEl.classList.add("turn-bump");
            setTimeout(() => tcEl.classList.remove("turn-bump"), 400);
          }

          const actionEl = document.createElement("div");
          actionEl.className = "narration-block nar-enter";
          actionEl.innerHTML = `<div class="narration-action" data-type="${esc(type)}">
            <strong>${esc(charName(charId))}</strong>
            — <em>${esc(fullDesc)}</em>
          </div>`;
          feed.append(actionEl);

          if (chunk.attack_result || chunk.dice_results?.length) {
            const resultEl = document.createElement("div");
            resultEl.className = "narration-block nar-enter";
            let chips = "";
            if (chunk.attack_result) {
              const ar = chunk.attack_result;
              const cls = ar.is_critical ? "crit" : ar.is_hit ? "hit" : "miss";
              const label = ar.is_critical ? "CRIT" : ar.is_hit ? "HIT" : "MISS";
              chips += `<span class="dice-chip ${cls}">${label} · roll ${ar.total_roll} vs AC</span>`;
              if (ar.is_hit) chips += `<span class="dice-chip">${ar.damage} dmg</span>`;
            }
            (chunk.dice_results || []).forEach(dr => {
              chips += `<span class="dice-chip">${esc(dr.expression)}: ${dr.total}</span>`;
            });
            // Skill check PASS/FAIL chip — engine-derived (real DC + roll), not
            // a guess parsed from the description.
            if (chunk.check_result) {
              chips += m11CheckChip(chunk.check_result);
            }
            if (chips) {
              resultEl.innerHTML = `<div class="narration-result">${chips}</div>`;
              feed.append(resultEl);
            }
          }

          const narBlockEl = document.createElement("div");
          narBlockEl.className = "narration-block nar-enter";
          streamDiv = document.createElement("div");
          streamDiv.className = "narration-dm narration-streaming";
          streamTextNode = document.createTextNode("");
          streamCursor = document.createElement("span");
          streamCursor.className = "dm-streaming-cursor";
          streamDiv.appendChild(streamTextNode);
          streamDiv.appendChild(streamCursor);
          narBlockEl.appendChild(streamDiv);
          feed.append(narBlockEl);

          if (chunk.state_changes && Object.keys(chunk.state_changes).length) {
            Object.entries(chunk.state_changes).forEach(([cid, change]) => {
              m11SyncPartyPip(cid, change.hp_current, change.hp_max);  // top strip
              const card = document.getElementById(`sidebar-char-${cid}`);
              if (!card) return;
              const fill = card.querySelector(".hp-bar-fill");
              const hpText = card.querySelector(".hp-value");
              const condEl = document.getElementById(`sidebar-cond-${cid}`);
              if (fill) {
                const pct = hpPct(change.hp_current, change.hp_max);
                const cls = hpFillClass(change.hp_current, change.hp_max);
                fill.style.width = `${pct}%`;
                fill.className = `hp-bar-fill ${cls} hp-damaged`;
                setTimeout(() => fill.classList.remove("hp-damaged"), 600);
              }
              if (hpText) hpText.textContent = `${change.hp_current} / ${change.hp_max}`;
              if (condEl) condEl.innerHTML = conditionBadge(change.hp_current, change.hp_max);
            });
          }

          _tlEntry = appendTurnLog(chunk, charId, fullDesc);

          if (type.startsWith("attack_") && chunk.attack_result) {
            const ar = chunk.attack_result;
            if (m11EngineCombat) {
              // Engine-backed: enemy HP comes from chunk.combat (rendered on
              // `done`). Just give the player a hit/miss toast for feedback.
              if (targetName && ar.is_hit && ar.damage > 0) {
                showToast(`${ar.damage} dmg → ${targetName}`, "info");
              } else if (targetName && !ar.is_hit) {
                showToast(`Miss! ${targetName} evades the blow.`, "secondary");
              }
            } else if (targetName) {
              const enemy = ensureEnemy(targetName);
              if (ar.is_hit && ar.damage > 0) {
                damageEnemy(enemy.id, ar.damage);
                showToast(`${ar.damage} dmg → ${targetName}`, "info");
              } else if (!ar.is_hit) {
                showToast(`Miss! ${targetName} evades the blow.`, "secondary");
              }
            } else if (ar.is_hit) {
              offerDamageToEnemy(ar.damage);
            }
            refreshSidebarHP(session.campaign_id);
          }

          feed.scrollTop = feed.scrollHeight;

        } else if (chunk.type === "token" && streamTextNode) {
          fullNarration += chunk.text;
          streamTextNode.nodeValue = fullNarration;
          feed.scrollTop = feed.scrollHeight;

        } else if (chunk.type === "done") {
          if (streamDiv) {
            streamDiv.classList.remove("narration-streaming");
            streamDiv.innerHTML = formatNarration(chunk.narration || fullNarration);
          }
          m11RenderCombat(chunk.combat);         // M11: engine-backed enemy HP / initiative / round
          if (chunk.objective_complete) m11ShowVictory();  // M11: adventure won
          m11MaybeAutoAdvance(chunk.next_turn);  // M11: run engine turns (enemy/NPC), then hand back to the human
          updateTurnLogNarration(_tlEntry, chunk.narration || fullNarration);
          if (_tlEntry && chunk.npc_responses?.length) {
            updateTurnLogNpcResponses(_tlEntry, chunk.npc_responses);
          }

          (chunk.npc_responses || []).forEach(npc => {
            const speech = (npc.response || npc.dialogue || "").trim();
            if (!speech) return;
            const npcEl = document.createElement("div");
            npcEl.className = "narration-block nar-enter";
            npcEl.innerHTML = `<div class="narration-npc">
              <div class="npc-speaker">${esc(npc.npc_name || "NPC")}</div>
              <div class="npc-speech">&ldquo;${esc(speech)}&rdquo;</div>
            </div>`;
            feed.append(npcEl);
          });

          if (resultData) {
            const divEl = document.createElement("div");
            divEl.className = "turn-divider";
            divEl.innerHTML = `<span>◆ Turn ${resultData.turn_number + 1} ◆</span>`;
            feed.append(divEl);
          }

          _markLatestNarBlock(feed);
          feed.scrollTop = feed.scrollHeight;
        }
      });

    } catch (e) {
      thinkingEl.remove();
      // If the stream dropped mid-narration, finalize the partial text cleanly
      // instead of leaving a forever-blinking cursor on an unfinished block.
      if (streamDiv) {
        streamDiv.classList.remove("narration-streaming");
        if (streamCursor) streamCursor.remove();
        if (fullNarration) streamDiv.innerHTML = formatNarration(fullNarration);
      }
      showToast(e.message, "danger");
    } finally {
      btn.disabled = false;
      btn.classList.remove("submitting");
      btn.innerHTML = `<i class="bi bi-send-fill me-1"></i>Submit`;
      btn.classList.remove("has-content");
      descEl2.focus();
    }
  }

  function charName(id) {
    const c = characters.find(c => c.id === id);
    return c ? c.character_name : id;
  }

  function appendNarration(result, charId, actionType, desc) {
    const feed = document.getElementById("narration-feed");

    const emptyEl = document.getElementById("narration-empty");
    if (emptyEl && emptyEl.style.display !== "none") {
      emptyEl.style.transition = "opacity 0.4s";
      emptyEl.style.opacity = "0";
      setTimeout(() => { emptyEl.style.display = "none"; }, 400);
    }

    const actionEl = document.createElement("div");
    actionEl.className = "narration-block nar-enter";
    actionEl.innerHTML = `<div class="narration-action" data-type="${esc(actionType)}">
      <strong>${esc(charName(charId))}</strong>
      — <em>${esc(desc)}</em>
    </div>`;
    feed.append(actionEl);

    if (result.attack_result || (result.dice_results && result.dice_results.length)) {
      const resultEl = document.createElement("div");
      resultEl.className = "narration-block nar-enter";
      let chips = "";
      if (result.attack_result) {
        const ar = result.attack_result;
        const cls = ar.is_critical ? "crit" : ar.is_hit ? "hit" : "miss";
        const label = ar.is_critical ? "CRIT" : ar.is_hit ? "HIT" : "MISS";
        chips += `<span class="dice-chip ${cls}">${label} · roll ${ar.total_roll} vs AC</span>`;
        if (ar.is_hit) chips += `<span class="dice-chip">${ar.damage} dmg</span>`;
      }
      (result.dice_results || []).forEach(dr => {
        chips += `<span class="dice-chip">${esc(dr.expression)}: ${dr.total}</span>`;
      });
      if (result.check_result) {
        chips += m11CheckChip(result.check_result);
      }
      if (chips) {
        resultEl.innerHTML = `<div class="narration-result">${chips}</div>`;
        feed.append(resultEl);
      }
    }

    if (result.narration) {
      const narEl = document.createElement("div");
      narEl.className = "narration-block nar-enter";
      narEl.innerHTML = `<div class="narration-dm">${formatNarration(result.narration)}</div>`;
      feed.append(narEl);
    }

    (result.npc_responses || []).forEach(npc => {
      const speech = (npc.response || npc.dialogue || "").trim();
      if (!speech) return;
      const npcEl = document.createElement("div");
      npcEl.className = "narration-block nar-enter";
      npcEl.innerHTML = `<div class="narration-npc">
        <div class="npc-speaker">${esc(npc.npc_name || "NPC")}</div>
        <div class="npc-speech">&ldquo;${esc(speech)}&rdquo;</div>
      </div>`;
      feed.append(npcEl);
    });

    const divEl = document.createElement("div");
    divEl.className = "turn-divider";
    divEl.innerHTML = `<span>◆ Turn ${result.turn_number + 1} ◆</span>`;
    feed.append(divEl);

    _markLatestNarBlock(feed);
    if (_narScrolledUp) {
      _unreadBadge.classList.add("visible");
    } else {
      feed.scrollTo({ top: feed.scrollHeight, behavior: "smooth" });
    }
    refreshMemoryIfOpen();
  }

  function appendTurnLog(result, charId, actionDesc = "") {
    const list = document.getElementById("turn-log-list");
    const empty = document.getElementById("turn-log-empty");
    if (empty) empty.style.display = "none";

    const entry = _buildTurnLogEntry({
      turnNumber:    result.turn_number,
      characterName: charName(charId),
      actionType:    result.action_type,
      actionText:    actionDesc,
      attackResult:  result.attack_result,
      narration:     result.narration || "",
    });
    list.prepend(entry);
    _updateTurnLogFilter();
    return entry;
  }

  function updateTurnLogNarration(entry, narration) {
    if (!entry || !narration) return;
    const detailsEl = entry.querySelector(".tl-details");
    if (!detailsEl) return;
    const narPart = detailsEl.querySelector(".tl-narration-part");
    const snippet = narration.slice(0, 180) + (narration.length > 180 ? "…" : "");
    if (narPart) {
      narPart.textContent = snippet;
    } else {
      const span = document.createElement("div");
      span.className = "mt-1 opacity-75 tl-narration-part";
      span.textContent = snippet;
      detailsEl.appendChild(span);
    }
  }

  function updateTurnLogNpcResponses(entry, npcResponses) {
    if (!entry || !npcResponses?.length) return;
    const detailsEl = entry.querySelector(".tl-details");
    if (!detailsEl) return;
    npcResponses.filter(n => (n.dialogue || n.response || "").trim()).forEach(n => {
      const speech = (n.dialogue || n.response || "").trim();
      const div = document.createElement("div");
      div.className = "mt-1 tl-npc-part";
      div.style.cssText = "font-size:0.68rem;color:var(--dd-gold);opacity:0.8;";
      div.innerHTML = `<i class="bi bi-chat-quote me-1"></i><strong>${esc(n.npc_name || "NPC")}:</strong> &ldquo;${esc(speech.slice(0, 120))}&rdquo;`;
      detailsEl.appendChild(div);
    });
  }
}
