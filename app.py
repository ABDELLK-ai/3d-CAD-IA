"""
3D CAD from Description — Streamlit Application
================================================
Transforms a natural-language part description into:
  • A 3D interactive viewer (Three.js via embedded HTML with OrbitControls)
  • Physical & geometric CAD analysis (Bounding box, volume, area, masses)
  • Live CadQuery code editor with real-time 3D recalculation
  • Downloadable STEP files (CATIA V5/V6, SolidWorks, Fusion 360 compatible)
  • Downloadable STL files for 3D printing
"""

import os
import base64
import json
import time
from datetime import datetime

# Ensure font directories for OpenCASCADE Font_FontMgr in headless Linux containers
if "CSF_FontDirectories" not in os.environ:
    for _fdir in ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype", "/usr/share/fonts"]:
        if os.path.isdir(_fdir):
            os.environ["CSF_FontDirectories"] = _fdir
            break

import streamlit as st
from dotenv import load_dotenv

from cad_generator import (
    generate_part,
    generate_part_from_code,
    get_last_used_model,
    get_part_properties,
    PRESET_EXAMPLES,
)

# ─── Config ──────────────────────────────────────────────────────────────────
load_dotenv()
st.set_page_config(
    page_title="3D CAD Studio — IA & CadQuery",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Advanced Styling ────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    code, kbd, samp, pre {
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* Studio dark gradient canvas */
    .stApp {
        background: radial-gradient(circle at 50% 0%, #111827 0%, #080c14 70%, #05070c 100%);
        color: #e6edf3;
    }

    /* Sidebar Glassmorphism */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0e1524 0%, #090d16 100%) !important;
        border-right: 1px solid rgba(88, 166, 255, 0.15) !important;
    }

    /* Main Hero Banner */
    .hero-container {
        text-align: center;
        padding: 1.5rem 1rem 0.5rem 1rem;
        position: relative;
    }
    .hero-title {
        font-size: 2.7rem;
        font-weight: 800;
        background: linear-gradient(90deg, #58a6ff 0%, #79c0ff 50%, #d2a8ff 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: -0.03em;
        margin-bottom: 0.3rem;
    }
    .hero-sub {
        color: #8b949e;
        font-size: 1.05rem;
        max-width: 780px;
        margin: 0 auto 1.2rem auto;
        line-height: 1.5;
    }

    /* Pill Badges */
    .pill-row {
        display: flex;
        justify-content: center;
        gap: 0.6rem;
        flex-wrap: wrap;
        margin-bottom: 1.5rem;
    }
    .pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 12px;
        border-radius: 999px;
        font-size: 0.76rem;
        font-weight: 600;
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        color: #c9d1d9;
    }
    .pill.pill-green {
        background: rgba(46, 160, 67, 0.15);
        border-color: rgba(46, 160, 67, 0.4);
        color: #3fb950;
    }
    .pill.pill-blue {
        background: rgba(56, 139, 253, 0.15);
        border-color: rgba(56, 139, 253, 0.4);
        color: #58a6ff;
    }
    .pill.pill-purple {
        background: rgba(163, 113, 247, 0.15);
        border-color: rgba(163, 113, 247, 0.4);
        color: #d2a8ff;
    }

    /* Cards */
    .card {
        background: rgba(17, 24, 39, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 1.25rem;
        margin-bottom: 1rem;
        backdrop-filter: blur(12px);
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
    }
    .card-title {
        font-weight: 700;
        font-size: 0.95rem;
        color: #58a6ff;
        margin-bottom: 0.7rem;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    /* Metric Cards */
    .metric-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 0.8rem;
        margin: 1rem 0;
    }
    .metric-card {
        background: rgba(14, 20, 32, 0.75);
        border: 1px solid rgba(88, 166, 255, 0.15);
        border-radius: 10px;
        padding: 0.9rem;
        text-align: center;
        backdrop-filter: blur(8px);
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .metric-card:hover {
        border-color: rgba(88, 166, 255, 0.4);
        transform: translateY(-2px);
    }
    .metric-card .val {
        font-size: 1.25rem;
        font-weight: 700;
        color: #58a6ff;
        font-family: 'JetBrains Mono', monospace;
    }
    .metric-card .lbl {
        font-size: 0.74rem;
        color: #8b949e;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-top: 0.2rem;
    }

    /* Text Inputs & Areas */
    .stTextArea textarea {
        background: #090d16 !important;
        border: 1px solid #21262d !important;
        border-radius: 10px !important;
        color: #e6edf3 !important;
        font-size: 0.95rem !important;
        line-height: 1.6 !important;
    }
    .stTextArea textarea:focus {
        border-color: #58a6ff !important;
        box-shadow: 0 0 0 3px rgba(88, 166, 255, 0.2) !important;
    }

    /* Buttons */
    .btn-ai > button {
        background: linear-gradient(90deg, #238636 0%, #2ea043 100%) !important;
        color: #ffffff !important;
        border: none !important;
        font-weight: 700 !important;
        border-radius: 9px !important;
        padding: 0.7rem 1.5rem !important;
        box-shadow: 0 0 15px rgba(46, 160, 67, 0.25) !important;
        transition: all 0.2s ease !important;
    }
    .btn-ai > button:hover {
        background: linear-gradient(90deg, #2ea043 0%, #3fb950 100%) !important;
        box-shadow: 0 0 25px rgba(46, 160, 67, 0.45) !important;
        transform: translateY(-1px) !important;
    }

    .btn-demo > button {
        background: linear-gradient(90deg, #6e40c9 0%, #8957e5 100%) !important;
        color: #ffffff !important;
        border: none !important;
        font-weight: 700 !important;
        border-radius: 9px !important;
        padding: 0.7rem 1.5rem !important;
        box-shadow: 0 0 15px rgba(137, 87, 229, 0.25) !important;
        transition: all 0.2s ease !important;
    }
    .btn-demo > button:hover {
        background: linear-gradient(90deg, #8957e5 0%, #a371f7 100%) !important;
        box-shadow: 0 0 25px rgba(163, 113, 247, 0.45) !important;
        transform: translateY(-1px) !important;
    }

    .btn-update > button {
        background: linear-gradient(90deg, #1f6feb 0%, #388bfd 100%) !important;
        color: #ffffff !important;
        border: none !important;
        font-weight: 700 !important;
        border-radius: 9px !important;
    }

    /* Step Badge */
    .step-badge {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 26px; height: 26px;
        background: linear-gradient(135deg, #58a6ff, #1f6feb);
        color: #fff;
        border-radius: 50%;
        font-weight: 700;
        font-size: 0.85rem;
        margin-right: 0.5rem;
    }

    /* Tabs Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        border-bottom: 1px solid #21262d;
    }
    .stTabs [data-baseweb="tab"] {
        background: transparent;
        border-radius: 8px 8px 0 0;
        color: #8b949e;
        padding: 8px 18px;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        color: #58a6ff !important;
        border-bottom: 2px solid #58a6ff !important;
    }

    /* Custom Scrollbars */
    ::-webkit-scrollbar { width: 7px; height: 7px; }
    ::-webkit-scrollbar-track { background: #080c14; }
    ::-webkit-scrollbar-thumb { background: #21262d; border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: #30363d; }
</style>
""", unsafe_allow_html=True)


# ─── Three.js Viewer HTML Generator ──────────────────────────────────────────
def build_threejs_viewer(stl_path: str, props: dict = None) -> str:
    """
    Generate an interactive Three.js 3D viewport embedded in HTML.
    Uses OrbitControls, STLLoader, CAD Feature Edges, ground shadows,
    material presets, view angle controls, and snapshot export.
    """
    if not os.path.exists(stl_path):
        return "<p style='color:#f85149;'>Fichier STL non trouvé.</p>"

    with open(stl_path, "rb") as f:
        stl_b64 = base64.b64encode(f.read()).decode("ascii")

    dim_info = ""
    vol_info = ""
    if props:
        dim_info = f"{props.get('bbox_x', 0)} × {props.get('bbox_y', 0)} × {props.get('bbox_z', 0)} mm"
        vol_info = f"{props.get('volume_cm3', 0)} cm³"

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>3D CAD Viewport</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; user-select:none; }}
  body {{
    background: #06090f;
    overflow: hidden;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  }}
  #canvas-container {{
    width: 100vw;
    height: 100vh;
    position: relative;
    background: radial-gradient(circle at 50% 40%, #0d1527 0%, #06090f 85%);
  }}
  canvas {{ display: block; width: 100%; height: 100%; }}

  /* Top Control Toolbar */
  .toolbar {{
    position: absolute;
    top: 12px;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    gap: 6px;
    background: rgba(10, 16, 28, 0.85);
    backdrop-filter: blur(14px);
    border: 1px solid rgba(88, 166, 255, 0.25);
    border-radius: 10px;
    padding: 6px 10px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.5);
    z-index: 10;
    align-items: center;
  }}
  .tool-btn {{
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.12);
    color: #c9d1d9;
    padding: 5px 10px;
    border-radius: 6px;
    font-size: 0.76rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.18s ease;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    white-space: nowrap;
  }}
  .tool-btn:hover {{
    background: rgba(88, 166, 255, 0.25);
    border-color: #58a6ff;
    color: #ffffff;
    transform: translateY(-1px);
  }}
  .tool-btn.active {{
    background: #1f6feb;
    border-color: #58a6ff;
    color: #ffffff;
  }}
  .tool-sep {{
    width: 1px;
    height: 20px;
    background: rgba(255,255,255,0.15);
    margin: 0 4px;
  }}

  /* Material Selector dropdown */
  .select-ctrl {{
    background: rgba(22, 27, 34, 0.95);
    border: 1px solid rgba(88, 166, 255, 0.3);
    color: #e6edf3;
    padding: 4px 8px;
    border-radius: 6px;
    font-size: 0.74rem;
    cursor: pointer;
    outline: none;
  }}

  /* Floating HUDs */
  .hud-bottom-left {{
    position: absolute;
    bottom: 12px;
    left: 12px;
    display: flex;
    gap: 8px;
    z-index: 10;
    pointer-events: none;
  }}
  .hud-badge {{
    background: rgba(10, 16, 28, 0.85);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 6px;
    padding: 4px 10px;
    color: #8b949e;
    font-size: 0.73rem;
    font-family: monospace;
  }}
  .hud-badge b {{ color: #58a6ff; }}

  .hud-bottom-right {{
    position: absolute;
    bottom: 12px;
    right: 12px;
    background: rgba(10, 16, 28, 0.8);
    backdrop-filter: blur(8px);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 6px;
    padding: 4px 10px;
    color: #8b949e;
    font-size: 0.72rem;
    pointer-events: none;
  }}
</style>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/STLLoader.js"></script>
</head>
<body>
<div id="canvas-container">
  <!-- Toolbar -->
  <div class="toolbar">
    <!-- Camera Views -->
    <button class="tool-btn" onclick="setView('iso')" title="Vue Isométrique 3D">📐 Iso</button>
    <button class="tool-btn" onclick="setView('top')" title="Vue de dessus">🔝 Dessus</button>
    <button class="tool-btn" onclick="setView('front')" title="Vue de face">🔲 Face</button>
    <button class="tool-btn" onclick="setView('right')" title="Vue de droite">➡️ Droite</button>
    <button class="tool-btn" onclick="setView('reset')" title="Recentrer la caméra">🔄 Reset</button>

    <div class="tool-sep"></div>

    <!-- Materials -->
    <select class="select-ctrl" id="matSelect" onchange="changeMaterial(this.value)">
      <option value="cad_blue">🔷 Bleu CAO</option>
      <option value="steel">⚪ Acier Inox</option>
      <option value="brass">🟡 Laiton / Bronze</option>
      <option value="dark">🪨 Polymère Sombre</option>
      <option value="orange">🟠 Orange Atelier</option>
    </select>

    <div class="tool-sep"></div>

    <!-- Display Toggles -->
    <button class="tool-btn active" id="btnEdges" onclick="toggleEdges()" title="Afficher/Masquer arêtes de découpe">Arêtes</button>
    <button class="tool-btn" id="btnBox" onclick="toggleBBox()" title="Afficher/Masquer la boîte englobante 3D">Boîte</button>
    <button class="tool-btn active" id="btnGrid" onclick="toggleGrid()" title="Afficher/Masquer la grille de sol">Grille</button>
    <button class="tool-btn" id="btnRotate" onclick="toggleAutoRotate()" title="Activer/Désactiver rotation automatique">🔄 Auto</button>

    <div class="tool-sep"></div>

    <!-- Snapshot export -->
    <button class="tool-btn" onclick="takeSnapshot()" title="Télécharger un rendu PNG">📸 Capture</button>
  </div>

  <!-- Bottom HUD -->
  <div class="hud-bottom-left">
    <div class="hud-badge">DIM: <b>{dim_info}</b></div>
    <div class="hud-badge">VOL: <b>{vol_info}</b></div>
    <div class="hud-badge" id="polyBadge">TRI: <b>—</b></div>
  </div>

  <div class="hud-bottom-right">
    🖱 <b>Clic G</b>: Rotation · <b>Clic D / Maj+G</b>: Déplacement · <b>Molette</b>: Zoom
  </div>
</div>

<script>
// ── Scene Setup ─────────────────────────────────────────────────────────────
const container = document.getElementById('canvas-container');
const scene = new THREE.Scene();

const W = container.clientWidth || window.innerWidth;
const H = container.clientHeight || window.innerHeight;

const camera = new THREE.PerspectiveCamera(40, W / H, 0.1, 10000);
const renderer = new THREE.WebGLRenderer({{ antialias: true, alpha: true, preserveDrawingBuffer: true }});
renderer.setSize(W, H);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
container.appendChild(renderer.domElement);

const controls = new THREE.OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.06;
controls.screenSpacePanning = true;

// ── Lighting Setup ──────────────────────────────────────────────────────────
const ambientLight = new THREE.HemisphereLight(0xffffff, 0x1a2333, 0.6);
scene.add(ambientLight);

const mainLight = new THREE.DirectionalLight(0xffffff, 0.9);
mainLight.position.set(150, 250, 180);
mainLight.castShadow = true;
scene.add(mainLight);

const fillLight = new THREE.DirectionalLight(0x79c0ff, 0.4);
fillLight.position.set(-150, -50, -150);
scene.add(fillLight);

const rimLight = new THREE.DirectionalLight(0xffffff, 0.3);
rimLight.position.set(0, 200, -200);
scene.add(rimLight);

// ── Materials Library ───────────────────────────────────────────────────────
const materials = {{
  cad_blue: new THREE.MeshStandardMaterial({{
    color: 0x388bfd,
    metalness: 0.25,
    roughness: 0.28,
    side: THREE.DoubleSide
  }}),
  steel: new THREE.MeshStandardMaterial({{
    color: 0xd0d7de,
    metalness: 0.85,
    roughness: 0.18,
    side: THREE.DoubleSide
  }}),
  brass: new THREE.MeshStandardMaterial({{
    color: 0xe3b341,
    metalness: 0.72,
    roughness: 0.32,
    side: THREE.DoubleSide
  }}),
  dark: new THREE.MeshStandardMaterial({{
    color: 0x21262d,
    metalness: 0.35,
    roughness: 0.45,
    side: THREE.DoubleSide
  }}),
  orange: new THREE.MeshStandardMaterial({{
    color: 0xf0883e,
    metalness: 0.2,
    roughness: 0.35,
    side: THREE.DoubleSide
  }})
}};

let currentMaterial = materials.cad_blue;
let mesh = null;
let edgeLines = null;
let bboxHelper = null;
let grid = null;
let maxDim = 100;
let heightDim = 50;

// ── Load STL from Base64 ────────────────────────────────────────────────────
try {{
  const b64 = "{stl_b64}";
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {{
    bytes[i] = binary.charCodeAt(i);
  }}

  const loader = new THREE.STLLoader();
  const geometry = loader.parse(bytes.buffer);
  geometry.computeVertexNormals();
  geometry.center();

  // Bounding measurements
  geometry.computeBoundingBox();
  const bbox = geometry.boundingBox;
  const dx = bbox.max.x - bbox.min.x;
  const dy = bbox.max.y - bbox.min.y;
  const dz = bbox.max.z - bbox.min.z;
  maxDim = Math.max(dx, dy, dz);

  // Mesh creation
  mesh = new THREE.Mesh(geometry, currentMaterial);
  mesh.castShadow = true;
  mesh.receiveShadow = true;

  // CadQuery has Z-up. Rotate -90° around X so CAD Z becomes Three.js Y (up)!
  mesh.rotation.x = -Math.PI / 2;
  scene.add(mesh);

  // Mechanical feature edges (EdgesGeometry)
  const edgeGeo = new THREE.EdgesGeometry(geometry, 28);
  const edgeMat = new THREE.LineBasicMaterial({{ color: 0x091427, linewidth: 1.2 }});
  edgeLines = new THREE.LineSegments(edgeGeo, edgeMat);
  mesh.add(edgeLines);

  // Bounding box helper
  bboxHelper = new THREE.BoxHelper(mesh, 0x58a6ff);
  bboxHelper.visible = false;
  scene.add(bboxHelper);

  // Grid placed right under the bottom of the part
  // After mesh.rotation.x = -PI/2, CAD Z becomes Three.js Y
  heightDim = dz;
  const gridY = -dz / 2 - (maxDim * 0.005);
  grid = new THREE.GridHelper(maxDim * 2.5, 24, 0x30363d, 0x161b22);
  grid.position.y = gridY;
  scene.add(grid);

  // Initial camera position (Isometric view)
  const d = maxDim * 1.9;
  camera.position.set(d * 0.85, d * 0.75, d * 0.95);
  controls.target.set(0, 0, 0);
  controls.update();

  // Poly count update
  const triCount = geometry.attributes.position.count / 3;
  document.getElementById('polyBadge').innerHTML = "TRI: <b>" + Math.round(triCount).toLocaleString() + "</b>";

}} catch (err) {{
  console.error("Error loading STL in Three.js:", err);
}}

// ── Viewport Control Functions ──────────────────────────────────────────────
function setView(view) {{
  controls.autoRotate = false;
  document.getElementById('btnRotate').classList.remove('active');
  const d = maxDim * 2.0;

  if (view === 'iso') {{
    camera.position.set(d * 0.85, d * 0.75, d * 0.95);
  }} else if (view === 'top') {{
    camera.position.set(0, d * 1.6, 0.001);
  }} else if (view === 'front') {{
    camera.position.set(0, 0, d * 1.6);
  }} else if (view === 'right') {{
    camera.position.set(d * 1.6, 0, 0);
  }} else if (view === 'reset') {{
    camera.position.set(d * 0.85, d * 0.75, d * 0.95);
  }}
  controls.target.set(0, 0, 0);
  controls.update();
}}

function changeMaterial(name) {{
  if (materials[name] && mesh) {{
    currentMaterial = materials[name];
    mesh.material = currentMaterial;
  }}
}}

function toggleEdges() {{
  if (edgeLines) {{
    edgeLines.visible = !edgeLines.visible;
    document.getElementById('btnEdges').classList.toggle('active', edgeLines.visible);
  }}
}}

function toggleBBox() {{
  if (bboxHelper) {{
    bboxHelper.visible = !bboxHelper.visible;
    document.getElementById('btnBox').classList.toggle('active', bboxHelper.visible);
  }}
}}

function toggleGrid() {{
  if (grid) {{
    grid.visible = !grid.visible;
    document.getElementById('btnGrid').classList.toggle('active', grid.visible);
  }}
}}

function toggleAutoRotate() {{
  controls.autoRotate = !controls.autoRotate;
  controls.autoRotateSpeed = 2.0;
  document.getElementById('btnRotate').classList.toggle('active', controls.autoRotate);
}}

function takeSnapshot() {{
  renderer.render(scene, camera);
  const dataURL = renderer.domElement.toDataURL('image/png');
  const a = document.createElement('a');
  a.href = dataURL;
  a.download = 'rendu_3d_cad.png';
  a.click();
}}

// ── Animation Loop & Resize ─────────────────────────────────────────────────
function animate() {{
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}}
animate();

window.addEventListener('resize', () => {{
  const nW = container.clientWidth || window.innerWidth;
  const nH = container.clientHeight || window.innerHeight;
  camera.aspect = nW / nH;
  camera.updateProjectionMatrix();
  renderer.setSize(nW, nH);
}});
</script>
</body>
</html>"""
    return html


# ─── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style='text-align:center; padding: 0.8rem 0 0.5rem;'>
        <div style='font-size:2.8rem;'>⚙️</div>
        <h2 style='color:#58a6ff; margin:0.2rem 0 0; font-size:1.45rem; font-weight:800;'>3D CAD Studio</h2>
        <p style='color:#8b949e; font-size:0.8rem;'>IA Gemini → CadQuery → STEP / STL</p>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    # API Configuration
    st.markdown("### 🔑 Configuration API")
    default_env_key = os.getenv("GEMINI_API_KEY", "")
    if not default_env_key and hasattr(st, "secrets"):
        try:
            default_env_key = st.secrets.get("GEMINI_API_KEY", "")
        except Exception:
            pass
    if "your_" in default_env_key.lower():
        default_env_key = ""

    api_key_input = st.text_input(
        "Clé API Google Gemini",
        value=default_env_key,
        type="password",
        help="Clé gratuite sur https://aistudio.google.com/ — Permet la génération IA de n'importe quelle géométrie.",
        placeholder="AIzaSy...",
    )

    is_key_active = bool(api_key_input and not api_key_input.startswith("your_"))
    if is_key_active:
        st.markdown('<span class="pill pill-green">🟢 Clé API Détectée (IA Active)</span>', unsafe_allow_html=True)
    else:
        st.markdown(
            '<span class="pill pill-purple">⚡ Mode Démo Disponible (Sans clé)</span>',
            unsafe_allow_html=True,
        )
        st.caption(
            "💡 [Obtenir une clé API gratuite](https://aistudio.google.com/) en 30 secondes."
        )

    # Model choice
    model_choice = st.selectbox(
        "Moteur IA",
        [
            "Auto (Recommandé - Détection dynamique)",
            "gemini-1.5-flash (Ultra rapide ~3s)",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
            "gemini-2.5-flash",
            "gemini-1.5-flash-8b",
            "gemini-1.5-pro",
        ],
        help="Auto sélectionne le modèle le plus rapide et robuste disponible avec votre quota.",
    )
    selected_model = None
    if not model_choice.startswith("Auto"):
        selected_model = model_choice.split()[0].strip()

    st.divider()

    # Presets Library
    st.markdown("### 📚 Bibliothèque d'Exemples")
    preset_names = ["— Choisir un modèle prêt à l'emploi —"] + list(PRESET_EXAMPLES.keys())
    selected_preset = st.selectbox(
        "Charger un exemple mécanique",
        preset_names,
        help="Charge une description technique validée dans l'éditeur.",
    )

    st.divider()

    # Software compatibility quick info
    st.markdown("""
    <div style='color:#8b949e; font-size:0.78rem; line-height:1.7;'>
    <b style='color:#58a6ff;'>Export CAO Industriel</b><br>
    • <b>STEP (.step / .stp)</b> : B-Rep exact pour CATIA V5/V6, SolidWorks, Fusion 360, FreeCAD<br>
    • <b>STL (.stl)</b> : Maillage triangulaire pour impression 3D (Cura, Bambu, Prusa)<br>
    • <b>Python (.py)</b> : Code CadQuery 100% paramétrique et reproductible<br><br>
    <b style='color:#58a6ff;'>Noyau Géométrique</b><br>
    • OpenCASCADE Technology (OCCT 7.8 via CadQuery 2.4)
    </div>
    """, unsafe_allow_html=True)


# ─── Main Content ─────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero-container">
    <h1 class="hero-title">⚙️ 3D CAD Studio</h1>
    <p class="hero-sub">
        Transformez une description textuelle en pièce mécanique 3D paramétrique exacte (STEP & STL)
        avec <b>Google Gemini AI</b> et le moteur <b>CadQuery (OpenCASCADE)</b>.
    </p>
    <div class="pill-row">
        <span class="pill pill-blue">🤖 Google Gemini AI</span>
        <span class="pill pill-green">⚙️ OpenCASCADE B-Rep</span>
        <span class="pill pill-purple">📥 Export STEP AP203/AP214</span>
        <span class="pill">🖨️ Export STL 3D Print</span>
    </div>
</div>
""", unsafe_allow_html=True)

# ─── Input & Action Section ───────────────────────────────────────────────────
col_input, col_tips = st.columns([2, 1])

# Preset text loading logic
loaded_text = ""
if selected_preset != "— Choisir un modèle prêt à l'emploi —":
    loaded_text = PRESET_EXAMPLES[selected_preset]["description"]

with col_input:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown('<span class="step-badge">1</span> <b>Description de la pièce mécanique</b>', unsafe_allow_html=True)

    desc_input = st.text_area(
        label="Description de la pièce",
        value=loaded_text,
        height=160,
        placeholder=(
            "Exemple : Une plaque rectangulaire en acier 120×80×15mm avec 4 trous de 10mm aux coins "
            "à 10mm des bords, un alésage central de 30mm et des chanfreins de 2mm sur les arêtes supérieures..."
        ),
        label_visibility="collapsed",
    )

    # Action Buttons
    c_btn1, c_btn2 = st.columns(2)
    with c_btn1:
        st.markdown('<div class="btn-ai">', unsafe_allow_html=True)
        generate_ai_clicked = st.button("🚀 Générer avec l'IA Gemini", use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with c_btn2:
        st.markdown('<div class="btn-demo">', unsafe_allow_html=True)
        demo_clicked = st.button("⚡ Mode Démo (Sans clé API)", use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)

with col_tips:
    st.markdown("""
    <div class="card" style="height: 100%;">
        <div class="card-title">💡 Conseils de conception</div>
        <ul style="color:#8b949e; font-size:0.83rem; line-height:1.75; padding-left:1.1rem; margin-bottom:0;">
            <li>Précisez les <b>dimensions en millimètres</b> (ex: <code>100x60x15mm</code>)</li>
            <li>Définissez la <b>forme primaire</b> (boîte, cylindre, profil en L, bride...)</li>
            <li>Listez les <b>opérations</b> (perçages, alésages, chanfreins, congés)</li>
            <li>Indiquez les <b>positions relatives</b> (entraxes, distance aux bords)</li>
            <li>Français 🇫🇷 et Anglais 🇬🇧 acceptés</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)


# ─── Execution Pipeline ───────────────────────────────────────────────────────
out_dir = os.path.join(os.path.dirname(__file__), "output")
step_path = os.path.join(out_dir, "piece.step")
stl_path = os.path.join(out_dir, "piece.stl")

trigger_generation = False
force_demo_mode = False

if generate_ai_clicked:
    if not is_key_active:
        st.warning(
            "⚠️ Aucune clé API Gemini configurée dans la barre latérale. "
            "Génération basculée automatiquement en **Mode Démo local** !"
        )
        force_demo_mode = True
        trigger_generation = True
    elif not desc_input.strip():
        st.error("⚠️ Veuillez décrire une pièce mécanique avant de lancer la génération.")
    else:
        force_demo_mode = False
        trigger_generation = True

elif demo_clicked:
    force_demo_mode = True
    trigger_generation = True
    if not desc_input.strip():
        desc_input = "Plaque percée"

if trigger_generation:
    spinner_msg = "⚡ Génération de la pièce en Mode Démo…" if force_demo_mode else "🤖 Gemini analyse la description et génère le code CadQuery…"
    with st.spinner(spinner_msg):
        try:
            start_t = time.time()
            code, step_p, props = generate_part(
                description=desc_input,
                api_key=api_key_input,
                step_output_path=step_path,
                stl_output_path=stl_path,
                model_name=selected_model,
                force_demo=force_demo_mode,
            )
            duration = time.time() - start_t
            used_model = get_last_used_model()

            st.session_state["cq_code"] = code
            st.session_state["step_path"] = step_p
            st.session_state["stl_path"] = stl_path
            st.session_state["used_model"] = used_model
            st.session_state["props"] = props
            st.session_state["part_description"] = desc_input
            st.session_state["generated"] = True

            # Save to session history
            if "history" not in st.session_state:
                st.session_state["history"] = []
            st.session_state["history"].append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "desc": desc_input[:60] + ("..." if len(desc_input) > 60 else ""),
                "model": used_model,
                "bbox": f"{props.get('bbox_x', 0)}×{props.get('bbox_y', 0)}×{props.get('bbox_z', 0)} mm",
                "vol": f"{props.get('volume_cm3', 0)} cm³",
                "code": code,
                "props": props,
            })

            st.success(f"✅ Pièce 3D générée avec succès en {duration:.1f}s ! (Moteur : {used_model})")

        except Exception as exc:
            st.error(f"❌ Erreur lors de la modélisation : {exc}")
            st.session_state["generated"] = False


# ─── Results Dashboard ────────────────────────────────────────────────────────
if st.session_state.get("generated") and os.path.exists(stl_path):
    st.divider()

    tab_viewer, tab_code, tab_export, tab_history = st.tabs([
        "🔭 Viewer 3D Interactif",
        "📄 Code CadQuery & Éditeur Live",
        "⬇️ Export CAO & Guide",
        "📜 Historique de Session",
    ])

    props = st.session_state.get("props", {})

    # ── TAB 1 : 3D Interactive Viewport ───────────────────────────────────────
    with tab_viewer:
        st.markdown('<span class="step-badge">2</span> <b>Visualisation 3D temps réel</b>', unsafe_allow_html=True)
        st.caption("Contrôles : Orbite (Clic G) · Pan (Clic D / Maj+G) · Zoom (Molette) · Barres d'outils intégrées")

        viewer_html = build_threejs_viewer(stl_path, props)
        st.components.v1.html(viewer_html, height=580, scrolling=False)

        # Physical and Geometric Analysis Cards
        st.markdown("#### 📊 Propriétés Physiques & Géométriques (OpenCASCADE B-Rep)")
        st.markdown(f"""
        <div class="metric-grid">
            <div class="metric-card">
                <div class="val">{props.get('bbox_x', 0)} × {props.get('bbox_y', 0)} × {props.get('bbox_z', 0)}</div>
                <div class="lbl">Dimensions X × Y × Z (mm)</div>
            </div>
            <div class="metric-card">
                <div class="val">{props.get('volume_cm3', 0)} cm³</div>
                <div class="lbl">Volume ({props.get('volume_mm3', 0):,.0f} mm³)</div>
            </div>
            <div class="metric-card">
                <div class="val">{props.get('area_cm2', 0)} cm²</div>
                <div class="lbl">Surface Totale</div>
            </div>
            <div class="metric-card">
                <div class="val">{props.get('mass_steel_g', 0)} g</div>
                <div class="lbl">Masse Acier (7.85 g/cm³)</div>
            </div>
            <div class="metric-card">
                <div class="val">{props.get('mass_alu_g', 0)} g</div>
                <div class="lbl">Masse Aluminium (2.70 g/cm³)</div>
            </div>
            <div class="metric-card">
                <div class="val">{props.get('mass_pla_g', 0)} g</div>
                <div class="lbl">Masse PLA Impression 3D (1.25 g/cm³)</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        center = props.get("center", (0, 0, 0))
        st.caption(f"🎯 **Centre de gravité calculé :** X = `{center[0]} mm`, Y = `{center[1]} mm`, Z = `{center[2]} mm`")

    # ── TAB 2 : CadQuery Code & Live Interactive Editor ───────────────────────
    with tab_code:
        st.markdown('<span class="step-badge">3</span> <b>Code CadQuery & Édition en Direct</b>', unsafe_allow_html=True)
        st.caption(
            "Vous pouvez modifier les dimensions, rayons ou opérations directement ci-dessous, "
            "puis cliquer sur le bouton bleu pour recalculer le modèle 3D instantanément !"
        )

        user_edited_code = st.text_area(
            label="Éditeur de code CadQuery",
            value=st.session_state["cq_code"],
            height=300,
            key="code_editor_area",
        )

        col_recalc, col_dl_code = st.columns([2, 1])
        with col_recalc:
            st.markdown('<div class="btn-update">', unsafe_allow_html=True)
            recalc_clicked = st.button("▶️ Mettre à jour le modèle 3D depuis le code", use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

        with col_dl_code:
            st.download_button(
                label="📋 Télécharger le script (.py)",
                data=user_edited_code,
                file_name="piece_cadquery.py",
                mime="text/x-python",
                use_container_width=True,
            )

        if recalc_clicked:
            with st.spinner("⚙️ Recalcul de la géométrie CadQuery…"):
                try:
                    updated_code, _, updated_props = generate_part_from_code(
                        code=user_edited_code,
                        step_output_path=step_path,
                        stl_output_path=stl_path,
                    )
                    st.session_state["cq_code"] = updated_code
                    st.session_state["props"] = updated_props
                    st.session_state["used_model"] = "Éditeur utilisateur (Direct)"
                    st.success("✅ Modèle 3D et fichiers STEP/STL mis à jour avec succès !")
                    st.rerun()
                except Exception as exc:
                    st.error(f"❌ Erreur lors de l'exécution du code : {exc}")

    # ── TAB 3 : Export & CAD Guide ────────────────────────────────────────────
    with tab_export:
        st.markdown('<span class="step-badge">4</span> <b>Fichiers CAO et Impression 3D prêts à télécharger</b>', unsafe_allow_html=True)

        col_step, col_stl = st.columns(2)

        with col_step:
            st.markdown("""
            <div class="card" style="text-align:center;">
                <div style="font-size:2.6rem;">🏭</div>
                <h3 style="color:#58a6ff; margin:0.4rem 0;">Fichier STEP (.step)</h3>
                <p style="color:#8b949e; font-size:0.85rem; margin-bottom:1rem;">
                    Format standard international ISO 10303 (AP203/AP214).<br>
                    <b>B-Rep exact</b> — Compatible CATIA, SolidWorks, Fusion 360, FreeCAD.
                </p>
            </div>
            """, unsafe_allow_html=True)

            if os.path.exists(step_path):
                with open(step_path, "rb") as f:
                    step_data = f.read()
                st.metric("Taille du fichier STEP", f"{len(step_data) / 1024:.1f} Ko")
                st.download_button(
                    label="⬇️ Télécharger le fichier STEP (CATIA/SolidWorks)",
                    data=step_data,
                    file_name="piece_mecanique.step",
                    mime="application/step",
                    use_container_width=True,
                )

        with col_stl:
            st.markdown("""
            <div class="card" style="text-align:center;">
                <div style="font-size:2.6rem;">🖨️</div>
                <h3 style="color:#58a6ff; margin:0.4rem 0;">Fichier STL (.stl)</h3>
                <p style="color:#8b949e; font-size:0.85rem; margin-bottom:1rem;">
                    Format maillage triangulaire haute résolution.<br>
                    Prêt pour les trancheurs <b>Cura, Bambu Studio, PrusaSlicer</b>.
                </p>
            </div>
            """, unsafe_allow_html=True)

            if os.path.exists(stl_path):
                with open(stl_path, "rb") as f:
                    stl_data = f.read()
                st.metric("Taille du fichier STL", f"{len(stl_data) / 1024:.1f} Ko")
                st.download_button(
                    label="⬇️ Télécharger le fichier STL (Impression 3D)",
                    data=stl_data,
                    file_name="piece_mecanique.stl",
                    mime="application/octet-stream",
                    use_container_width=True,
                )

        st.markdown("---")
        st.markdown("#### 📖 Guide d'Ouverture et d'Import CAO")
        with st.expander("🛠️ Comment ouvrir dans CATIA V5 & V6 / 3DEXPERIENCE"):
            st.markdown("""
            1. Ouvrez CATIA.
            2. Allez dans **Fichier → Ouvrir** (ou `Ctrl + O`).
            3. Dans le filtre des types de fichiers, sélectionnez **STEP Files (`*.stp`, `*.step`)**.
            4. Sélectionnez votre fichier `piece_mecanique.step`.
            5. CATIA convertit automatiquement le modèle en solide exact (CATPart B-Rep).
            """)

        with st.expander("🛠️ Comment ouvrir dans Dassault SolidWorks"):
            st.markdown("""
            1. Ouvrez SolidWorks.
            2. Cliquez sur **Ouvrir** (`Ctrl + O`).
            3. Choisissez le type **STEP AP203/214 (`*.step`, `*.stp`)**.
            4. Activez l'option *Reconnaissance de fonctions (FeatureWorks)* si vous souhaitez rendre l'arbre de conception modifiable.
            5. Validez pour générer une pièce `.sldprt`.
            """)

        with st.expander("🛠️ Comment ouvrir dans Autodesk Fusion 360 & FreeCAD"):
            st.markdown("""
            - **Fusion 360** : Fichier → Ouvrir → Ouvrir depuis l'ordinateur, ou glissez-déposez le fichier `.step` dans le panneau de données.
            - **FreeCAD** : Fichier → Importer (`Ctrl + I`) → Sélectionnez le fichier `.step` (atelier *Part* ou *PartDesign*).
            """)

    # ── TAB 4 : Session History Gallery ───────────────────────────────────────
    with tab_history:
        st.markdown('<span class="step-badge">5</span> <b>Pièces générées pendant cette session</b>', unsafe_allow_html=True)
        history_list = st.session_state.get("history", [])

        if not history_list:
            st.info("Aucune pièce supplémentaire dans l'historique.")
        else:
            for idx, item in enumerate(reversed(history_list)):
                with st.expander(f"🕒 {item['time']} — {item['desc']} ({item['bbox']})", expanded=(idx == 0)):
                    col_h1, col_h2 = st.columns([3, 1])
                    with col_h1:
                        st.markdown(f"**Modèle utilisé :** `{item['model']}`")
                        st.markdown(f"**Dimensions :** `{item['bbox']}` &nbsp;|&nbsp; **Volume :** `{item['vol']}`")
                        st.code(item["code"], language="python")
                    with col_h2:
                        if st.button(f"Restaurer cette pièce #{len(history_list) - idx}", key=f"restore_{idx}"):
                            st.session_state["cq_code"] = item["code"]
                            st.session_state["props"] = item["props"]
                            generate_part_from_code(item["code"], step_path, stl_path)
                            st.rerun()


# ─── Footer ───────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("""
<div style='text-align:center; color:#8b949e; font-size:0.8rem; padding: 1rem 0;'>
    Propulsé par <b style='color:#58a6ff;'>Google Gemini AI</b> · 
    <b style='color:#58a6ff;'>CadQuery</b> (Noyau OpenCASCADE OCCT) · 
    <b style='color:#58a6ff;'>Three.js WebGL</b> · 
    Compatible CATIA V5/V6 & SolidWorks
</div>
""", unsafe_allow_html=True)
