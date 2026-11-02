/**
 * 3D CAD Studio — Main Application Controller
 * Handles user interactions, API requests, code editor syncing, and metrology updates.
 */

import { CADViewer } from './viewer.js';

let viewer = null;
let presetsData = {};
let currentCode = '';

// DOM Elements
const elApiKey = document.getElementById('apiKeyInput');
const elApiKeyBadge = document.getElementById('apiKeyBadge');
const elModelSelect = document.getElementById('modelSelect');
const elPresetSelect = document.getElementById('presetSelect');
const elBtnLoadPreset = document.getElementById('btnLoadPreset');
const elPromptInput = document.getElementById('promptInput');
const elBtnGenerate = document.getElementById('btnGenerate');
const elBtnRecalculate = document.getElementById('btnRecalculate');
const elCodeEditor = document.getElementById('codeEditor');
const elEditorFeedback = document.getElementById('editorFeedback');

const elOverlay = document.getElementById('viewerOverlay');
const elOverlayStatus = document.getElementById('overlayStatus');

// HUD & Metrology elements
const elHudDim = document.getElementById('hudDim');
const elHudVol = document.getElementById('hudVol');
const elHudTri = document.getElementById('hudTri');

const elPropDim = document.getElementById('propDim');
const elPropVol = document.getElementById('propVol');
const elPropArea = document.getElementById('propArea');
const elPropCenter = document.getElementById('propCenter');
const elMassSteel = document.getElementById('massSteel');
const elMassAlu = document.getElementById('massAlu');
const elMassPla = document.getElementById('massPla');
const elMassTitanium = document.getElementById('massTitanium');

const elBtnDownloadStep = document.getElementById('btnDownloadStep');
const elBtnDownloadStl = document.getElementById('btnDownloadStl');

// ── Initialization ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  // 1. Initialize Three.js CAD Viewer
  viewer = new CADViewer('viewport-container');

  // 2. Load API key from localStorage if present
  const savedKey = localStorage.getItem('gemini_api_key') || '';
  if (savedKey) {
    elApiKey.value = savedKey;
  }
  updateApiKeyStatus();

  elApiKey.addEventListener('input', () => {
    const val = elApiKey.value.trim();
    if (val) {
      localStorage.setItem('gemini_api_key', val);
    } else {
      localStorage.removeItem('gemini_api_key');
    }
    updateApiKeyStatus();
  });

  // 3. Setup tabs
  setupTabs();

  // 4. Setup toolbar events
  setupToolbar();

  // 5. Fetch presets from backend & load default
  await loadPresets();

  // 6. Connect action buttons
  elBtnGenerate.addEventListener('click', onGenerateClicked);
  elBtnRecalculate.addEventListener('click', onRecalculateClicked);
  elBtnLoadPreset.addEventListener('click', () => {
    const key = elPresetSelect.value;
    if (presetsData[key]) {
      elPromptInput.value = presetsData[key].description;
      onGeneratePreset(key);
    }
  });

  // Load first preset as default demo
  const firstPreset = Object.keys(presetsData)[0];
  if (firstPreset) {
    elPresetSelect.value = firstPreset;
    elPromptInput.value = presetsData[firstPreset].description;
    onGeneratePreset(firstPreset);
  }
});

function updateApiKeyStatus() {
  const key = elApiKey.value.trim();
  if (key && !key.startsWith('your_')) {
    elApiKeyBadge.className = 'badge badge-green';
    elApiKeyBadge.textContent = '🟢 IA Gemini Active';
  } else {
    elApiKeyBadge.className = 'badge badge-purple';
    elApiKeyBadge.textContent = '⚡ Mode Démo';
  }
}

// ── Tabs Switching ──────────────────────────────────────────────────────────
function setupTabs() {
  const tabBtns = document.querySelectorAll('.tab-btn');
  tabBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      tabBtns.forEach((b) => b.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach((p) => p.classList.remove('active'));

      btn.classList.add('active');
      const targetPane = document.getElementById(btn.dataset.target);
      if (targetPane) targetPane.classList.add('active');
    });
  });
}

// ── Toolbar Controls ────────────────────────────────────────────────────────
function setupToolbar() {
  // Camera Views
  document.querySelectorAll('[data-view]').forEach((btn) => {
    btn.addEventListener('click', () => {
      viewer.setView(btn.dataset.view);
    });
  });

  // Materials
  const elMatSelect = document.getElementById('matSelect');
  elMatSelect.addEventListener('change', (e) => {
    viewer.setMaterial(e.target.value);
  });

  // Toggles
  const btnEdges = document.getElementById('btnEdges');
  btnEdges.addEventListener('click', () => {
    const active = viewer.toggleEdges();
    btnEdges.classList.toggle('active', active);
  });

  const btnBox = document.getElementById('btnBox');
  btnBox.addEventListener('click', () => {
    const active = viewer.toggleBBox();
    btnBox.classList.toggle('active', active);
  });

  const btnGrid = document.getElementById('btnGrid');
  btnGrid.addEventListener('click', () => {
    const active = viewer.toggleGrid();
    btnGrid.classList.toggle('active', active);
  });

  const btnRotate = document.getElementById('btnRotate');
  btnRotate.addEventListener('click', () => {
    const active = viewer.toggleAutoRotate();
    btnRotate.classList.toggle('active', active);
  });

  // Snapshot
  document.getElementById('btnSnapshot').addEventListener('click', () => {
    viewer.takeSnapshot('3d_cad_model.png');
  });
}

// ── Presets Loading ─────────────────────────────────────────────────────────
async function loadPresets() {
  try {
    const res = await fetch('/api/presets');
    if (res.ok) {
      presetsData = await res.json();
      elPresetSelect.innerHTML = '';
      Object.keys(presetsData).forEach((key) => {
        const opt = document.createElement('option');
        opt.value = key;
        opt.textContent = `⚡ ${key}`;
        elPresetSelect.appendChild(opt);
      });
    }
  } catch (err) {
    console.error('Failed to load presets:', err);
  }
}

// ── Generation Handlers ─────────────────────────────────────────────────────
async function onGeneratePreset(presetKey) {
  showOverlay(`Génération du modèle "${presetKey}"...`);
  try {
    const res = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        preset_name: presetKey,
      }),
    });
    const data = await res.json();
    handleGenerationResponse(data);
  } catch (err) {
    showFeedback(`Erreur: ${err.message}`, 'error');
  } finally {
    hideOverlay();
  }
}

async function onGenerateClicked() {
  const prompt = elPromptInput.value.trim();
  if (!prompt) {
    alert('Veuillez décrire la pièce mécanique à modéliser.');
    return;
  }

  showOverlay('Génération CAO paramétrique en cours...');
  elBtnGenerate.disabled = true;

  try {
    const res = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: prompt,
        api_key: elApiKey.value.trim(),
        model: elModelSelect.value,
      }),
    });

    const data = await res.json();
    handleGenerationResponse(data);
  } catch (err) {
    showFeedback(`Erreur de connexion: ${err.message}`, 'error');
  } finally {
    hideOverlay();
    elBtnGenerate.disabled = false;
  }
}

async function onRecalculateClicked() {
  const code = elCodeEditor.value.trim();
  if (!code) return;

  showOverlay('Recalcul de la géométrie 3D...');
  elBtnRecalculate.disabled = true;

  try {
    const res = await fetch('/api/recalculate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: code }),
    });

    const data = await res.json();
    handleGenerationResponse(data);
    showFeedback('✓ Géométrie 3D recalculée avec succès !', 'success');
  } catch (err) {
    showFeedback(`Erreur d'exécution: ${err.message}`, 'error');
  } finally {
    hideOverlay();
    elBtnRecalculate.disabled = false;
  }
}

function handleGenerationResponse(data) {
  if (!data.success) {
    showFeedback(`Échec: ${data.error || 'Erreur inconnue'}`, 'error');
    return;
  }

  // 1. Update Code Editor
  currentCode = data.code || '';
  elCodeEditor.value = currentCode;

  // 2. Load 3D model into Three.js
  if (data.stl_base64) {
    const stats = viewer.loadSTL(data.stl_base64);
    if (stats && elHudTri) {
      elHudTri.innerHTML = `TRI: <b>${stats.triangles.toLocaleString()}</b>`;
    }
  }

  // 3. Update Metrology Properties
  const props = data.properties || {};
  updateMetrology(props);

  // 4. Update Download Links
  if (data.step_download_url) {
    elBtnDownloadStep.href = data.step_download_url;
    elBtnDownloadStep.style.display = 'flex';
  }
  if (data.stl_download_url) {
    elBtnDownloadStl.href = data.stl_download_url;
    elBtnDownloadStl.style.display = 'flex';
  }

  showFeedback('✓ Modèle 3D compilé avec succès (B-Rep exact).', 'success');
}

function updateMetrology(props) {
  const dx = (props.bbox_x || 0).toFixed(1);
  const dy = (props.bbox_y || 0).toFixed(1);
  const dz = (props.bbox_z || 0).toFixed(1);
  const dimStr = `${dx} × ${dy} × ${dz} mm`;

  const volCm3 = (props.volume_cm3 || 0).toFixed(2);
  const areaCm2 = (props.area_cm2 || 0).toFixed(2);

  // HUD
  if (elHudDim) elHudDim.innerHTML = `DIM: <b>${dimStr}</b>`;
  if (elHudVol) elHudVol.innerHTML = `VOL: <b>${volCm3} cm³</b>`;

  // Metrology Cards
  if (elPropDim) elPropDim.textContent = dimStr;
  if (elPropVol) elPropVol.textContent = `${volCm3} cm³`;
  if (elPropArea) elPropArea.textContent = `${areaCm2} cm²`;

  if (elPropCenter && props.center) {
    const [cx, cy, cz] = props.center;
    elPropCenter.textContent = `(${cx.toFixed(1)}, ${cy.toFixed(1)}, ${cz.toFixed(1)})`;
  }

  // Masses
  if (elMassSteel) elMassSteel.textContent = `${(props.mass_steel_g || 0).toFixed(1)} g`;
  if (elMassAlu) elMassAlu.textContent = `${(props.mass_alu_g || 0).toFixed(1)} g`;
  if (elMassPla) elMassPla.textContent = `${(props.mass_pla_g || 0).toFixed(1)} g`;
  if (elMassTitanium) elMassTitanium.textContent = `${(props.mass_titanium_g || 0).toFixed(1)} g`;
}

function showOverlay(message) {
  elOverlayStatus.textContent = message;
  elOverlay.classList.add('active');
}

function hideOverlay() {
  elOverlay.classList.remove('active');
}

function showFeedback(msg, type = 'success') {
  elEditorFeedback.textContent = msg;
  elEditorFeedback.className = `editor-feedback ${type}`;
}
