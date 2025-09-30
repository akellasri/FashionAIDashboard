#!/usr/bin/env python3
# render_utils.py (fixed + robust)
import os
import json
import base64
import sys
import random
from pathlib import Path
from PIL import Image
from dotenv import load_dotenv

# prefer new SDK import
try:
    from google import genai
except Exception as e:
    print("ERROR: google-genai not available:", e, file=sys.stderr)
    raise SystemExit("Install google-genai in your venv (pip install google-genai)")

# Load .env.local
project_root = Path(__file__).resolve().parents[1]
env_file = project_root / ".env.local"
if env_file.exists():
    load_dotenv(env_file)
    print("Loaded env from:", env_file, file=sys.stderr)
else:
    print("No .env.local found at:", env_file, file=sys.stderr)

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    raise SystemExit("GEMINI_API_KEY not set in .env.local")

# Initialize client (robust pattern)
client = None
try:
    client = genai.Client(api_key=API_KEY)
    print("Instantiated genai.Client(api_key=...)", file=sys.stderr)
except Exception:
    try:
        genai.configure(api_key=API_KEY)
        client = genai.Client()
        print("Instantiated genai.Client() after configure()", file=sys.stderr)
    except Exception:
        client = genai
        print("Falling back to genai module as client", file=sys.stderr)

MODEL_NAME = "gemini-2.5-flash-image-preview"


def _call_generate_content(prompt):
    """
    Try multiple call shapes for generate_content to be compatible with differing SDK versions.
    Returns the raw response object.
    """
    # Try modern pattern: client.models.generate_content(model=..., contents=[...], config=...)
    try:
        if hasattr(client, "models") and hasattr(client.models, "generate_content"):
            return client.models.generate_content(
                model=MODEL_NAME,
                contents=[{"type": "text", "text": prompt}],
                config={"temperature": 0.0, "candidate_count": 1},
            )
    except Exception as e:
        print("client.models.generate_content(...) failed:", e, file=sys.stderr)

    # Older pattern: client.models.generate_content with contents as string
    try:
        if hasattr(client, "models") and hasattr(client.models, "generate_content"):
            return client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config={"temperature": 0.0, "candidate_count": 1},
            )
    except Exception as e:
        print(
            "client.models.generate_content(contents=prompt) failed:",
            e,
            file=sys.stderr,
        )

    # Fallback: client.generate_content(prompt)
    try:
        if hasattr(client, "generate_content"):
            return client.generate_content(prompt)
    except Exception as e:
        print("client.generate_content(prompt) failed:", e, file=sys.stderr)

    # Last fallback: genai.generate_content(prompt)
    try:
        if hasattr(genai, "generate_content"):
            return genai.generate_content(prompt)
    except Exception as e:
        print("genai.generate_content(prompt) failed:", e, file=sys.stderr)

    raise RuntimeError("No compatible generate_content method succeeded on SDK client")


def render_design_via_gemini(design_json, variant="flatlay", out_dir="renders"):
    """
    design_json: dict (expects image_prompt key else will build one)
    variant: "flatlay" or other
    returns path to saved file
    """
    # Use design_text if present (most descriptive and consistent)
    prompt = (
        design_json.get("design_text")
        or design_json.get("image_prompt")
        or design_json.get("title")
        or "photorealistic flat-lay product image"
    )

    # Append attributes in a stable, mapped way
    attr_map = {
        "color_palette": "Colors",
        "fabrics": "Fabrics",
        "garment_type": "Garment type",
        "silhouette": "Silhouette",
        "sleeves": "Sleeves",
        "prints_patterns": "Prints/Patterns",
    }
    for key, label in attr_map.items():
        val = design_json.get(key)
        if val:
            if isinstance(val, list):
                val = ", ".join(val)
            prompt += f". {label}: {val}"

    # Add flatlay prefix once (outside the loop)
    if variant == "flatlay":
        prompt = (
            "Flat-lay apparel-only: isolated garment, NO MODEL, NO MANNEQUIN, NO HUMAN. "
            + prompt
            + ". Photorealistic product-only PNG, high-detail fabric texture. White background."
        )

    # Call Gemini (robust wrapper)
    resp = _call_generate_content(prompt)

    # Defensive extraction of image bytes
    img_bytes = None
    mime = "image/png"

    # candidates -> content -> parts -> inline_data / image / data / b64
    candidates = getattr(resp, "candidates", None) or (
        resp.get("candidates") if isinstance(resp, dict) else []
    )
    for cand in candidates:
        content = None
        if hasattr(cand, "content"):
            content = getattr(cand, "content")
        elif isinstance(cand, dict):
            content = cand.get("content")
        else:
            try:
                content = cand.__dict__.get("content")
            except Exception:
                content = None
        if not content:
            continue

        parts = None
        if hasattr(content, "parts"):
            parts = getattr(content, "parts") or []
        elif isinstance(content, dict):
            parts = content.get("parts") or []
        else:
            try:
                parts = content.__dict__.get("parts") or []
            except Exception:
                parts = []

        for part in parts:
            inline = (
                getattr(part, "inline_data", None)
                if hasattr(part, "inline_data")
                else (part.get("inline_data") if isinstance(part, dict) else None)
            )
            if inline:
                data_attr = (
                    getattr(inline, "data", None)
                    if hasattr(inline, "data")
                    else (inline.get("data") if isinstance(inline, dict) else None)
                )
                mime_attr = (
                    getattr(inline, "mime_type", None)
                    if hasattr(inline, "mime_type")
                    else (inline.get("mime_type") if isinstance(inline, dict) else None)
                )
                if data_attr:
                    mime = mime_attr or mime
                    img_bytes = (
                        data_attr
                        if isinstance(data_attr, (bytes, bytearray))
                        else base64.b64decode(data_attr)
                    )
                    break

            if getattr(part, "image", None):
                img_field = getattr(part, "image")
                if isinstance(img_field, (bytes, bytearray)):
                    img_bytes = img_field
                    break
                if hasattr(img_field, "content"):
                    img_bytes = getattr(img_field, "content")
                    break
                if isinstance(img_field, dict) and img_field.get("data"):
                    img_bytes = base64.b64decode(img_field.get("data"))
                    break

            if isinstance(part, dict):
                for k in ("b64", "data", "image", "inline_data", "content"):
                    val = part.get(k)
                    if not val:
                        continue
                    if isinstance(val, dict) and val.get("data"):
                        img_bytes = base64.b64decode(val.get("data"))
                        mime = val.get("mime_type") or mime
                        break
                    if isinstance(val, (bytes, bytearray)):
                        img_bytes = val
                        break
                    if isinstance(val, str):
                        try:
                            img_bytes = base64.b64decode(val)
                            break
                        except Exception:
                            continue
                if img_bytes:
                    break
        if img_bytes:
            break

    # Fallback: some SDKs use resp.output or resp.image
    if not img_bytes:
        try:
            if hasattr(resp, "output") and isinstance(resp.output, (bytes, bytearray)):
                img_bytes = resp.output
        except Exception:
            pass

    if not img_bytes:
        print(
            "[DEBUG] Could not locate image bytes in response. Response repr (truncated):",
            file=sys.stderr,
        )
        try:
            print(repr(resp)[:2000], file=sys.stderr)
        except Exception:
            pass
        raise RuntimeError("No image returned from Gemini for prompt.")

    ext = ".png"
    if "jpeg" in mime or "jpg" in mime:
        ext = ".jpg"

    save_dir = Path(out_dir)
    save_dir.mkdir(parents=True, exist_ok=True)
    design_id = design_json.get("design_id", "design")
    out_file = save_dir / f"{design_id}__{variant}{ext}"

    with open(out_file, "wb") as f:
        f.write(img_bytes)

    # normalize with Pillow to ensure PNG
    try:
        img = Image.open(out_file)
        fixed_file = save_dir / f"{design_id}__{variant}.png"
        img.save(fixed_file, format="PNG")
        out_file = fixed_file
    except Exception as e:
        print(f"⚠️ Warning: could not re-save with Pillow: {e}", file=sys.stderr)

    return str(out_file)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--input", help="Path to design.json (optional)")
    parser.add_argument("--variant", default="flatlay")
    args = parser.parse_args()

    if args.input:
        d = json.load(open(args.input, encoding="utf-8"))
    else:
        design_dir = Path("output/agent2_designs")
        candidates = list(design_dir.glob("*.design.json"))
        if not candidates:
            raise SystemExit("No design JSONs found in output/agent2_designs/")
        d = json.load(open(random.choice(candidates), encoding="utf-8"))

    out = render_design_via_gemini(d, args.variant)
    print("Saved:", out)
