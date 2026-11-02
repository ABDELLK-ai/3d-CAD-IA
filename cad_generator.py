"""
CAD Generator — Converts natural language descriptions into CadQuery code
using the Google Gemini REST API directly, then generates STEP/STL files.

Uses the REST API directly (no SDK version dependency).
"""
import socket
import re
import os
import json
import ast
import textwrap
import urllib.request
import urllib.error

# Ensure font directories for OpenCASCADE Font_FontMgr in headless Linux containers
if "CSF_FontDirectories" not in os.environ:
    for _fdir in ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype", "/usr/share/fonts"]:
        if os.path.isdir(_fdir):
            os.environ["CSF_FontDirectories"] = _fdir
            break

import cadquery as cq


# ─── System prompt for Gemini ────────────────────────────────────────────────
SYSTEM_PROMPT = (
    "You are an expert mechanical CAD engineer who translates natural-language part descriptions "
    "into clean, robust, runnable CadQuery Python code.\n\n"
    "STRICT RULES:\n"
    "1. Enclose your Python code in a single ```python ... ``` markdown code block.\n"
    "2. Do NOT output internal thinking, conversational text, or reasoning outside or inside the code block.\n"
    "3. Output EXACTLY ONE single, finished, working Python script. Do NOT output multiple attempts, scratch work, or alternative drafts.\n"
    "4. The final result MUST be stored in a variable named exactly: `result`\n"
    "5. Use only the `cadquery` library (pre-imported as `cq`).\n"
    "6. Keep geometry realistic, manifold, and parametric.\n"
    "7. Do NOT call show_object(), exporters.export(), or any display function.\n"
    "8. All top-level code (imports, variable assignments, result =) MUST have ZERO indentation (start at column 0).\n"
    "9. Every non-code line inside the block MUST begin with a '#' comment. NEVER write un-commented English headings like 'Base parameters' or '1. Base plate'.\n\n"
    "CRITICAL CADQUERY API RULES (AVOID THESE COMMON BUGS):\n"
    "  • NEVER CALL .arc()! CadQuery Workplane has NO .arc() method. To round arm tops or bracket ends, use 3D fillets: .edges('>Z and |Y').fillet(radius) or .edges('|Y').fillet(radius), or combine with cylinders.\n"
    "  • NEVER PASS centerPoint to .workplane()! .workplane() takes NO centerPoint argument. To shift sketch origin, use .center(x, y) after .workplane().\n"
    "  • Text engraving: use .faces('>Z').workplane().center(x, y).text('TEXT', fontsize=4.0, distance=-0.6). Note that fontsize is all lowercase, and distance is negative for engraving cut depth. Do NOT use fontSize or depth.\n"
    "  • .box() on a fresh Workplane does NOT take combine=True (e.g. use cq.Workplane('XY').box(L, W, H)). combine=True is only valid when adding to an existing solid.\n"
    "  • CRITICAL FILLET/CHAMFER RULE (PREVENTS 'BRep_API: command not done'):\n"
    "    NEVER CALL .edges('|Z').chamfer() or .edges('|Z').fillet() on complex profiles (gears, teeth, sprockets, splines, or multi-vertex polygons)!\n"
    "    Calling .edges('|Z') on a gear selects all 80+ vertical tooth flank corners simultaneously, which immediately crashes OpenCASCADE with 'BRep_API: command not done'.\n"
    "    When generating gears, sprockets, or complex profiles, DO NOT add decorative chamfers or fillets to the teeth. Keep tooth geometries clean.\n"
    "  • GEARS & TEETH PATTERN: Compute tooth vertices in polar coordinates around the center in a loop, close the profile with cq.Workplane('XY').polyline(pts).close(), extrude once with .extrude(thickness), and add the bore with .faces('>Z').workplane().hole(bore_dia). Do NOT chamfer tooth edges.\n\n"
    "AVAILABLE CadQuery PATTERNS:\n"
    "  box                       -> cq.Workplane('XY').box(L, W, H)\n"
    "  cylinder                  -> cq.Workplane('XY').cylinder(height, radius)\n"
    "  sphere                    -> cq.Workplane('XY').sphere(radius)\n"
    "  through hole              -> .faces('>Z').workplane().hole(diameter)\n"
    "  counterbore (lamage)      -> .faces('>Z').workplane().cboreHole(holeDiameter, cboreDiameter, cboreDepth)\n"
    "  countersink (fraisure)    -> .faces('>Z').workplane().cskHole(holeDiameter, cskDiameter, cskAngle)\n"
    "  shell (hollow)            -> .shell(-thickness)\n"
    "  chamfer                   -> .edges('|Z').chamfer(size) or .edges('>Z').chamfer(size)\n"
    "  fillet                    -> .edges('|Z').fillet(size) or .edges('>Z').fillet(size)\n"
    "  clevis / bracket in U     ->\n"
    "      base = cq.Workplane('XY').box(L, W, H_base)\n"
    "      arms = base.faces('>Z').workplane().box(L, W, H_arm, centered=(True, True, False), combine=True)\n"
    "      clevis = arms.faces('>Z').workplane().rect(gap_w, W + 2).cutBlind(-H_arm)\n"
    "      clevis = clevis.faces('>Z').edges('|Y').fillet(arm_thickness / 2.0)\n"
    "      clevis = clevis.faces('>X').workplane().center(0, pin_z).hole(pin_dia)\n"
    "  text / engraving          -> .faces('<Y').workplane().center(x, y).text('TEXT', fontsize=4.0, distance=-0.6)\n"
    "  union                     -> result = body1.union(body2)\n"
    "  cut                       -> result = body1.cut(body2)\n\n"
    "EXAMPLE for 'a 100x60x20mm rectangular plate with four 8mm holes at corners':\n"
    "```python\n"
    "import cadquery as cq\n"
    "plate = cq.Workplane('XY').box(100, 60, 20)\n"
    "result = (\n"
    "    plate\n"
    "    .faces('>Z').workplane()\n"
    "    .pushPoints([(-40, -20), (40, -20), (-40, 20), (40, 20)])\n"
    "    .hole(8)\n"
    ")\n"
    "```\n"
)

# ─── Gemini REST API Configuration ──────────────────────────────────────────
# Default candidate models in order of priority (fast text/code models first)
DEFAULT_PREFERRED_MODELS = [
    "gemini-1.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash-8b",
    "gemini-2.5-flash",
    "gemini-1.5-pro",
    "gemini-pro",
]

# Patterns for models that cannot be used for text-to-CAD generation
DISALLOWED_PATTERNS = (
    "-tts",
    "-audio",
    "-image",
    "-video",
    "embedding",
    "imagen",
    "realtime",
    "robotics",
    "medlm",
)

_LAST_USED_MODEL = None

# ─── Built-in Preset Examples (Offline Demo Mode) ────────────────────────────
PRESET_EXAMPLES = {
    "Plaque percée": {
        "description": (
            "Une plaque rectangulaire en acier de 120mm x 80mm x 15mm "
            "avec 4 trous de 10mm de diamètre aux coins, à 10mm des bords."
        ),
        "code": (
            "import cadquery as cq\n\n"
            "# Plaque rectangulaire 120x80x15mm\n"
            "plate = cq.Workplane('XY').box(120, 80, 15)\n\n"
            "# 4 trous Ø10mm aux coins, à 10mm des bords (entraxe 100x60mm)\n"
            "result = (\n"
            "    plate.faces('>Z')\n"
            "    .workplane()\n"
            "    .pushPoints([(-50, -30), (50, -30), (-50, 30), (50, 30)])\n"
            "    .hole(10)\n"
            ")\n"
        ),
    },
    "Boulon hexagonal": {
        "description": (
            "Un boulon M16 avec une tête hexagonale de 24mm de plat, hauteur de tête 10mm, "
            "et un filetage cylindrique de 16mm de diamètre et 60mm de longueur."
        ),
        "code": (
            "import cadquery as cq\n\n"
            "# Tête hexagonale 24mm sur plat (diamètre circonscrit ~27.71mm), hauteur 10mm\n"
            "head = cq.Workplane('XY').polygon(nSides=6, diameter=27.71).extrude(10)\n\n"
            "# Corps de vis cylindrique M16 (diamètre 16mm, longueur 60mm)\n"
            "shank = head.faces('>Z').workplane().circle(8).extrude(60)\n\n"
            "# Chanfrein d'extrémité 1.5mm\n"
            "result = shank.faces('>Z').chamfer(1.5)\n"
        ),
    },
    "Équerre de support": {
        "description": (
            "Une équerre en L en aluminium: deux faces perpendiculaires de 80mm x 60mm "
            "avec une épaisseur de 8mm, arrondie sur les bords intérieurs à rayon 5mm."
        ),
        "code": (
            "import cadquery as cq\n\n"
            "# Profil en L 80x60mm, épaisseur 8mm, largeur 50mm\n"
            "pts = [(0, 0), (80, 0), (80, 8), (8, 8), (8, 60), (0, 60)]\n"
            "bracket = cq.Workplane('XY').polyline(pts).close().extrude(50)\n\n"
            "# Congé intérieur de 5mm sur l'arête intérieure\n"
            "result = bracket.edges(cq.NearestToPointSelector((8, 8, 25))).fillet(5)\n"
        ),
    },
    "Boîtier creux": {
        "description": (
            "Un boîtier rectangulaire creux de 100x70x50mm, épaisseur de paroi 4mm, "
            "ouvert en haut. Avec un congé de 3mm sur toutes les arêtes extérieures."
        ),
        "code": (
            "import cadquery as cq\n\n"
            "# Boîtier extérieur 100x70x50mm avec congés verticaux de 3mm\n"
            "box = cq.Workplane('XY').box(100, 70, 50).edges('|Z').fillet(3)\n\n"
            "# Coque ouverte en haut (épaisseur paroi 4mm)\n"
            "result = box.faces('>Z').shell(-4)\n"
        ),
    },
    "Cylindre fileté": {
        "description": (
            "Un cylindre de 50mm de diamètre et 80mm de hauteur avec un trou central "
            "de 20mm de diamètre et un chanfrein de 2mm sur les deux faces supérieures."
        ),
        "code": (
            "import cadquery as cq\n\n"
            "# Cylindre Ø50x80mm avec alésage central traversant Ø20mm\n"
            "cyl = cq.Workplane('XY').cylinder(80, 25)\n"
            "bore = cyl.faces('>Z').workplane().hole(20)\n\n"
            "# Chanfrein 2mm sur la face supérieure\n"
            "result = bore.faces('>Z').chamfer(2)\n"
        ),
    },
    "Bride circulaire": {
        "description": (
            "Une bride circulaire de tuyauterie: disque de 120mm de diamètre, 15mm d'épaisseur, "
            "alésage central de 50mm, et 4 trous de fixation de 12mm répartis sur un cercle de 90mm."
        ),
        "code": (
            "import cadquery as cq\n\n"
            "# Bride circulaire Ø120mm, épaisseur 15mm, alésage central Ø50mm\n"
            "flange = (\n"
            "    cq.Workplane('XY')\n"
            "    .circle(60)\n"
            "    .extrude(15)\n"
            "    .faces('>Z')\n"
            "    .workplane()\n"
            "    .hole(50)\n"
            "    .faces('>Z')\n"
            "    .workplane()\n"
            "    .polygon(nSides=4, diameter=90)\n"
            "    .vertices()\n"
            "    .hole(12)\n"
            ")\n"
            "result = flange\n"
        ),
    },
    "Arbre épaulé claveté": {
        "description": (
            "Un arbre mécanique étagé: premier cylindre Ø40mm x 50mm de long, second cylindre "
            "Ø25mm x 60mm de long, avec chanfreins de 1.5mm aux extrémités."
        ),
        "code": (
            "import cadquery as cq\n\n"
            "# Premier étage de l'arbre: Ø40mm x 50mm\n"
            "base = cq.Workplane('XY').cylinder(50, 20)\n\n"
            "# Second étage: Ø25mm x 60mm centré sur la face supérieure\n"
            "step = base.faces('>Z').workplane().circle(12.5).extrude(60)\n\n"
            "# Chanfreins d'extrémité 1.5mm\n"
            "result = step.faces('>Z').chamfer(1.5).faces('<Z').chamfer(1.5)\n"
        ),
    },
    "Cylindre avec lamage": {
        "description": (
            "Un cylindre de 60mm de diamètre et 45mm de hauteur, traversé par un trou central "
            "de 24mm de diamètre, avec un lamage supérieur de 36mm de diamètre sur 12mm de profondeur "
            "et un chanfrein de 2mm sur la face supérieure."
        ),
        "code": (
            "import cadquery as cq\n\n"
            "# Cylindre Ø60x45mm (rayon 30mm) avec chanfrein 2mm supérieur\n"
            "cyl = cq.Workplane('XY').cylinder(45, 30).edges('>Z').chamfer(2)\n\n"
            "# Alésage central Ø24mm traversant et lamage Ø36mm x 12mm de profondeur\n"
            "result = cyl.faces('>Z').workplane().cboreHole(24, 36, 12)\n"
        ),
    },
    "Chape d'articulation en U": {
        "description": (
            "Une chape d'articulation en U : embase rectangulaire de 90mm x 60mm x 15mm avec 4 trous "
            "de fixation Ø9mm (à 10mm des bords, entraxe 70x40mm). Deux bras verticaux s'élèvent de 70mm au-dessus de l'embase, "
            "séparés par un dégagement central de 36mm de large. Sommet des deux bras arrondi et alésage coaxial traversant Ø25mm "
            "au centre de l'arrondi. Gravure 'ILIASS EL AHMAR Futur Leader' sur la face avant."
        ),
        "code": (
            "import cadquery as cq\n\n"
            "# 1. Embase rectangulaire 90x60x15mm avec 4 trous Ø9mm (entraxe 70x40mm)\n"
            "base = (\n"
            "    cq.Workplane('XY')\n"
            "    .box(90, 60, 15)\n"
            "    .faces('>Z')\n"
            "    .workplane()\n"
            "    .pushPoints([(-35, -20), (35, -20), (-35, 20), (35, 20)])\n"
            "    .hole(9)\n"
            ")\n\n"
            "# 2. Bloc des deux bras verticaux s'élevant de 70mm au-dessus de l'embase\n"
            "arms = base.faces('>Z').workplane().box(90, 60, 70, centered=(True, True, False), combine=True)\n\n"
            "# 3. Dégagement central de 36mm de large traversant la profondeur (60mm)\n"
            "clevis = arms.faces('>Z').workplane().rect(36, 62).cutBlind(-70)\n\n"
            "# 4. Sommet des bras arrondi en plein demi-cercle (rayon 13.4mm)\n"
            "clevis = clevis.faces('>Z').edges('|Y').fillet(13.4)\n\n"
            "# 5. Alésage coaxial traversant Ø25mm au centre de l'arrondi\n"
            "clevis = clevis.faces('>X').workplane().center(0, 70 - 13.5).hole(25)\n\n"
            "# 6. Gravure texte personnalisée sur la face avant de l'embase\n"
            "result = clevis.faces('<Y').workplane().center(0, -35).text('ILIASS EL AHMAR Futur Leader', 4.0, -0.6)\n"
        ),
    },
    "Engrenage droit": {
        "description": (
            "Un engrenage droit standard à 20 dents: module 2 (diamètre primitif 40mm, "
            "diamètre extérieur 44mm), épaisseur 10mm avec alésage central de 10mm."
        ),
        "code": (
            "import cadquery as cq\n"
            "import math\n\n"
            "# Paramètres de l'engrenage droit\n"
            "num_teeth = 20\n"
            "module = 2.0\n"
            "pitch_diameter = num_teeth * module  # 40mm\n"
            "addendum = module\n"
            "dedendum = 1.25 * module\n"
            "outer_diameter = pitch_diameter + 2 * addendum  # 44mm\n"
            "root_diameter = pitch_diameter - 2 * dedendum   # 35mm\n"
            "thickness = 10.0\n"
            "bore_diameter = 10.0\n"
            "pitch_angle = 360.0 / num_teeth\n\n"
            "# Profil 2D polygonal pour toutes les dents\n"
            "def polar(deg, r):\n"
            "    rad = math.radians(deg)\n"
            "    return (r * math.cos(rad), r * math.sin(rad))\n\n"
            "pts = []\n"
            "for i in range(num_teeth):\n"
            "    a_center = i * pitch_angle\n"
            "    a_root1 = a_center - pitch_angle * 0.45\n"
            "    a_root2 = a_center + pitch_angle * 0.45\n"
            "    a_tip1 = a_center - pitch_angle * 0.2\n"
            "    a_tip2 = a_center + pitch_angle * 0.2\n"
            "    pts.append(polar(a_root1, root_diameter / 2.0))\n"
            "    pts.append(polar(a_tip1, outer_diameter / 2.0))\n"
            "    pts.append(polar(a_tip2, outer_diameter / 2.0))\n"
            "    pts.append(polar(a_root2, root_diameter / 2.0))\n\n"
            "gear_sketch = cq.Workplane('XY').polyline(pts).close()\n"
            "gear_solid = gear_sketch.extrude(thickness)\n"
            "result = gear_solid.faces('>Z').workplane().hole(bore_diameter)\n"
        ),
    },
}


def find_matching_preset(description: str):
    """Find a matching preset example by description or title, if any."""
    if not description:
        return None, None
    desc_clean = description.strip().lower()

    # Priority direct keywords for specialized mechanical parts
    if "chape" in desc_clean or "clevis" in desc_clean or ("bras" in desc_clean and "36mm" in desc_clean):
        return "Chape d'articulation en U", PRESET_EXAMPLES["Chape d'articulation en U"]["code"]
    if "engrenage" in desc_clean or "gear" in desc_clean or "pignon" in desc_clean or "dent" in desc_clean:
        return "Engrenage droit", PRESET_EXAMPLES["Engrenage droit"]["code"]

    # 1. Exact match with description or title
    for name, item in PRESET_EXAMPLES.items():
        if desc_clean == item["description"].strip().lower() or desc_clean == name.lower():
            return name, item["code"]
    # 2. Prefix match
    for name, item in PRESET_EXAMPLES.items():
        if desc_clean.startswith(name.lower()):
            return name, item["code"]
    # 3. Significant unique keywords (excluding common prepositions/articles)
    stopwords = {"de", "la", "le", "en", "un", "une", "des", "du", "et", "au", "aux", "pour", "avec", "par"}
    for name, item in PRESET_EXAMPLES.items():
        sig_words = [w for w in name.lower().split() if w not in stopwords and len(w) > 3]
        if any(w in desc_clean for w in sig_words):
            return name, item["code"]
    return None, None


def get_last_used_model() -> str:
    """Return the name of the model that successfully generated the last code."""
    return _LAST_USED_MODEL or "Inconnu"


def is_text_generation_model(name: str) -> bool:
    """Check if model name is suitable for text/code generation (not TTS, audio, embedding)."""
    name_lower = name.lower()
    return not any(pat in name_lower for pat in DISALLOWED_PATTERNS)


def get_available_models(api_key: str) -> list:
    """
    Query Gemini ListModels to find which text models support generateContent for this key.
    Excludes specialized models (TTS, image, embedding) that have limit: 0 on free tier.
    """
    if not api_key:
        return []

    for api_version in ("v1beta", "v1"):
        url = f"https://generativelanguage.googleapis.com/{api_version}/models?key={api_key}"
        try:
            req = urllib.request.Request(
                url,
                headers={"Content-Type": "application/json"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                found = []
                for item in data.get("models", []):
                    methods = item.get("supportedGenerationMethods", [])
                    if "generateContent" in methods:
                        m_name = item.get("name", "")
                        if m_name.startswith("models/"):
                            m_name = m_name[len("models/"):]
                        if is_text_generation_model(m_name):
                            found.append(m_name)
                if found:
                    return found
        except Exception:
            continue
    return []


def sanitize_cadquery_code(code: str) -> str:
    """
    Sanitize generated CadQuery code to fix common LLM hallucinations before execution:
    - Replace .arc(p1, p2) with .threePointArc(p1, p2) (Workplane has no .arc method).
    - Fix .workplane(centerPoint=(x, y, z)) or centerPoint=(x, y) -> .workplane().center(x, y).
    - Fix .text() parameters: fontSize -> fontsize, depth=X -> distance=-X.
    - Fix .box(..., combine=True) when on a fresh cq.Workplane('XY') with no previous solid.
    - Auto-comment lines that are plain markdown headings, numbered steps ('1. Base plate'),
      or un-commented English text titles ('Base parameters') inside the code block.
    """
    if not code:
        return ""

    # 1. Hallucinated .arc( -> .threePointArc(
    code = re.sub(r"\.arc\(", ".threePointArc(", code)

    # 2. Hallucinated centerPoint in workplane(...)
    code = re.sub(
        r"\.workplane\(\s*centerPoint=\(([^),]+),\s*([^),]+)(?:,\s*[^)]+)?\)\s*\)",
        r".workplane().center(\1, \2)",
        code,
    )
    code = re.sub(
        r"\.workplane\(\s*centerPoint=\(([^)]+)\)\s*\)",
        r".workplane().center(\1)",
        code,
    )

    # 3. Parameter names for .text()
    code = re.sub(r"fontSize\s*=", "fontsize=", code)
    code = re.sub(r"depth\s*=\s*([0-9.]+)", r"distance=-\1", code)

    # 4. combine=True on fresh workplane
    code = re.sub(
        r"cq\.Workplane\(\s*['\"]([A-Z]+)['\"]\s*\)\.box\(([^)]+),\s*combine=True\)",
        r"cq.Workplane('\1').box(\2)",
        code,
    )

    # 5. Comment out stray un-commented English prose lines / headings
    prose_starters = (
        "step ", "step:", "note:", "explanation:", "description:",
        "let's ", "we ", "the ", "this ", "therefore", "furthermore",
        "width ", "height ", "depth ", "radius ", "diameter ",
        "left ", "right ", "top ", "bottom ", "front ", "back ",
        "add ", "cut ", "round ", "combine ", "intersect ", "remove ",
        "simpler ", "even simpler", "wait,", "often ", "shape:", "dimensions:"
    )

    lines = code.splitlines()
    fixed_lines = []
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            fixed_lines.append(line)
            continue

        s_lower = s.lower()

        # If it starts with standard Python syntax keywords, keep it
        if s.startswith(("import ", "from ", "def ", "class ", "return ", "result =", "result=")):
            fixed_lines.append(line)
            continue

        # If it's a chained method call or continuation line, keep it
        if s.startswith((".", ")", "]", "}", "+", "-", "*", "/", "%", ",")):
            fixed_lines.append(line)
            continue

        # If it's a variable assignment like x = 10, keep it
        if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*\s*=[^=]", s):
            fixed_lines.append(line)
            continue

        # Numbered headings like '1. Base plate'
        if re.match(r"^\d+\.\s+[A-Za-z]", s):
            fixed_lines.append("# " + line)
            continue

        # Markdown bullet or header like '- Left arm' or '### Base'
        if s.startswith(("- ", "* ", "### ", "## ", "# ")):
            if not s.startswith("#"):
                fixed_lines.append("# " + line)
                continue

        # Prose sentence starters
        if any(s_lower.startswith(p) for p in prose_starters):
            if re.match(r"^[A-Z][a-z]+.*", s) and not any(op in s for op in ("=", "(", "cq.")):
                fixed_lines.append("# " + line)
                continue
            if s_lower.startswith(("let's ", "the ", "this ", "wait,", "even simpler", "simpler", "we ")):
                fixed_lines.append("# " + line)
                continue

        # Words without any Python operators (e.g. 'Base parameters', 'Arm parameters')
        if not any(c in s for c in "()[]={}:;,.+\"'") and len(s.split()) >= 2:
            fixed_lines.append("# " + line)
            continue

        fixed_lines.append(line)

    return "\n".join(fixed_lines)


def fix_code_indentation(code: str) -> str:
    """
    Ensure python code has valid top-level indentation.
    Handles:
    - Entire block indented by K spaces (textwrap.dedent).
    - Line 1 unindented while lines 2+ were block-indented (unexpected indent).
    - Mixed tabs/spaces.
    """
    if not code:
        return ""

    code = code.replace("\t", "    ")

    # 1. Standard dedent on full code
    candidate = textwrap.dedent(code).strip()
    try:
        ast.parse(candidate)
        return candidate
    except (IndentationError, SyntaxError):
        pass

    # 2. Case where line 1 has 0 indent but lines 2+ are block-indented
    lines = candidate.splitlines()
    if len(lines) > 1:
        rest_dedented = textwrap.dedent("\n".join(lines[1:]))
        attempt = lines[0].strip() + "\n" + rest_dedented
        try:
            ast.parse(attempt)
            return attempt
        except (IndentationError, SyntaxError):
            pass

    # 3. Line-by-line alignment: detect common indentation on subsequent lines
    if len(lines) > 1:
        indent_len = 0
        for l in lines[1:]:
            s = l.strip()
            if s and not s.startswith("#"):
                m = re.match(r"^(\s+)", l)
                if m:
                    indent_len = len(m.group(1))
                break
        if indent_len > 0:
            realigned = [lines[0].strip()]
            for l in lines[1:]:
                if len(l) >= indent_len and l[:indent_len].isspace():
                    realigned.append(l[indent_len:])
                else:
                    realigned.append(l.strip())
            attempt2 = "\n".join(realigned)
            try:
                ast.parse(attempt2)
                return attempt2
            except (IndentationError, SyntaxError):
                pass

    return candidate


def extract_code(raw_text: str) -> str:
    """Extract clean Python code from Gemini response, stripping markdown fences, commentary and fixing indentation."""
    if not raw_text:
        return ""

    # 1. Search for fenced python block
    m = re.search(r"```(?:python)?\s*\n([\s\S]*?)```", raw_text)
    if m:
        content = m.group(1)
    else:
        m2 = re.search(r"```([\s\S]*?)```", raw_text)
        if m2:
            content = m2.group(1)
        else:
            # Fallback: strip any ```
            content = re.sub(r"```(?:python)?", "", raw_text)
            content = content.replace("```", "")

    # 2. Filter out non-code commentary lines before code starts
    lines = content.splitlines()
    cleaned = []
    started = False
    for line in lines:
        stripped = line.strip()
        if not started:
            if stripped.startswith((
                "import ", "from ", "cq", "#", "result", "val", "pts",
                "plate", "box", "cyl", "head", "shank", "bracket", "body", "base", "part", "flange"
            )):
                started = True
                cleaned.append(line)
        else:
            cleaned.append(line)

    raw_code = "\n".join(cleaned) if cleaned else (content if ("cq." in content or "cadquery" in content or "result =" in content) else "")
    sanitized = sanitize_cadquery_code(raw_code)
    return fix_code_indentation(sanitized)


def description_to_cadquery_code(
    description: str,
    api_key: str,
    model_name: str = None,
) -> str:
    """
    Call the Gemini REST API to convert a text description into CadQuery code.
    Tries standard text models, discovers available models via ListModels (excluding TTS/audio),
    and falls back through compatible candidates if 404 or 429 (limit 0) occurs.
    """
    global _LAST_USED_MODEL

    # Build candidates list
    candidates = []
    if model_name and model_name.strip() and model_name.lower() != "auto":
        candidates.append(model_name.strip())

    # Dynamically discover text models supported by this user's API key
    discovered = get_available_models(api_key)

    # Prioritize preferred models if found or as defaults
    for pref in DEFAULT_PREFERRED_MODELS:
        if (not discovered or pref in discovered) and pref not in candidates:
            candidates.append(pref)

    # Add any other discovered text models
    for disc in discovered:
        if disc not in candidates:
            candidates.append(disc)

    if not candidates:
        candidates = list(DEFAULT_PREFERRED_MODELS)

    payload = {
        "system_instruction": {
            "parts": [{"text": SYSTEM_PROMPT}]
        },
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            "Generate CadQuery Python code for the following part description.\n"
                            "Store the final result in a variable named `result`.\n\n"
                            f"Description:\n{description}"
                        )
                    }
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 8192,
        },
    }

    api_key = (api_key or "").strip()
    data = json.dumps(payload).encode("utf-8")
    errors_encountered = []

    for candidate in candidates:
        for api_version in ("v1beta", "v1"):
            url = (
                f"https://generativelanguage.googleapis.com/{api_version}/models/"
                f"{candidate}:generateContent?key={api_key}"
            )
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=35) as resp:
                    result = json.loads(resp.read().decode("utf-8"))

                candidates_data = result.get("candidates", [])
                if not candidates_data:
                    errors_encountered.append(f"{candidate} ({api_version}): Aucun candidat dans la réponse")
                    continue

                content = candidates_data[0].get("content", {})
                parts = content.get("parts", [])
                if not parts:
                    errors_encountered.append(f"{candidate} ({api_version}): Aucun contenu dans la réponse")
                    continue

                # Filter out thought parts (used in Gemini 2.0 / 2.5 thinking models)
                answer_parts = [p.get("text", "") for p in parts if not p.get("thought", False) and "text" in p]
                if answer_parts:
                    raw_text = "\n".join(answer_parts)
                else:
                    raw_text = parts[-1].get("text", "")

                code = extract_code(raw_text)
                if not code or ("cq." not in code and "cadquery" not in code and "result" not in code):
                    errors_encountered.append(f"{candidate} ({api_version}): Réponse sans code CadQuery valide")
                    continue

                _LAST_USED_MODEL = f"{candidate} ({api_version})"
                return code

            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")
                # 404: model not supported on this endpoint/version, try next
                if e.code == 404:
                    errors_encountered.append(f"{candidate} ({api_version}): 404 Not Found")
                    continue
                # 429: quota or free tier limit:0 for this model, try next candidate!
                if e.code == 429:
                    errors_encountered.append(f"{candidate} ({api_version}): 429 Quota/Tier restriction")
                    continue
                # 400: invalid key
                if e.code == 400 and ("API_KEY_INVALID" in body or "API key not valid" in body):
                    raise RuntimeError("Clé API Gemini invalide. Veuillez vérifier votre clé.") from e

                errors_encountered.append(f"{candidate} ({api_version}): HTTP {e.code}")
                continue

            except (socket.timeout, TimeoutError):
                errors_encountered.append(f"{candidate} ({api_version}): Délai dépassé (>35s)")
                continue

            except urllib.error.URLError as e:
                err_msg = str(getattr(e, "reason", e))
                errors_encountered.append(f"{candidate} ({api_version}): Erreur réseau ({err_msg})")
                continue

            except Exception as e:
                errors_encountered.append(f"{candidate} ({api_version}): Erreur ({e})")
                continue

    # If all candidates failed, check if 429 was the only reason
    quota_errors = [err for err in errors_encountered if "429" in err]
    if quota_errors and len(quota_errors) == len(errors_encountered):
        raise RuntimeError(
            "Quota API Gemini dépassé (HTTP 429) sur tous les modèles testés. "
            "Le palier gratuit limite le nombre de requêtes par minute/jour. "
            "Veuillez patienter quelques instants ou vérifier votre quota sur https://ai.dev/rate-limit"
        )

    avail_info = f"Modèles disponibles détectés : {', '.join(discovered[:6])}" if discovered else "Aucun modèle standard détecté."
    raise RuntimeError(
        f"Impossible d'appeler l'API Gemini avec les modèles testés.\n"
        f"Tentatives : {', '.join(errors_encountered[:4])}\n{avail_info}"
    )


def get_part_properties(result) -> dict:
    """
    Extract exact geometrical and physical properties from a CadQuery result.
    Computes bounding box, volume, area, center of mass, and estimated masses.
    """
    try:
        if isinstance(result, cq.Assembly):
            shape = result.toCompound()
        elif hasattr(result, "val"):
            shape = result.val()
        else:
            shape = result

        bb = shape.BoundingBox()
        volume_mm3 = float(shape.Volume())
        volume_cm3 = volume_mm3 / 1000.0
        area_mm2 = float(shape.Area())
        area_cm2 = area_mm2 / 100.0
        center = shape.Center().toTuple()

        # Densities in g/cm3
        mass_steel_g = volume_cm3 * 7.85
        mass_alu_g = volume_cm3 * 2.70
        mass_pla_g = volume_cm3 * 1.25
        mass_titanium_g = volume_cm3 * 4.51

        return {
            "bbox_x": round(bb.xlen, 2),
            "bbox_y": round(bb.ylen, 2),
            "bbox_z": round(bb.zlen, 2),
            "volume_mm3": round(volume_mm3, 1),
            "volume_cm3": round(volume_cm3, 2),
            "area_mm2": round(area_mm2, 1),
            "area_cm2": round(area_cm2, 2),
            "center": (round(center[0], 2), round(center[1], 2), round(center[2], 2)),
            "mass_steel_g": round(mass_steel_g, 1),
            "mass_alu_g": round(mass_alu_g, 1),
            "mass_pla_g": round(mass_pla_g, 1),
            "mass_titanium_g": round(mass_titanium_g, 1),
        }
    except Exception as exc:
        return {
            "bbox_x": 0.0,
            "bbox_y": 0.0,
            "bbox_z": 0.0,
            "volume_mm3": 0.0,
            "volume_cm3": 0.0,
            "area_mm2": 0.0,
            "area_cm2": 0.0,
            "center": (0.0, 0.0, 0.0),
            "mass_steel_g": 0.0,
            "mass_alu_g": 0.0,
            "mass_pla_g": 0.0,
            "mass_titanium_g": 0.0,
            "error": str(exc),
        }


def strip_failing_chamfer_fillet(code: str) -> str:
    """
    Remove risky or failing .chamfer() and .fillet() operations from CadQuery code.
    Fixes OpenCASCADE StdFail_NotDone / BRep_API: command not done on gears, sprockets, etc.
    """
    c = re.sub(
        r'^\s*(?:result\s*=\s*)?result\s*\.(?:edges\([^\)]*\)\s*\.\s*)?(?:chamfer|fillet)\([^\)]*\)\s*$',
        '',
        code,
        flags=re.MULTILINE,
    )
    c = re.sub(r'\.(?:edges\([^\)]*\)\s*\.\s*)?(?:chamfer|fillet)\([^\)]*\)', '', c)
    return c


def execute_cadquery_code(code: str):
    """
    Safely execute generated CadQuery code in an isolated namespace.
    Ensures syntax sanitization and indentation normalization before execution.
    Returns the `result` object.
    Raises RuntimeError on failure.
    """
    code = sanitize_cadquery_code(code)
    code = fix_code_indentation(code)
    namespace: dict = {"cq": cq, "math": __import__("math")}
    try:
        exec(code, namespace)  # noqa: S102
    except Exception as exc:
        raise RuntimeError(
            f"CadQuery code execution failed:\n{exc}\n\nGenerated Code:\n{code}"
        ) from exc

    if "result" not in namespace:
        raise RuntimeError(
            f"Generated code did not define a `result` variable.\n\nCode:\n{code}"
        )
    return namespace["result"]


def export_step(result, output_path: str) -> None:
    """Export a CadQuery result to a STEP file (CATIA / SolidWorks compatible)."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    if isinstance(result, cq.Assembly):
        result.save(output_path)
    else:
        cq.exporters.export(result, output_path)


def export_stl(result, output_path: str) -> None:
    """Export a CadQuery result to an STL file (used for 3D preview)."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    if isinstance(result, cq.Assembly):
        cq.exporters.export(result.toCompound(), output_path)
    else:
        cq.exporters.export(result, output_path)


def generate_part_from_code(code: str, step_output_path: str, stl_output_path: str) -> tuple:
    """
    Directly execute CadQuery code, export STEP and STL files, and compute geometric properties.
    Includes automated fallback if decorative chamfer/fillet crashes OpenCASCADE.
    Returns (code, step_output_path, properties_dict).
    """
    try:
        result = execute_cadquery_code(code)
        working_code = code
    except Exception as exc:
        err_str = str(exc).lower()
        if ("brep_api: command not done" in err_str or "stdfail_notdone" in err_str) and (
            "chamfer" in code or "fillet" in code
        ):
            working_code = strip_failing_chamfer_fillet(code)
            result = execute_cadquery_code(working_code)
        else:
            raise

    export_step(result, step_output_path)
    export_stl(result, stl_output_path)
    props = get_part_properties(result)
    return working_code, step_output_path, props


def repair_cadquery_code(
    original_code: str,
    error_message: str,
    description: str,
    api_key: str,
    model_name: str = None,
) -> str:
    """
    Ask Gemini to fix failing CadQuery code using the exact execution error traceback
    and CadQuery-specific domain diagnostic hints.
    """
    diagnostic_hints = []
    err_lower = error_message.lower()

    if "has no attribute 'arc'" in err_lower or ("attributeerror" in err_lower and "arc" in err_lower):
        diagnostic_hints.append(
            "• CRITICAL: CadQuery Workplane has NO .arc() method! "
            "To round top edges or ends, use 3D fillets: .edges('>Z and |Y').fillet(radius) or .edges('|Y').fillet(radius), "
            "or .threePointArc(p1, p2), or combine with cylinders."
        )
    if "centerpoint" in err_lower:
        diagnostic_hints.append(
            "• CRITICAL: .workplane() takes NO centerPoint argument. "
            "To shift the origin, call .center(x, y) after .workplane()."
        )
    if "fontsize" in err_lower:
        diagnostic_hints.append(
            "• CRITICAL: In .text(), the parameter is 'fontsize' (all lowercase), NOT 'fontSize'."
        )
    if "depth" in err_lower and "unexpected keyword" in err_lower:
        diagnostic_hints.append(
            "• CRITICAL: In .text(), the parameter is 'distance' (negative for engraving cut depth, e.g. distance=-0.6), NOT 'depth'."
        )
    if "unexpected indent" in err_lower or "indentationerror" in err_lower:
        diagnostic_hints.append(
            "• CRITICAL: All top-level code (imports, variable assignments, result =) MUST have ZERO indentation (column 0)."
        )
    if "combine=true" in err_lower:
        diagnostic_hints.append(
            "• CRITICAL: .box() on a new Workplane cannot use combine=True because there is no prior solid to combine with."
        )
    if "brep_api: command not done" in err_lower or "stdfail_notdone" in err_lower:
        diagnostic_hints.append(
            "• CRITICAL: 'BRep_API: command not done' is caused by .chamfer() or .fillet() on complex or intersecting edges "
            "(such as .edges('|Z') on gears, teeth, sprockets, splines, or multi-vertex polygons). "
            "REMOVE all .chamfer() and .fillet() calls from the code to let the core solid geometry compile cleanly."
        )

    hints_str = "\n".join(diagnostic_hints)
    if hints_str:
        hints_section = f"\nCADQUERY REPAIR GUIDELINES:\n{hints_str}\n"
    else:
        hints_section = ""

    repair_prompt = (
        f"The following CadQuery code was generated for the part description: '{description}'\n"
        f"However, executing it caused this error:\n"
        f"--- ERROR ---\n{error_message}\n\n"
        f"{hints_section}\n"
        f"--- FAILED CODE ---\n{original_code}\n\n"
        "Please fix the CadQuery code so it executes cleanly and produces the exact requested mechanical part.\n"
        "STRICT RULES:\n"
        "1. Output a single ```python ... ``` block with ONLY clean, runnable Python code.\n"
        "2. Store the final geometry in variable `result`.\n"
        "3. Output ONE single coherent script without scratch attempts."
    )
    return description_to_cadquery_code(repair_prompt, api_key, model_name=model_name)


def generate_part(
    description: str,
    api_key: str,
    step_output_path: str,
    stl_output_path: str,
    model_name: str = None,
    force_demo: bool = False,
) -> tuple:
    """
    Full pipeline: description -> Gemini AI -> CadQuery code -> STEP + STL files + properties.
    Falls back to pre-compiled models if force_demo=True or if api_key is missing/placeholder.
    Includes automatic AI self-repair if initial execution produces an error.
    Returns (cadquery_code, step_path, properties_dict).
    """
    global _LAST_USED_MODEL

    # Check for demo mode / preset match
    is_placeholder_key = not api_key or "your_" in api_key.lower() or api_key.strip() == ""
    preset_name, preset_code = find_matching_preset(description)

    if force_demo or (is_placeholder_key and preset_code):
        if not preset_code:
            preset_name = "Plaque percée"
            preset_code = PRESET_EXAMPLES[preset_name]["code"]
        _LAST_USED_MODEL = f"Mode Démo ({preset_name})"
        return generate_part_from_code(preset_code, step_output_path, stl_output_path)

    if is_placeholder_key:
        raise RuntimeError(
            "Aucune clé API Gemini valide n'est configurée dans .env ou dans la barre latérale. "
            "Vous pouvez utiliser le bouton '⚡ Mode Démo' pour tester les pièces prédéfinies sans clé API, "
            "ou configurer votre clé sur https://aistudio.google.com/."
        )

    code = description_to_cadquery_code(description, api_key, model_name=model_name)
    try:
        return generate_part_from_code(code, step_output_path, stl_output_path)
    except Exception as exc:
        # Attempt AI self-repair
        try:
            repaired_code = repair_cadquery_code(
                original_code=code,
                error_message=str(exc),
                description=description,
                api_key=api_key,
                model_name=model_name,
            )
            res = generate_part_from_code(repaired_code, step_output_path, stl_output_path)
            _LAST_USED_MODEL = f"{_LAST_USED_MODEL} (auto-corrigé)"
            return res
        except Exception as repair_exc:
            raise RuntimeError(
                f"Erreur d'exécution CadQuery : {exc}\n\n"
                f"(Tentative d'auto-correction IA échouée : {repair_exc})"
            ) from exc


