# scripts/server.py
import os
import sys
import json
import subprocess
import tempfile
import re
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, abort

PROJECT_ROOT = Path(__file__).resolve().parents[1]
app = Flask(__name__, static_folder=None)

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


if __name__ == "__main__":
    # run dev server
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")), debug=False)
