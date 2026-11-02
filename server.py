"""
3D CAD Studio — FastAPI Server
Serves the modern JavaScript/Three.js frontend and exposes REST APIs for:
  • Prompt-to-CAD generation via Google Gemini
  • Direct CadQuery geometry evaluation & repair
  • B-Rep physical metrology computation
  • STEP / STL file downloads
"""

import os
import base64
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

from cad_generator import (
    generate_part,
    generate_part_from_code,
    PRESET_EXAMPLES,
)

load_dotenv()

# Setup paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
os.makedirs(OUTPUT_DIR, exist_ok=True)

DEFAULT_STEP_PATH = os.path.join(OUTPUT_DIR, "piece.step")
DEFAULT_STL_PATH = os.path.join(OUTPUT_DIR, "piece.stl")

app = FastAPI(
    title="3D CAD Studio API",
    description="CAD generation and physical analysis service powered by CadQuery & Gemini",
    version="2.0.0",
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic Request Models ─────────────────────────────────────────────────
class GenerateRequest(BaseModel):
    prompt: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    preset_name: Optional[str] = None


class RecalculateRequest(BaseModel):
    code: str


# ── Helper functions ────────────────────────────────────────────────────────
def read_stl_as_base64(path: str) -> str:
    if os.path.exists(path):
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    return ""


# ── API Endpoints ───────────────────────────────────────────────────────────
@app.get("/api/health")
def health_check():
    return {"status": "ok", "app": "3D CAD Studio"}


@app.get("/api/presets")
def get_presets():
    """Returns available mechanical preset examples."""
    return PRESET_EXAMPLES


@app.post("/api/generate")
def api_generate(req: GenerateRequest):
    """
    Generate a CAD model from a natural-language description or a preset name.
    """
    try:
        # If preset requested, directly compile from preset code
        if req.preset_name and req.preset_name in PRESET_EXAMPLES:
            preset_code = PRESET_EXAMPLES[req.preset_name]["code"]
            code, step_path, props = generate_part_from_code(
                code=preset_code,
                step_output_path=DEFAULT_STEP_PATH,
                stl_output_path=DEFAULT_STL_PATH,
            )
        else:
            api_key = req.api_key.strip() if req.api_key else ""
            if not api_key:
                api_key = os.getenv("GEMINI_API_KEY", "")

            code, step_path, props = generate_part(
                description=req.prompt or "",
                api_key=api_key,
                step_output_path=DEFAULT_STEP_PATH,
                stl_output_path=DEFAULT_STL_PATH,
                model_name=req.model,
                force_demo=False,
            )

        stl_b64 = read_stl_as_base64(DEFAULT_STL_PATH)

        return {
            "success": True,
            "code": code,
            "properties": props,
            "stl_base64": stl_b64,
            "step_download_url": "/api/download/step",
            "stl_download_url": "/api/download/stl",
        }
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": str(exc)},
        )


@app.post("/api/recalculate")
def api_recalculate(req: RecalculateRequest):
    """
    Recalculate 3D geometry directly from edited CadQuery Python code.
    """
    try:
        code, step_path, props = generate_part_from_code(
            code=req.code,
            step_output_path=DEFAULT_STEP_PATH,
            stl_output_path=DEFAULT_STL_PATH,
        )

        stl_b64 = read_stl_as_base64(DEFAULT_STL_PATH)

        return {
            "success": True,
            "code": code,
            "properties": props,
            "stl_base64": stl_b64,
            "step_download_url": "/api/download/step",
            "stl_download_url": "/api/download/stl",
        }
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": str(exc)},
        )


@app.get("/api/download/step")
def download_step():
    """Download current CAD geometry as standard STEP AP203/214 file."""
    if not os.path.exists(DEFAULT_STEP_PATH):
        raise HTTPException(status_code=404, detail="No STEP file generated yet.")
    return FileResponse(
        path=DEFAULT_STEP_PATH,
        filename="piece.step",
        media_type="application/octet-stream",
    )


@app.get("/api/download/stl")
def download_stl():
    """Download current 3D geometry as STL mesh for 3D printing."""
    if not os.path.exists(DEFAULT_STL_PATH):
        raise HTTPException(status_code=404, detail="No STL file generated yet.")
    return FileResponse(
        path=DEFAULT_STL_PATH,
        filename="piece.stl",
        media_type="model/stl",
    )


# ── Mount Frontend Static Files at Root ─────────────────────────────────────
if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8501))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)
