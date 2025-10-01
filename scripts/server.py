# scripts/server.py
import os
import sys
import json
import subprocess
import tempfile
import re
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, abort
from flask_cors import CORS


PROJECT_ROOT = Path(__file__).resolve().parents[1]
app = Flask(__name__, static_folder=None)

# Allow cross-origin requests from anywhere (dev). For production, restrict origins:
CORS(
    app,
    resources={
        r"/*": {"origins": ["https://gentle-field-0b0b1760f.1.azurestaticapps.net"]}
    },
)


# prefer explicit env var, otherwise use running interpreter
PYTHON_EXE = os.getenv("PYTHON_PATH") or sys.executable

# safe directories to serve (relative to project root)
ALLOWED_ASSET_DIRS = ["renders", "output", "temp", "scripts"]


def _run_cmd(cmd, cwd=PROJECT_ROOT):
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def _find_saved_path(stdout, stderr, design_id=None):
    # look for common "Saved:" or "Saved showcase image:" messages
    combined = (stdout or "") + "\n" + (stderr or "")
    m = re.search(r"Saved(?::| .*?:)\s*(.+\.(?:png|jpg|jpeg|mp4))", combined, re.I)
    if m:
        return Path(m.group(1).strip())
    # fallback: check output/renders for files matching design_id
    if design_id:
        for d in ("renders", "output"):
            p = PROJECT_ROOT / d
            if p.exists():
                for f in sorted(
                    p.glob(f"{design_id}*"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                ):
                    if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".mp4"):
                        return f
    return None


def _public_url_for_path(path_obj, req):
    # path_obj is absolute or relative to project root
    try:
        rel = Path(path_obj).resolve().relative_to(PROJECT_ROOT)
    except Exception:
        rel = Path(path_obj)
    # only allow known directories
    for allowed in ALLOWED_ASSET_DIRS:
        if str(rel).replace("\\", "/").startswith(allowed + "/") or str(rel) == allowed:
            rel_path = str(rel).replace("\\", "/")
            return f"{req.scheme}://{req.host}/assets/{rel_path}"

    return None


@app.route("/assets/<path:rel_path>", methods=["GET"])
def serve_assets(rel_path):
    # prevent traversal
    safe = os.path.normpath(rel_path).lstrip(os.sep).replace("..", "")
    # only allow allowed dirs
    for allowed in ALLOWED_ASSET_DIRS:
        if safe.startswith(allowed + os.sep) or safe == allowed:
            full = PROJECT_ROOT / safe
            if full.exists() and full.is_file():
                return send_from_directory(str(PROJECT_ROOT), safe, as_attachment=False)
    abort(404)


@app.route("/flatlay-render", methods=["POST"])
def flatlay_render():
    body = request.get_json() or {}
    design = body.get("design") or body
    # write to temp design file
    td = tempfile.mkdtemp()
    design_path = Path(td) / f"{design.get('design_id','design')}.design.json"
    design_path.write_text(
        json.dumps(design, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # call your render_utils.py CLI
    cmd = [
        PYTHON_EXE,
        str(PROJECT_ROOT / "scripts" / "render_utils.py"),
        "--input",
        str(design_path),
        "--variant",
        "flatlay",
    ]
    code, out, err = _run_cmd(cmd)
    if code != 0:
        return jsonify(success=False, raw_stdout=out, raw_stderr=err), 500
    saved = _find_saved_path(out, err, design_id=design.get("design_id"))
    if not saved:
        return jsonify(success=False, raw_stdout=out, raw_stderr=err), 500
    public = _public_url_for_path(saved, request)
    return jsonify(
        success=True, imageUrl=public, message="Flatlay render generated successfully"
    )


@app.route("/virtual-showcase", methods=["POST"])
def virtual_showcase():
    body = request.get_json() or {}
    design = body.get("design")
    modelConfig = body.get("modelConfig") or body.get("model_attrs") or {}
    reference = body.get("reference")  # may be absolute URL
    if not design:
        return jsonify(success=False, error="missing design"), 400
    td = tempfile.mkdtemp()
    design_path = Path(td) / f"{design.get('design_id','design')}.design.json"
    design_path.write_text(
        json.dumps(design, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    args = [
        PYTHON_EXE,
        str(PROJECT_ROOT / "scripts" / "agent3_virtual_showcase_demo.py"),
        "--design",
        str(design_path),
        "--model-attrs",
        json.dumps(modelConfig),
        "--out-dir",
        str(PROJECT_ROOT / "output"),
    ]
    if reference:
        args += ["--reference", reference]
    code, out, err = _run_cmd(args)
    if code != 0:
        return jsonify(success=False, raw_stdout=out, raw_stderr=err), 500
    saved = _find_saved_path(out, err, design_id=design.get("design_id"))
    if not saved:
        # try output dir pattern
        possible = Path(PROJECT_ROOT / "output").glob(
            f"{design.get('design_id','design')}*showcase*.png"
        )
        for f in possible:
            saved = f
            break
    if not saved:
        return jsonify(success=False, raw_stdout=out, raw_stderr=err), 500
    public = _public_url_for_path(saved, request)
    return jsonify(
        success=True, imageUrl=public, message="Virtual showcase generated successfully"
    )


@app.route("/runway", methods=["POST"])
def runway():
    body = request.get_json() or {}
    design = body.get("design")
    modelConfig = body.get("modelConfig") or {}
    reference = body.get("reference")
    if not design:
        return jsonify(success=False, error="missing design"), 400
    td = tempfile.mkdtemp()
    design_path = Path(td) / f"{design.get('design_id','design')}.design.json"
    design_path.write_text(
        json.dumps(design, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    args = [
        PYTHON_EXE,
        str(PROJECT_ROOT / "scripts" / "agent3_runway_demo.py"),
        "--design",
        str(design_path),
        "--model-attrs",
        json.dumps(modelConfig),
        "--out-dir",
        str(PROJECT_ROOT / "output"),
    ]
    if reference:
        args += ["--reference", reference]
    code, out, err = _run_cmd(args)
    if code != 0:
        return jsonify(success=False, raw_stdout=out, raw_stderr=err), 500
    saved = _find_saved_path(out, err, design_id=design.get("design_id"))
    if not saved:
        # try output dir for mp4
        possible = Path(PROJECT_ROOT / "output").glob(
            f"{design.get('design_id','design')}*runway*.mp4"
        )
        for f in possible:
            saved = f
            break
    if not saved:
        return jsonify(success=False, raw_stdout=out, raw_stderr=err), 500
    public = _public_url_for_path(saved, request)
    return jsonify(
        success=True, videoUrl=public, message="Runway video generated successfully"
    )


@app.route("/apply-change", methods=["POST"])
def apply_change():
    body = request.get_json() or {}
    design = body.get("design")
    textChange = body.get("textChange") or body.get("changeText") or ""
    if not design or not textChange:
        return jsonify(success=False, error="missing design or change text"), 400
    td = tempfile.mkdtemp()
    design_path = Path(td) / f"{design.get('design_id','design')}.design.json"
    change_path = Path(td) / "change.txt"
    design_path.write_text(
        json.dumps(design, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    change_path.write_text(textChange, encoding="utf-8")
    args = [
        PYTHON_EXE,
        str(PROJECT_ROOT / "scripts" / "apply_text_change.py"),
        str(design_path),
        str(change_path),
    ]
    code, out, err = _run_cmd(args)
    if code != 0:
        return jsonify(success=False, raw_stdout=out, raw_stderr=err), 500
    # script prints "Wrote: <path>" — try to parse stdout
    m = re.search(r"Wrote:\s*(.*)", out)
    if m:
        modified = m.group(1).strip()
        try:
            with open(modified, "r", encoding="utf-8") as fh:
                parsed = json.load(fh)
                return jsonify(
                    success=True, design=parsed, message="Design updated successfully"
                )
        except Exception:
            pass
    # fallback: try to parse stdout as JSON
    try:
        parsed = json.loads(out.strip())
        return jsonify(
            success=True, design=parsed, message="Design updated from stdout"
        )
    except Exception:
        return jsonify(success=False, raw_stdout=out, raw_stderr=err), 500


@app.route("/")
def index():
    return jsonify(
        {
            "status": "ok",
            "message": "Fashion API is running",
            "endpoints": [
                "/flatlay-render",
                "/virtual-showcase",
                "/runway",
                "/apply-change",
                "/assets/<path>",
            ],
        }
    )


@app.route("/trends", methods=["GET"])
def get_trends():
    try:
        # Load the same trends_index.json your route.ts was using
        trends_file = PROJECT_ROOT / "trends_index.json"
        if trends_file.exists():
            with open(trends_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return jsonify(data)
        else:
            # fallback sample data (same as in your route.ts)
            fallback_data = {
                "generated_at": "2025-09-24T12:24:33.444177+00:00",
                "records_count": 1410,
                "top_by_category": {
                    "colors": [
                        "brown",
                        "white",
                        "grey",
                        "cream",
                        "black",
                        "red",
                        "olive",
                        "beige",
                        "blue",
                        "pink",
                    ],
                    "fabrics": [
                        "cotton",
                        "silk",
                        "linen",
                        "satin",
                        "chiffon",
                        "lace",
                        "denim",
                        "rayon",
                        "chikankari",
                        "crepe",
                    ],
                    "prints": [
                        "embroidery",
                        "solids / minimalist",
                        "florals",
                        "bandhani",
                        "ikat",
                        "block print",
                        "geometric",
                        "paisley",
                        "polka dot",
                        "floral",
                    ],
                    "silhouettes": [
                        "Draped/Flowing",
                        "A-line",
                        "Tailored",
                        "Fit-and-flare",
                        "sheath",
                        "Bodycon/Fitted",
                        "anarkali",
                        "Oversized/Baggy",
                        "slip dress",
                        "asymmetric",
                    ],
                    "sleeves": [
                        "Full sleeves",
                        "Sleeveless/Tank",
                        "short sleeve",
                        "3/4th sleeves",
                        "kimono sleeve",
                        "bell sleeve",
                    ],
                    "necklines": [
                        "Crew neck",
                        "V-neck",
                        "Collared",
                        "Halter",
                        "Square neck",
                        "Sweetheart neck",
                        "Off-shoulder",
                        "Asymmetrical/One-shoulder",
                        "Cowl neck",
                    ],
                    "garment_types": [
                        "dress",
                        "kurta",
                        "kurta-set",
                        "coord set",
                        "top",
                        "shirt",
                        "lehenga",
                        "sari",
                        "jacket",
                        "skirt",
                    ],
                    "lengths": [
                        "Full-length",
                        "Midi",
                        "Mini",
                        "Ankle-length",
                        "Maxi",
                        "Cropped",
                        "Knee-length",
                    ],
                },
                "top_combos": [
                    {"combo": "color:brown | color:white", "weight": 329},
                    {"combo": "color:grey | color:white", "weight": 260},
                    {"combo": "color:white | garment:dress", "weight": 240},
                    {"combo": "color:white | print:solids / minimalist", "weight": 239},
                    {"combo": "color:red | color:white", "weight": 199},
                ],
                "trend_entries": [
                    {
                        "trend_id": "fabric:cotton",
                        "type": "fabric",
                        "canonical": "cotton",
                        "count": 282,
                        "score": 1.18,
                    },
                    {
                        "trend_id": "print:embroidery",
                        "type": "print",
                        "canonical": "embroidery",
                        "count": 285,
                        "score": 1.12,
                    },
                    {
                        "trend_id": "print:solids / minimalist",
                        "type": "print",
                        "canonical": "solids / minimalist",
                        "count": 397,
                        "score": 1.11,
                    },
                    {
                        "trend_id": "color:brown",
                        "type": "color",
                        "canonical": "brown",
                        "count": 580,
                        "score": 1.09,
                    },
                    {
                        "trend_id": "color:white",
                        "type": "color",
                        "canonical": "white",
                        "count": 804,
                        "score": 1.05,
                    },
                ],
            }
            return jsonify(fallback_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # run dev server
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=False)
