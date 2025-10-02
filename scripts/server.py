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
import requests
import uuid
from datetime import datetime
from shutil import which
from typing import Optional
import imageio_ffmpeg


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


def _make_runway_from_flatlay(flatlay_url, out_dir):
    """
    Download flatlay_url to a temp file, run ffmpeg (via imageio-ffmpeg binary)
    to create a short panning/zooming mp4, and return the output path.
    """
    import tempfile, os, time

    # create output dir
    out_dir_path = Path(out_dir)
    out_dir_path.mkdir(parents=True, exist_ok=True)

    # Download the flatlay (support http(s) URLs)
    r = requests.get(flatlay_url, stream=True, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Failed to download flatlay ({r.status_code})")

    td = Path(tempfile.mkdtemp(prefix="flatlay_"))
    in_file = td / f"flatlay_{uuid.uuid4().hex}.png"
    with open(in_file, "wb") as fh:
        for chunk in r.iter_content(8192):
            if chunk:
                fh.write(chunk)

    # choose output path
    out_file = out_dir_path / f"runway_{uuid.uuid4().hex}.mp4"

    # find ffmpeg binary shipped with imageio-ffmpeg
    ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()

    # ffmpeg filter: scale then gentle zoompan for 6s at 30fps (180 frames)
    # note: zoompan expression must be escaped when passed to shell; we'll use shlex.split
    filter_complex = (
        "scale=1280:-2,zoompan="
        "z='zoom+0.0008':"
        "x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':"
        "d=180:s=1280x720,"
        "fps=30,format=yuv420p"
    )

    cmd = [
        ffmpeg_bin,
        "-y",
        "-loop",
        "1",
        "-i",
        str(in_file),
        "-filter_complex",
        filter_complex,
        "-t",
        "6",
        "-movflags",
        "+faststart",
        str(out_file),
    ]

    # run ffmpeg
    try:
        proc = subprocess.run(
            cmd, check=True, capture_output=True, text=True, timeout=120
        )
    except subprocess.CalledProcessError as e:
        # include ffmpeg stdout/stderr for debugging
        raise RuntimeError(f"ffmpeg failed: {e.returncode}\n{e.stdout}\n{e.stderr}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("ffmpeg timed out")

    if not out_file.exists():
        raise RuntimeError("ffmpeg did not produce output")

    return str(out_file)


def get_python_executable():
    # Windows venv path
    win_venv = PROJECT_ROOT / "scripts" / "venv" / "Scripts" / "python.exe"
    posix_venv = PROJECT_ROOT / "scripts" / "venv" / "bin" / "python"
    if win_venv.exists():
        return str(win_venv)
    if posix_venv.exists():
        return str(posix_venv)
    # fallbacks
    candidate = os.getenv("PYTHON_PATH")
    if candidate:
        return candidate
    # look for commonly named binaries
    for p in ("python3.10", "python3.9", "python3", "python"):
        which_p = which(p)
        if which_p:
            return which_p
    return sys.executable


# helper: extract first balanced JSON object/array from text
def extract_first_json(text: str) -> Optional[str]:
    if not text:
        return None
    start_obj = text.find("{")
    start_arr = text.find("[")
    if start_obj == -1 and start_arr == -1:
        return None
    # choose earliest open bracket
    if start_obj == -1:
        start = start_arr
    elif start_arr == -1:
        start = start_obj
    else:
        start = min(start_obj, start_arr)

    open_ch = text[start]
    close_ch = "}" if open_ch == "{" else "]"
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
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


# helper: run render_utils and return public image URL (or error)
def _render_flatlay_for_design(design: dict, req):
    """
    Writes design -> temp file, calls render_utils.py (variant=flatlay),
    finds saved image and returns (image_url, error_string).
    """
    try:
        td = tempfile.mkdtemp()
        design_path = Path(td) / f"{design.get('design_id','design')}.design.json"
        design_path.write_text(
            json.dumps(design, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        python_exec = get_python_executable()
        cmd = [
            python_exec,
            str(PROJECT_ROOT / "scripts" / "render_utils.py"),
            "--input",
            str(design_path),
            "--variant",
            "flatlay",
        ]
        app.logger.info("Running render command: %s", " ".join(cmd))
        rc, out, err = _run_cmd(cmd)
        app.logger.debug(
            "render_utils rc=%s stdout_len=%s stderr_len=%s",
            rc,
            len(out or ""),
            len(err or ""),
        )

        if rc != 0:
            return None, f"render_utils failed (rc={rc}): {err[:2000] or out[:2000]}"

        saved = _find_saved_path(out, err, design_id=design.get("design_id"))
        if not saved:
            return None, "render_utils finished but no saved image path found."

        public = _public_url_for_path(saved, req)
        if not public:
            return None, "Saved file is outside allowed asset directories."

        return public, None

    except Exception as e:
        app.logger.exception("Exception in _render_flatlay_for_design: %s", e)
        return None, f"exception while rendering flatlay: {str(e)}"


# main route: generate design from payload OR use provided design, then render flatlay and return imageUrl
@app.route("/generate-design", methods=["POST"])
def generate_design():
    """
    Accepts payload similar to your Next.js route:
    { description, colors, fabrics, prints, garmentType, silhouette, sleeves, neckline, trims, variants }
    If generator script exists it will be invoked; fallback produces a simple design dict.
    After design is obtained, it immediately renders a flatlay via render_utils.py and returns:
      { success: true, design: {...}, imageUrl: "https://.../assets/..." }
    """
    try:
        body = request.get_json() or {}

        # if frontend supplied an already-built design object, use it
        if body.get("design"):
            design = body.get("design")
        else:
            # Build payload similar to Next.js helper
            user_content = {
                "colors": body.get("colors", []),
                "fabrics": body.get("fabrics", []),
                "prints": body.get("prints", []),
                "garment_type": body.get("garmentType") or body.get("garment_type"),
                "silhouette": body.get("silhouette"),
                "sleeves": body.get("sleeves"),
                "neckline": body.get("neckline"),
                "trims_and_details": ([body.get("trims")] if body.get("trims") else []),
                "variants": body.get("variants", 1),
                "description": body.get("description", "") or "",
                "user_override_prompt": body.get("description", "") or "",
            }

            payload = {
                "id": str(uuid.uuid4()),
                "user_content": user_content,
                "system_prompt": "You are a fashion product design assistant. Respond ONLY with valid JSON (no extra explanation).",
            }

            # write payload to a temp file that generator can read
            temp_dir = PROJECT_ROOT / "temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            payload_path = (
                temp_dir / f"payload_{int(datetime.utcnow().timestamp())}.json"
            )
            payload_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            # attempt to run generator script (if available). Use your real generator script path/name.
            # If you have a different generator script, change the name below.
            gen_script = (
                PROJECT_ROOT / "scripts" / "test_agent2_payload.py"
            )  # replace if you have a real generator
            design = None
            if gen_script.exists():
                python_exec = get_python_executable()
                cmd = [python_exec, str(gen_script), str(payload_path)]
                app.logger.info("Running generator: %s", " ".join(cmd))
                proc = subprocess.run(
                    cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True
                )
                out = proc.stdout or ""
                err = proc.stderr or ""
                if proc.returncode == 0:
                    extracted = extract_first_json(out)
                    if extracted:
                        try:
                            parsed = json.loads(extracted)
                            # generator may return an array or object
                            if isinstance(parsed, list) and parsed:
                                design = parsed[0]
                            else:
                                design = parsed
                        except Exception as e:
                            app.logger.exception(
                                "Failed to parse JSON from generator stdout: %s", e
                            )
                            design = None
                    else:
                        app.logger.warning(
                            "No JSON found in generator stdout; stdout head: %s",
                            (out[:800] + "...") if out else "<empty>",
                        )
                else:
                    app.logger.error(
                        "Generator script failed (code=%s): %s",
                        proc.returncode,
                        err[:2000] or out[:2000],
                    )

            # fallback simple design if generator not present or parse failed
            if not design:
                design_id = f"design-{uuid.uuid4().hex[:8]}"
                now = datetime.utcnow().isoformat() + "Z"
                design = {
                    "design_id": design_id,
                    "generated_at": now,
                    "design_text": payload["user_content"].get(
                        "description", "Auto-generated look"
                    ),
                    "colors": payload["user_content"].get("colors", [])[:5],
                    "fabrics": payload["user_content"].get("fabrics", [])[:5],
                    "prints_patterns": payload["user_content"].get("prints", [])[:5],
                    "garment_type": payload["user_content"].get("garment_type")
                    or "dress",
                    "silhouette": payload["user_content"].get("silhouette") or "A-line",
                }

        # render immediate flatlay
        image_url, render_err = _render_flatlay_for_design(design, request)

        result = {"success": True, "design": design}
        if image_url:
            result["imageUrl"] = image_url
        else:
            result["renderError"] = render_err

        return jsonify(result)

    except Exception as e:
        app.logger.exception("generate-design unexpected error: %s", e)
        return jsonify(success=False, error=str(e)), 500


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
    reference = body.get("reference")  # may be absolute URL or null

    if not design:
        return jsonify(success=False, error="missing design"), 400

    # write design json to a temp file for the agent script
    td = tempfile.mkdtemp()
    design_path = Path(td) / f"{design.get('design_id','design')}.design.json"
    design_path.write_text(
        json.dumps(design, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # If reference is a remote URL, download it to a temp file so the agent can access it
    downloaded_reference = None
    try:
        if (
            reference
            and isinstance(reference, str)
            and reference.lower().startswith("http")
        ):
            # download remote image (with timeout and streaming)
            try:
                r = requests.get(reference, stream=True, timeout=60)
                r.raise_for_status()
                # save to temp file
                ext = ".png"
                # try to detect extension from content-type
                ctype = r.headers.get("Content-Type", "").lower()
                if "jpeg" in ctype:
                    ext = ".jpg"
                fd, tmp_path = tempfile.mkstemp(suffix=ext, prefix="ref_", dir=td)
                os.close(fd)
                with open(tmp_path, "wb") as fh:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            fh.write(chunk)
                downloaded_reference = tmp_path
            except Exception as e:
                # log and continue: we may still call the agent without a reference
                print(
                    f"[virtual_showcase] failed to download reference {reference}: {e}",
                    file=sys.stderr,
                )
                downloaded_reference = None

    except Exception as e:
        print(
            "[virtual_showcase] unexpected error while handling reference:",
            e,
            file=sys.stderr,
        )

    # Build agent args; pass --reference <path> only if downloaded_reference available
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
    if downloaded_reference:
        args += ["--reference", str(downloaded_reference)]
    elif reference:
        # If reference was given but couldn't be downloaded, still include it (agent may accept URL)
        args += ["--reference", reference]

    # run the agent script
    code, out, err = _run_cmd(args)
    # log for diagnostics
    print("[virtual_showcase] agent exit code:", code, file=sys.stderr)
    print("[virtual_showcase] stdout (truncated):", (out or "")[:3000], file=sys.stderr)
    print("[virtual_showcase] stderr (truncated):", (err or "")[:3000], file=sys.stderr)

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

    # If a reference flatlay URL is provided, use the deterministic ffmpeg fallback
    # to create a runway-video that matches the flatlay exactly.
    if reference:
        try:
            out_file = _make_runway_from_flatlay(
                reference, str(PROJECT_ROOT / "output")
            )
            public = _public_url_for_path(out_file, request)
            return jsonify(
                success=True,
                videoUrl=public,
                message="Runway video generated from flatlay (ffmpeg fallback)",
            )
        except Exception as e:
            # If ffmpeg fallback fails, log and fall through to the original pipeline
            # (so you still have a chance to use the heavy generator)
            # Keep the error accessible for debugging
            err_msg = str(e)
            print("ffmpeg fallback error:", err_msg, file=sys.stderr)
            # continue to original path below (optional)


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

    # parse updated JSON
    updated = None
    try:
        m = re.search(r"Wrote:\s*(.*)", out)
        if m:
            with open(m.group(1).strip(), "r", encoding="utf-8") as fh:
                updated = json.load(fh)
        else:
            updated = json.loads(out.strip())
    except Exception as e:
        return (
            jsonify(
                success=False,
                error=f"Failed to parse updated design: {e}",
                raw_stdout=out,
            ),
            500,
        )

    # ✅ Immediately generate a new flatlay
    flatlay_cmd = [
        PYTHON_EXE,
        str(PROJECT_ROOT / "scripts" / "render_utils.py"),
        "--input",
        str(design_path),
        "--variant",
        "flatlay",
    ]
    code2, out2, err2 = _run_cmd(flatlay_cmd)
    if code2 != 0:
        return (
            jsonify(success=False, design=updated, raw_stdout=out2, raw_stderr=err2),
            500,
        )

    saved = _find_saved_path(out2, err2, design_id=updated.get("design_id"))
    image_url = _public_url_for_path(saved, request) if saved else None

    return jsonify(
        success=True,
        design=updated,
        flatlay=image_url,
        message="Design updated and flatlay regenerated",
    )


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
