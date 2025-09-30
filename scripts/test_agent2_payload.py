#!/usr/bin/env python3
"""
test_agent2_payload.py (cleaned)

- Sends chat request to Azure GPT (gpt-5-chat) with flatlay constraints.
- Saves raw response to output/agent2_designs/<payload_id>.response.json
- Saves each variant to output/agent2_designs/<design_id>.design.json
- Writes ONLY the parsed design JSON (object or array) to STDOUT.
- All debug/log printing goes to STDERR.
"""

import os
import sys
import json
import time
import uuid
import re
import requests
from pathlib import Path
from dotenv import load_dotenv

# project root and env
project_root = Path(__file__).resolve().parents[1]
env_file = project_root / ".env.local"
if env_file.exists():
    load_dotenv(env_file)
    print(f"Loaded env from: {env_file}", file=sys.stderr)
else:
    print(f"No .env.local found at: {env_file}", file=sys.stderr)

AZ_ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT")
AZ_KEY = os.environ.get("AZURE_OPENAI_KEY")
AZ_DEPLOY = os.environ.get("AZURE_OPENAI_DEPLOYMENT")  # e.g. "gpt-5-chat"
API_VERSION = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

if not (AZ_ENDPOINT and AZ_KEY and AZ_DEPLOY):
    print(
        "Missing one of AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY, AZURE_OPENAI_DEPLOYMENT in env.",
        file=sys.stderr,
    )
    sys.exit(1)

# CLI args
if len(sys.argv) < 2:
    print("Usage: python test_agent2_payload.py path/to/payload.json", file=sys.stderr)
    sys.exit(1)

payload_path = Path(sys.argv[1])
if not payload_path.exists():
    print(f"Payload file not found: {payload_path}", file=sys.stderr)
    sys.exit(1)

# read payload
try:
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
except Exception as e:
    print(f"Failed to read payload: {e}", file=sys.stderr)
    sys.exit(1)

# output dir
out_dir = Path("output/agent2_designs")
out_dir.mkdir(parents=True, exist_ok=True)

# build Azure request
url = f"{AZ_ENDPOINT.rstrip('/')}/openai/deployments/{AZ_DEPLOY}/chat/completions?api-version={API_VERSION}"
headers = {"Content-Type": "application/json", "api-key": AZ_KEY}

user_content = payload.get("user_content", {}) or {}
variants_count = int(user_content.get("variants", 1) or 1)
user_override_prompt = (
    user_content.get("user_override_prompt")
    or user_content.get("image_prompt_override")
    or ""
)

system_prompt = payload.get(
    "system_prompt",
    "You are a fashion product design assistant. Respond ONLY with valid JSON (no extra explanation).",
)

# Strong flatlay constraint and preservation instruction
flatlay_constraint = (
    "IMPORTANT: The generated image prompts and any render instructions MUST produce an "
    "apparel-only flat-lay / product render. No model, no mannequin, no human, no body parts, "
    "no model poses, and no lifestyle scene. Output should be suitable for product pages: "
    "isolated garment on a plain white or transparent background, high-detail fabric texture, "
    "visible stitching and trims. Respond ONLY with JSON (or JSON array) and nothing else."
)

# Force the model to preserve user-specified fields
preserve_instruction = (
    "\n\nRULE: If the user provides a value for any field in the 'User content' JSON (e.g. "
    "neckline, sleeves, garment_type, color palette etc.), DO NOT change or overwrite those values. "
    "Only fill missing fields. Return EXACTLY one JSON object (or an array of objects if requesting multiple variants). "
    "Do not output any explanatory text."
)

# Compose user block
variant_instruction = (
    f"Please output exactly {variants_count} distinct design variant(s) as a JSON array. "
    "Each variant must be a JSON object with keys: design_id, title, image_prompt, color_palette, "
    "fabrics, prints_patterns, garment_type, silhouette, sleeves, neckline, length, style_fit, "
    "trims_and_details, techpack, provenance."
)
merged_user_text = flatlay_constraint + preserve_instruction + "\n\n"
if user_override_prompt:
    merged_user_text += (
        "User-specified prompt (merge into design but preserve the above constraints):\n"
        + user_override_prompt.strip()
        + "\n\n"
    )

merged_user_text += (
    variant_instruction
    + "\n\nUser content (context JSON):\n"
    + json.dumps(user_content, ensure_ascii=False, indent=2)
)

user_blocks = [{"type": "text", "text": merged_user_text}]

# attach example images if present (keeps existing behavior)
examples = user_content.get("examples") or []
for ex in examples:
    img = ex.get("image_url") or ex.get("image")
    if img:
        user_blocks.append({"type": "image_url", "image_url": {"url": img}})

messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": user_blocks},
]

body = {
    "messages": messages,
    "max_tokens": 1600,
    "temperature": 0.0,
    "top_p": 0.95,
    "n": 1,
}

print("Sending request to Azure GPT-5-chat...", file=sys.stderr)
try:
    resp = requests.post(url, headers=headers, json=body, timeout=180)
except Exception as e:
    print(f"Azure request failed: {e}", file=sys.stderr)
    sys.exit(1)

payload_id = payload.get("id") or payload_path.stem or str(uuid.uuid4())
raw_resp_file = out_dir / f"{payload_id}.response.json"

if resp.status_code != 200:
    print("Error:", resp.status_code, resp.text[:1000], file=sys.stderr)
    raw_resp_file.write_text(
        json.dumps(
            {"status": resp.status_code, "text": resp.text},
            ensure_ascii=False,
            indent=2,
        )
    )
    sys.exit(1)

data = resp.json()
raw_resp_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))
print(f"Saved raw response to: {raw_resp_file}", file=sys.stderr)


# ---------- helper to build human summary ----------
def design_to_text(d):
    lines = []
    lines.append(f"{d.get('title','Untitled')} ({d.get('design_id')})")
    cp = ", ".join(d.get("color_palette", []) or d.get("colors", [])) or "unknown"
    fabrics = ", ".join(d.get("fabrics", [])) or "unknown"
    prints = ", ".join(d.get("prints_patterns", [])) or "none"
    lines.append(f"Colors: {cp}")
    lines.append(f"Fabrics: {fabrics}")
    lines.append(f"Prints/Patterns: {prints}")
    lines.append(f"Garment Type: {d.get('garment_type','unknown')}")
    lines.append(f"Silhouette: {d.get('silhouette','unknown')}")
    lines.append(f"Sleeves: {d.get('sleeves','unknown')}")
    lines.append(f"Neckline: {d.get('neckline','unknown')}")
    lines.append(f"Length: {d.get('length','unknown')}")
    sf = ", ".join(d.get("style_fit", [])) or ""
    if sf:
        lines.append(f"Style / Fit: {sf}")
    trims = ", ".join(d.get("trims_and_details", [])) or ""
    if trims:
        lines.append(f"Trims & details: {trims}")
    if d.get("techpack"):
        lines.append("Techpack: available")
    return "\n".join(lines)


# ---------- extract text from varying Azure response shapes ----------
def extract_text_from_choice(choice):
    msg = choice.get("message") or choice.get("delta") or {}
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        tb = [
            b.get("text")
            for b in content
            if isinstance(b, dict) and b.get("type") == "text" and b.get("text")
        ]
        if tb:
            return "\n\n".join(tb)
        return json.dumps(content, ensure_ascii=False)
    return json.dumps(msg, ensure_ascii=False)


# ---------- parse model output ----------
try:
    choice = data.get("choices", [])[0]
    resp_text = extract_text_from_choice(choice)
    # Print preview to stderr for debugging only
    print("\n----- MODEL OUTPUT (preview) -----\n", file=sys.stderr)
    print(resp_text[:1200], file=sys.stderr)

    # find first JSON block (object or array) - robust approach
    m = re.search(r"(\[?\s*\{[\s\S]*\}\s*\]?)", resp_text)
    parsed = None
    if m:
        text_json = m.group(1)
        try:
            parsed = json.loads(text_json)
        except Exception:
            # try to tidy trailing commas and reparse
            cleaned = re.sub(r",\s*}", "}", text_json)
            cleaned = re.sub(r",\s*]", "]", cleaned)
            try:
                parsed = json.loads(cleaned)
            except Exception:
                parsed = None

    # final attempt: raw parse
    if parsed is None:
        try:
            parsed = json.loads(resp_text.strip())
        except Exception:
            parsed = None

    if parsed is None:
        print(
            "Could not parse JSON automatically. Inspect the raw response file:",
            raw_resp_file,
            file=sys.stderr,
        )
        # Exit non-zero so caller knows it failed to produce JSON
        sys.exit(1)
    else:
        # ensure list
        if isinstance(parsed, dict):
            parsed_list = [parsed]
        else:
            parsed_list = parsed

        saved_files = []
        for idx, variant in enumerate(parsed_list, start=1):
            vid = variant.get("design_id") or f"{payload_id}__v{idx:02d}"

            # Defensive defaults for list fields
            for k in [
                "color_palette",
                "fabrics",
                "prints_patterns",
                "style_fit",
                "trims_and_details",
            ]:
                if k not in variant or variant.get(k) is None:
                    variant[k] = []

            # If user provided fields in payload.user_content, enforce/preserve them:
            # (overwrite only when user provided non-empty values)
            uc = user_content or {}
            # map some common keys
            mapping = {
                "colors": "color_palette",
                "fabrics": "fabrics",
                "prints": "prints_patterns",
                "garment_type": "garment_type",
                "silhouette": "silhouette",
                "sleeves": "sleeves",
                "neckline": "neckline",
                "trims_and_details": "trims_and_details",
            }
            for u_key, v_key in mapping.items():
                u_val = uc.get(u_key)
                if u_val:
                    # If user provided list or string, set into variant accordingly
                    if isinstance(u_val, list):
                        variant[v_key] = u_val
                    else:
                        # user may provide a single string for e.g. neckline
                        if v_key in [
                            "color_palette",
                            "fabrics",
                            "prints_patterns",
                            "style_fit",
                            "trims_and_details",
                        ]:
                            # convert single string to single-element list
                            variant[v_key] = (
                                [u_val]
                                if not isinstance(variant[v_key], list)
                                else variant[v_key]
                            )
                        else:
                            variant[v_key] = u_val

            # create design_text summary
            try:
                summary = design_to_text(variant)
            except Exception:
                summary = variant.get("title", vid)
            variant["design_text"] = summary

            outfile = out_dir / f"{vid}.design.json"
            outfile.write_text(
                json.dumps(variant, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            saved_files.append(str(outfile))

        # Write saved-files log to stderr
        print("Saved design JSON files:", saved_files, file=sys.stderr)

        # IMPORTANT: output the actual parsed JSON to STDOUT (object or array)
        # If only one variant, print single object; if multiple, print array.
        if len(parsed_list) == 1:
            # single object
            sys.stdout.write(json.dumps(parsed_list[0], ensure_ascii=False))
        else:
            sys.stdout.write(json.dumps(parsed_list, ensure_ascii=False))

        # successful exit
        sys.exit(0)

except Exception as e:
    print("Failed to parse or extract model content:", e, file=sys.stderr)
    print("Inspect raw response at:", raw_resp_file, file=sys.stderr)
    sys.exit(1)
