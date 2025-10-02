#!/usr/bin/env python3
"""
agent3_virtual_showcase_demo.py (modern google-genai only)

Generate a photorealistic virtual showcase image with Gemini (google-genai).
This simplified script expects the new `google-genai` package and uses:
    from google import genai
and client.models.generate_content(model=..., contents=[prompt], generation_config=...)

Usage:
  python scripts/agent3_virtual_showcase_demo.py --design output/agent2_designs/FL001.design.json \
      --model-attrs '{"gender":"female","body_type":"curvy"}' --out-dir output
"""
import os
import sys
import json
import argparse
import random
import base64
import traceback
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image
from urllib.parse import quote as urlquote
import requests
import time
from urllib.parse import urlparse


# load .env.local from project root (one level up)
project_root = Path(__file__).resolve().parents[1]
env_file = project_root / ".env.local"
if env_file.exists():
    load_dotenv(env_file)
    print("Loaded env from:", env_file, file=sys.stderr)
else:
    print("No .env.local found at:", env_file, file=sys.stderr)

# New: base to build reference asset URLs (set locally to http://localhost:3000)
REFERENCE_BASE = os.getenv("REFERENCE_BASE", "http://localhost:3000")

# require modern google-genai
try:
    from google import genai
except Exception:
    traceback.print_exc()
    raise SystemExit(
        "Install google-genai (pip install google-genai) and ensure it's in your venv."
    )

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise SystemExit("Set GEMINI_API_KEY in environment (.env.local)")

# instantiate client (new SDK)
try:
    client = genai.Client(api_key=API_KEY)
    print("Instantiated genai.Client(api_key=...)", file=sys.stderr)
except TypeError:
    # some versions require configure() then Client()
    genai.configure(api_key=API_KEY)
    client = genai.Client()
    print("Instantiated genai.Client() after configure()", file=sys.stderr)

MODEL_NAME = "gemini-2.5-flash-image-preview"

PROMPT_TEMPLATE = """
Generate a photorealistic studio image of a fashion model wearing the garment described below.

Model attributes:
- Gender: {gender}
- Age range: {age_range}
- Body type: {body_type}
- Skin tone: {skin_tone}
- Pose / action: {pose}
- Framing: {framing}

Design summary:
{design_summary}

Requirements:
- Preserve fabric texture, stitching, trims and colors exactly.
- Natural lighting, neutral studio background (white/gray) or transparent background if requested.
- No logos or text overlays.
- Output: high-resolution image (PNG) of the model wearing the garment.
"""


# new helper: download an HTTP(S) reference into out_dir, with retries
def download_reference_to_local(
    reference_url: str, out_dir: Path, max_retries: int = 3, timeout: int = 120
):
    """
    If reference_url is HTTP(S) this will attempt to download it into out_dir and return the local Path.
    Otherwise returns None.
    """
    if not reference_url:
        return None

    parsed = urlparse(reference_url)
    if parsed.scheme not in ("http", "https"):
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    local_name = Path(parsed.path).name
    # ensure extension present
    if not Path(local_name).suffix:
        local_name = local_name + ".png"
    local_path = out_dir / f"ref_{local_name}"

    attempt = 0
    while attempt < max_retries:
        try:
            # streaming get, respect server timeouts
            headers = {"User-Agent": "agent3-virtual-showcase/1.0"}
            r = requests.get(
                reference_url, headers=headers, stream=True, timeout=timeout
            )
            r.raise_for_status()
            with open(local_path, "wb") as fh:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        fh.write(chunk)
            # quick sanity check file size > 100 bytes
            if local_path.exists() and local_path.stat().st_size > 100:
                print(
                    f"[AUTO-REF] Downloaded reference to {local_path}", file=sys.stderr
                )
                return str(local_path)
            else:
                print(
                    f"[AUTO-REF] Downloaded file too small: {local_path}",
                    file=sys.stderr,
                )
        except Exception as ex:
            attempt += 1
            print(
                f"[AUTO-REF] download attempt {attempt} failed: {ex}", file=sys.stderr
            )
            time.sleep(1 + attempt * 1.5)
    print(
        f"[AUTO-REF] Failed to download reference after {max_retries} attempts: {reference_url}",
        file=sys.stderr,
    )
    return None


def design_to_summary(d: dict) -> str:
    parts = []
    title = d.get("title") or d.get("design_id") or "Untitled"
    parts.append(f"Title: {title}")
    palette = d.get("color_palette") or d.get("colors") or []
    if palette:
        parts.append("Colors: " + ", ".join(palette))
    fabrics = d.get("fabrics") or []
    if fabrics:
        parts.append("Fabrics: " + ", ".join(fabrics))
    garment = d.get("garment_type") or d.get("garment") or ""
    if garment:
        parts.append("Garment: " + garment)
    silhouette = d.get("silhouette") or d.get("style_fit") or ""
    if silhouette:
        parts.append(
            "Silhouette: "
            + (silhouette if isinstance(silhouette, str) else ", ".join(silhouette))
        )
    if d.get("sleeves"):
        parts.append("Sleeves: " + d.get("sleeves"))
    if d.get("neckline"):
        parts.append("Neckline: " + d.get("neckline"))
    if d.get("prints_patterns"):
        parts.append("Prints: " + ", ".join(d.get("prints_patterns")))
    tech = d.get("techpack") or d.get("image_prompt")
    if tech:
        parts.append("Notes: " + (str(tech)[:400]))
    return ". ".join(parts)


def build_prompt(summary: str, model_attrs: dict) -> str:
    framing = model_attrs.get("framing") or "full-body, studio frame, no close-ups"
    return PROMPT_TEMPLATE.format(
        gender=model_attrs.get("gender", "female"),
        age_range=model_attrs.get("age_range", "25-32"),
        body_type=model_attrs.get("body_type", "slim"),
        skin_tone=model_attrs.get("skin_tone", "medium"),
        pose=model_attrs.get("pose", "standing, natural fashion pose"),
        framing=framing,
        design_summary=summary,
    )


def parse_model_attrs(args):
    attrs = {}
    if args.model_attrs:
        try:
            p = Path(args.model_attrs)
            if p.exists():
                attrs = json.loads(p.read_text(encoding="utf-8"))
            else:
                attrs = json.loads(args.model_attrs)
        except Exception:
            print(
                "Warning: failed to parse --model-attrs as file or JSON, ignoring.",
                file=sys.stderr,
            )
            attrs = {}
    for k in ("gender", "age_range", "body_type", "skin_tone", "pose", "framing"):
        v = getattr(args, k, None)
        if v:
            attrs[k] = v
    defaults = {
        "gender": "female",
        "age_range": "25-32",
        "body_type": "slim",
        "skin_tone": "medium-dark",
        "pose": "standing, natural fashion pose",
        "framing": "full-body, studio frame, no close-ups",
    }
    for k, dv in defaults.items():
        attrs.setdefault(k, dv)
    return attrs


def find_design_files(path: Path):
    if path.is_file():
        return [path]
    files = sorted(
        [
            p
            for p in path.iterdir()
            if p.is_file() and p.suffix == ".json" and "design" in p.name.lower()
        ]
    )
    return files


def extract_image_bytes(resp):
    """
    Extract inline image bytes from modern google-genai response shape.
    Returns (bytes, mime) or (None, None)
    """
    try:
        # candidates -> content -> parts -> inline_data.data
        cands = getattr(resp, "candidates", None) or (
            resp.get("candidates") if isinstance(resp, dict) else []
        )
        if cands:
            cand = cands[0]
            content = getattr(cand, "content", None) or (
                cand.get("content") if isinstance(cand, dict) else None
            )
            if content:
                parts = getattr(content, "parts", None) or (
                    content.get("parts") if isinstance(content, dict) else []
                )
                for part in parts or []:
                    inline = getattr(part, "inline_data", None) or (
                        part.get("inline_data") if isinstance(part, dict) else None
                    )
                    if inline:
                        data = getattr(inline, "data", None) or inline.get("data")
                        mime = getattr(inline, "mime_type", None) or inline.get(
                            "mime_type", "image/png"
                        )
                        if data:
                            img_bytes = (
                                data
                                if isinstance(data, (bytes, bytearray))
                                else base64.b64decode(data)
                            )
                            return img_bytes, mime
    except Exception:
        pass

    # fallback: resp.output or resp.image
    try:
        if hasattr(resp, "output") and isinstance(resp.output, (bytes, bytearray)):
            return resp.output, "image/png"
    except Exception:
        pass

    if isinstance(resp, dict):
        if resp.get("image"):
            v = resp.get("image")
            try:
                if isinstance(v, (bytes, bytearray)):
                    return v, "image/png"
                if isinstance(v, str):
                    return base64.b64decode(v), "image/png"
            except Exception:
                pass

    return None, None


def showcase_from_design_file(
    design_file: Path, model_attrs: dict, out_dir: Path, reference_url: str = None
):
    d = json.loads(design_file.read_text(encoding="utf-8"))
    design_id = d.get("design_id") or design_file.stem
    summary = design_to_summary(d)
    prompt = build_prompt(summary, model_attrs)

    out_dir.mkdir(parents=True, exist_ok=True)
    storyboard = out_dir / f"{design_id}_storyboard.txt"
    storyboard.write_text(prompt, encoding="utf-8")

    print(
        f"-> Generating showcase for {design_id} with attributes {model_attrs} (reference={reference_url})",
        file=sys.stderr,
    )

    # Build prompt string; include reference URL in-line (simple, stable)
    if reference_url:
        # If reference_url looks like a local file path, include that explicitly AND the public URL comment.
        if Path(reference_url).exists():
            prompt_with_ref = f"Reference image file: {reference_url}\n\n{prompt}"
        else:
            prompt_with_ref = f"Reference image: {reference_url}\n\n{prompt}"
    else:
        prompt_with_ref = prompt

    # Use modern SDK shape: contents is a list (one string)
    try:
        resp = client.models.generate_content(
            model=MODEL_NAME,
            contents=[prompt_with_ref],
            config={"temperature": 0.0, "candidate_count": 1},
        )
        print(
            "Used client.models.generate_content(model=..., contents=[prompt])",
            file=sys.stderr,
        )
    except Exception as e:
        # bubble up a helpful message
        print("Generation call failed:", e, file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        raise

    img_bytes, mime = extract_image_bytes(resp)
    if not img_bytes:
        print(
            "[GENAI DEBUG] Could not extract image bytes; dumping repr (truncated):",
            file=sys.stderr,
        )
        try:
            print(repr(resp)[:2000], file=sys.stderr)
        except Exception:
            pass
        raise RuntimeError(
            "No image returned from Gemini for showcase. Inspect response object and SDK version."
        )

    out_file = out_dir / f"{design_id}_showcase.png"
    out_file.write_bytes(img_bytes)

    try:
        img = Image.open(out_file)
        img.save(out_file, format="PNG")
    except Exception as e:
        print("Pillow normalization skipped:", e, file=sys.stderr)

    print(f"Saved showcase image: {out_file} ({len(img_bytes)} bytes)", file=sys.stderr)
    return str(out_file)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--design", type=str, help="single design JSON file")
    parser.add_argument(
        "--input-dir",
        type=str,
        default="output/agent2_designs",
        help="directory of design JSONs",
    )
    parser.add_argument(
        "--limit", type=int, default=1, help="how many random showcases to generate"
    )
    parser.add_argument(
        "--seed", type=int, default=None, help="seed for reproducible randomness"
    )
    parser.add_argument(
        "--model-attrs",
        type=str,
        help="JSON string or path to JSON file with model attributes",
    )
    parser.add_argument(
        "--reference",
        type=str,
        help="HTTP URL to a reference image (flatlay) for conditioning",
    )
    parser.add_argument(
        "--description",
        type=str,
        help="textual description to reinforce garment details",
        default="",
    )
    parser.add_argument("--gender", type=str)
    parser.add_argument("--age_range", type=str)
    parser.add_argument("--body_type", type=str)
    parser.add_argument("--skin_tone", type=str)
    parser.add_argument("--pose", type=str)
    parser.add_argument("--framing", type=str)
    parser.add_argument("--out-dir", type=str, default="output")
    args = parser.parse_args()

    # Normalize reference URL if passed as relative path
    if args.reference and args.reference.startswith("/"):
        args.reference = f"http://localhost:3000{args.reference}"

        # --- AUTO-REF: if we have an HTTP reference or can find a local render, prefer to use a local file ---
    downloaded_local_ref = None
    if args.design and not args.reference:
        try:
            design_path = Path(args.design)
            if design_path.exists():
                try:
                    d = json.loads(design_path.read_text(encoding="utf-8"))
                    design_id = d.get("design_id") or design_path.stem
                except Exception:
                    design_id = design_path.stem
            else:
                design_id = design_path.stem
            expected_file = project_root / "renders" / f"{design_id}__flatlay.png"
            if expected_file.exists():
                # form the public URL if REFERENCE_BASE used by caller, but also keep a local fallback
                encoded = urlquote(f"renders/{expected_file.name}", safe="")
                public_url = f"{REFERENCE_BASE}/api/assets?path={encoded}"
                args.reference = public_url
                print(
                    f"[AUTO-REF] Using public reference URL {args.reference}",
                    file=sys.stderr,
                )
                # Also try to make a local copy for the agent to avoid remote GETs
                downloaded_local_ref = str(expected_file)
            else:
                print(
                    f"[AUTO-REF] No flatlay found at {expected_file}", file=sys.stderr
                )
        except Exception as e:
            print(f"[AUTO-REF] Failed auto-reference check: {e}", file=sys.stderr)

    # If caller passed an HTTP(S) reference, try to download it into out_dir for faster/safer access
    reference_local_path = None
    if args.reference and args.reference.startswith(("http://", "https://")):
        # try to download into out_dir (use temporary folder inside out_dir to persist)
        local_candidate = download_reference_to_local(
            args.reference, Path(args.out_dir) / "refs", max_retries=3, timeout=120
        )
        if local_candidate:
            reference_local_path = local_candidate
    # If we had an expected_file above, prefer that local file
    if downloaded_local_ref:
        reference_local_path = downloaded_local_ref

    # pass 'reference_local_path' into showcase_from_design_file via reference_url argument,
    # if present we will pass a file:// or absolute path to the worker
    if reference_local_path:
        # convert to absolute file path string so downstream can detect local file
        args.reference = str(Path(reference_local_path).resolve())
    print("Using reference (final):", args.reference, file=sys.stderr)

    if args.design:
        files = find_design_files(Path(args.design))
    else:
        files = find_design_files(Path(args.input_dir))
        if args.seed is not None:
            random.seed(args.seed)
        random.shuffle(files)
        files = files[: args.limit]

    model_attrs = parse_model_attrs(args)
    out_dir = Path(args.out_dir)
    print(
        f"Found {len(files)} designs to showcase. Using model_attrs={model_attrs}",
        file=sys.stderr,
    )

    for f in files:
        try:
            showcase_from_design_file(
                f, model_attrs, out_dir, reference_url=args.reference
            )
        except Exception as e:
            print(f"Failed for {f.name}: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)


if __name__ == "__main__":
    main()
