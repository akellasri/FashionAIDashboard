#!/usr/bin/env python3
"""
agent3_runway_demo.py (modern google-genai)

Read design JSON(s) and generate runway video(s) via Gemini Veo using the modern `google-genai`
SDK. Accepts --model-attrs as JSON string or path to JSON file. Supports optional --reference
HTTP URL to condition the video on a flatlay/reference image.
"""
import os
import sys
import time
import json
import argparse
import random
import traceback
from pathlib import Path
from dotenv import load_dotenv
import requests
import time
from urllib.parse import urlparse, quote as urlquote

# load .env.local from project root
project_root = Path(__file__).resolve().parents[1]
env_file = project_root / ".env.local"
if env_file.exists():
    load_dotenv(env_file)
    print("Loaded env from:", env_file, file=sys.stderr)
else:
    print("No .env.local found at:", env_file, file=sys.stderr)

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

# instantiate client
try:
    client = genai.Client(api_key=API_KEY)
    print("Instantiated genai.Client(api_key=...)", file=sys.stderr)
except TypeError:
    genai.configure(api_key=API_KEY)
    client = genai.Client()
    print("Instantiated genai.Client() after configure()", file=sys.stderr)

# Model
VEO_MODEL = "veo-3.0-generate-001"

PROMPT_TEMPLATE = """
You are a fashion video director. Use the design summary below to:
1) produce a short 6-second storyboard describing camera framing, timing and moves (3-5 bullets).
2) then render a photorealistic 6-second runway video showing an Indian model wearing the design.

Model attributes:
- Gender: {gender}
- Age range: {age_range}
- Body type: {body_type}
- Skin tone: {skin_tone}
- Pose / action: {pose}

Design summary:
{design_summary}

Requirements for the video:
- Shots: Full-length runway shots only (no close-ups). 3–4 distinct moves (walk, turn, pose).
- Lighting: soft studio key + subtle rim, neutral background, no logos or text.
- Output: photorealistic MP4, duration ~6s.
"""


def download_reference_to_local(
    reference_url: str, out_dir: Path, max_retries: int = 3, timeout: int = 120
):
    """
    If reference_url is HTTP(S) this will attempt to download it into out_dir and return the local Path string.
    Otherwise returns None.
    """
    if not reference_url:
        return None

    parsed = urlparse(reference_url)
    if parsed.scheme not in ("http", "https"):
        return None

    out_dir.mkdir(parents=True, exist_ok=True)
    local_name = Path(parsed.path).name or f"ref_{int(time.time())}.png"
    if not Path(local_name).suffix:
        local_name = local_name + ".png"
    local_path = out_dir / f"ref_{local_name}"

    attempt = 0
    while attempt < max_retries:
        try:
            headers = {"User-Agent": "agent3-runway/1.0"}
            r = requests.get(
                reference_url, headers=headers, stream=True, timeout=timeout
            )
            r.raise_for_status()
            with open(local_path, "wb") as fh:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        fh.write(chunk)
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
    parts.append(f"Title: {title}.")
    palette = d.get("color_palette") or d.get("colors") or []
    if palette:
        parts.append("Colors: " + ", ".join(palette) + ".")
    fabrics = d.get("fabrics") or []
    if fabrics:
        parts.append("Fabrics: " + ", ".join(fabrics) + ".")
    garment = d.get("garment_type") or d.get("garment") or ""
    if garment:
        parts.append("Garment: " + garment + ".")
    silhouette = d.get("silhouette") or d.get("style_fit") or ""
    if silhouette:
        if isinstance(silhouette, list):
            parts.append("Silhouette: " + ", ".join(silhouette) + ".")
        else:
            parts.append("Silhouette: " + silhouette + ".")
    if d.get("sleeves"):
        parts.append("Sleeves: " + d.get("sleeves") + ".")
    if d.get("neckline"):
        parts.append("Neckline: " + d.get("neckline") + ".")
    if d.get("prints_patterns"):
        parts.append("Prints: " + ", ".join(d.get("prints_patterns")) + ".")
    tech = d.get("techpack") or d.get("image_prompt")
    if tech:
        parts.append("Notes: " + (str(tech)[:400]))
    return " ".join(parts)


def build_prompt(summary: str, attrs: dict) -> str:
    return PROMPT_TEMPLATE.format(
        gender=attrs.get("gender", "female"),
        age_range=attrs.get("age_range", "25-32"),
        body_type=attrs.get("body_type", "slim"),
        skin_tone=attrs.get("skin_tone", "medium-dark"),
        pose=attrs.get("pose", "runway walk, natural turn"),
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
    for k in ("gender", "age_range", "body_type", "skin_tone", "pose"):
        v = getattr(args, k, None)
        if v:
            attrs[k] = v
    defaults = {
        "gender": "female",
        "age_range": "25-32",
        "body_type": "slim",
        "skin_tone": "medium-dark",
        "pose": "runway walk, natural turn",
    }
    for k, v in defaults.items():
        attrs.setdefault(k, v)
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


def robust_submit_veo(prompt: str, reference_url: str = None):
    """
    Submit runway video request to Veo.
    If reference_url is a local file path, include the file path text in the prompt.
    If an HTTP URL is given, include the URL.
    """
    if reference_url:
        try:
            if Path(reference_url).exists():
                # Local file case
                prompt = f"Reference image file: {reference_url}\n\n{prompt}"
            else:
                # URL case
                prompt = f"Reference image: {reference_url}\n\n{prompt}"
        except Exception:
            # fallback: treat as URL if Path fails
            prompt = f"Reference image: {reference_url}\n\n{prompt}"

    try:
        op = client.models.generate_videos(
            model=VEO_MODEL,
            prompt=prompt,
        )
        print(
            "Used client.models.generate_videos(model=..., prompt=...)",
            file=sys.stderr,
        )
        return op
    except Exception as e:
        print("client.models.generate_videos failed:", e, file=sys.stderr)
        traceback.print_exc(file=sys.stderr)

    # fallback: older style SDK
    if hasattr(client, "generate_videos"):
        return client.generate_videos(model=VEO_MODEL, prompt=prompt)

    raise RuntimeError(
        "All methods to submit Veo generation failed; see stderr for details."
    )


def poll_and_download(operation, out_path: Path, timeout=600):
    """
    Poll a Veo operation until done and save the resulting video file.

    Robust handling for multiple SDK return shapes:
      - vid_field.save(path)
      - client.files.download(file=vid_field) -> file_obj with .save / .content / .bytes / .read
      - generated_video.video may be an object containing a URL field -> requests.get(...)
      - lots of debug output written to stderr to help inspect SDK shapes
    """
    start = time.time()
    # wait for completion
    while not getattr(operation, "done", False):
        time.sleep(5)
        try:
            if hasattr(client, "operations") and hasattr(client.operations, "get"):
                operation = client.operations.get(operation)
        except Exception as e:
            print("Warning: poll refresh failed:", e, file=sys.stderr)
        if time.time() - start > timeout:
            raise TimeoutError("Timed out waiting for Veo operation")

    # Try to extract generated_videos (defensive)
    try:
        generated_video = operation.response.generated_videos[0]
    except Exception as e:
        # dump operation repr for debugging
        try:
            print("DEBUG operation repr:", repr(operation)[:4000], file=sys.stderr)
        except Exception:
            pass
        raise RuntimeError("No generated_videos found on operation.response") from e

    # log a small repr to help debugging
    try:
        print(
            "DEBUG generated_video repr:", repr(generated_video)[:2000], file=sys.stderr
        )
    except Exception:
        pass

    vid_field = getattr(generated_video, "video", None)
    if vid_field is None:
        # maybe there's a different field name: try common alternatives
        possible = []
        for k in ("video", "file", "video_file", "download", "video_url", "url"):
            v = (
                getattr(generated_video, k, None)
                if hasattr(generated_video, k)
                else (
                    generated_video.get(k)
                    if isinstance(generated_video, dict)
                    else None
                )
            )
            if v:
                possible.append((k, v))
        if possible:
            print(
                "DEBUG found alternative generated_video fields:",
                [(k, type(v)) for k, v in possible],
                file=sys.stderr,
            )
        raise RuntimeError("No 'video' field in generated_videos (inspect operation)")

    # 1) Official: if the object supports .save(path), try that first
    try:
        if hasattr(vid_field, "save"):
            try:
                vid_field.save(str(out_path))
                return str(out_path)
            except Exception as e:
                print("Warning: vid_field.save() failed:", e, file=sys.stderr)
    except Exception as e:
        print("Warning checking vid_field.save():", e, file=sys.stderr)

    # 2) Try client.files.download(file=vid_field) if available
    try:
        if hasattr(client, "files") and hasattr(client.files, "download"):
            try:
                file_obj = client.files.download(file=vid_field)
                print(
                    "DEBUG client.files.download returned:",
                    type(file_obj),
                    file=sys.stderr,
                )
            except Exception as e:
                print("Warning: client.files.download(...) raised:", e, file=sys.stderr)
                file_obj = None

            if file_obj is not None:
                # If file_obj has .save(), use it
                if hasattr(file_obj, "save"):
                    try:
                        file_obj.save(str(out_path))
                        return str(out_path)
                    except Exception as e:
                        print("Warning: file_obj.save() failed:", e, file=sys.stderr)

                # Try common attributes: content, bytes
                data = (
                    getattr(file_obj, "content", None)
                    or getattr(file_obj, "bytes", None)
                    or None
                )
                if data:
                    if isinstance(data, (bytes, bytearray)):
                        out_path.write_bytes(data)
                        return str(out_path)
                    if hasattr(data, "read"):
                        with open(out_path, "wb") as fh:
                            fh.write(data.read())
                        return str(out_path)

                # If file_obj itself is bytes-like
                if isinstance(file_obj, (bytes, bytearray)):
                    out_path.write_bytes(file_obj)
                    return str(out_path)

                # some SDKs return a wrapper with 'url' or 'download_url' or 'media_url'
                for url_attr in ("url", "download_url", "media_url", "file_url"):
                    u = (
                        getattr(file_obj, url_attr, None)
                        if hasattr(file_obj, url_attr)
                        else (
                            file_obj.get(url_attr)
                            if isinstance(file_obj, dict)
                            else None
                        )
                    )
                    if u and isinstance(u, str):
                        print(
                            "DEBUG found download URL on file_obj:",
                            url_attr,
                            u,
                            file=sys.stderr,
                        )
                        r = requests.get(u, timeout=60)
                        r.raise_for_status()
                        out_path.write_bytes(r.content)
                        return str(out_path)
    except Exception as e:
        print("Warning during client.files.download handling:", e, file=sys.stderr)

    # 3) Try common shapes on vid_field itself: maybe it's a dict with url
    try:
        if isinstance(vid_field, dict):
            for url_attr in ("url", "download_url", "media_url", "file_url"):
                u = vid_field.get(url_attr)
                if u and isinstance(u, str):
                    print(
                        "DEBUG found download URL on vid_field dict:",
                        url_attr,
                        u,
                        file=sys.stderr,
                    )
                    r = requests.get(u, timeout=60)
                    r.raise_for_status()
                    out_path.write_bytes(r.content)
                    return str(out_path)
        # maybe vid_field has attributes with URLs
        for url_attr in ("url", "download_url", "media_url", "file_url"):
            u = getattr(vid_field, url_attr, None)
            if u and isinstance(u, str):
                print(
                    "DEBUG found download URL on vid_field object:",
                    url_attr,
                    u,
                    file=sys.stderr,
                )
                r = requests.get(u, timeout=60)
                r.raise_for_status()
                out_path.write_bytes(r.content)
                return str(out_path)
    except Exception as e:
        print("Warning: URL-download fallback failed:", e, file=sys.stderr)

    # 4) Try to detect an ID string and call client.files.download(file=id) again
    try:
        if isinstance(vid_field, str):
            print(
                "DEBUG vid_field appears to be an ID string, trying client.files.download(file=vid_field)",
                file=sys.stderr,
            )
            try:
                file_obj = client.files.download(file=vid_field)
                print(
                    "DEBUG client.files.download returned for id-string:",
                    type(file_obj),
                    file=sys.stderr,
                )
            except Exception as e:
                print(
                    "Warning: client.files.download for id-string failed:",
                    e,
                    file=sys.stderr,
                )
                file_obj = None

            if file_obj:
                if hasattr(file_obj, "save"):
                    try:
                        file_obj.save(str(out_path))
                        return str(out_path)
                    except Exception as e:
                        print("Warning: file_obj.save() failed:", e, file=sys.stderr)
                data = (
                    getattr(file_obj, "content", None)
                    or getattr(file_obj, "bytes", None)
                    or None
                )
                if isinstance(data, (bytes, bytearray)):
                    out_path.write_bytes(data)
                    return str(out_path)
                if hasattr(data, "read"):
                    with open(out_path, "wb") as fh:
                        fh.write(data.read())
                    return str(out_path)
    except Exception as e:
        print("Warning: id-string download fallback failed:", e, file=sys.stderr)

    # Last resort: dump debug info and raise
    try:
        print(
            "FINAL DEBUG: operation repr (truncated):",
            repr(operation)[:4000],
            file=sys.stderr,
        )
        print(
            "FINAL DEBUG: generated_video repr (truncated):",
            repr(generated_video)[:2000],
            file=sys.stderr,
        )
    except Exception:
        pass

    raise RuntimeError(
        "Could not save Veo video; unexpected SDK return object. Inspect operation and client.files responses."
    )


REFERENCE_BASE = os.getenv("REFERENCE_BASE", "http://localhost:3000")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--design", type=str, help="single design JSON file")
    parser.add_argument("--input-dir", type=str, default="output/agent2_designs")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--model-attrs", type=str)
    parser.add_argument("--reference", type=str, help="HTTP URL to reference image")
    parser.add_argument("--gender", type=str)
    parser.add_argument("--age_range", type=str)
    parser.add_argument("--body_type", type=str)
    parser.add_argument("--skin_tone", type=str)
    parser.add_argument("--pose", type=str)
    parser.add_argument("--out-dir", type=str, default="output")
    args = parser.parse_args()

    # --- AUTO-REFERENCE LOGIC (NEW) ---
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

            expected = project_root / "renders" / f"{design_id}__flatlay.png"
            if expected.exists():
                # prefer local file
                args.reference = str(expected.resolve())
                print(
                    f"[AUTO-REF] Found local flatlay at {args.reference}",
                    file=sys.stderr,
                )
            else:
                print(f"[AUTO-REF] No flatlay found at {expected}", file=sys.stderr)
        except Exception as e:
            print(f"[AUTO-REF] Failed auto-reference check: {e}", file=sys.stderr)

    # If caller passed a remote HTTP reference, try to download into out_dir/refs
    if args.reference and args.reference.startswith(("http://", "https://")):
        local_candidate = download_reference_to_local(
            args.reference, Path(args.out_dir) / "refs", max_retries=3, timeout=120
        )
        if local_candidate:
            args.reference = str(Path(local_candidate).resolve())
            print(
                f"[AUTO-REF] Using downloaded local reference {args.reference}",
                file=sys.stderr,
            )

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
        f"Found {len(files)} design files. model_attrs={model_attrs}", file=sys.stderr
    )

    for f in files:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Skipping {f.name}: read error {e}", file=sys.stderr)
            continue

        design_id = d.get("design_id") or f.stem
        summary = design_to_summary(d)
        prompt = build_prompt(summary, model_attrs)

        sb_file = out_dir / f"{design_id}_storyboard.txt"
        sb_file.write_text(prompt, encoding="utf-8")

        print(f"-> [{design_id}] Submitting Veo request...", file=sys.stderr)
        try:
            op = robust_submit_veo(prompt, reference_url=args.reference)
        except Exception as e:
            print(f"  Submit failed: {e}. Saved storyboard.", file=sys.stderr)
            continue

        print("  Polling for completion...", file=sys.stderr)
        try:
            out_path = out_dir / f"{design_id}_runway.mp4"
            saved = poll_and_download(op, out_path)
            print(f"  Saved video: {saved}", file=sys.stderr)
        except Exception as e:
            print(f"  Failed to get video: {e}. Storyboard saved.", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)


if __name__ == "__main__":
    main()
