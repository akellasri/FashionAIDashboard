// src/app/api/virtual-showcase/route.ts
import { NextRequest, NextResponse } from "next/server";
import { spawn } from "child_process";
import { writeFile, mkdir } from "fs/promises";
import { join } from "path";
import { existsSync } from "fs";
import fs from "fs";

async function ensureTempDir(): Promise<string> {
  const tmp = join(process.cwd(), "temp");
  if (!existsSync(tmp)) {
    await mkdir(tmp, { recursive: true });
  }
  return tmp;
}

function normalizeForBrowser(p: string) {
  let s = p.replace(/\\/g, "/").replace(/^[A-Za-z]:/, "");
  s = s.replace(/^\/+/, "");
  return `/api/assets?path=${encodeURIComponent(s)}`;
}

function getPythonExecutable(): string {
  const winVenv = join(process.cwd(), "scripts", "venv", "Scripts", "python.exe");
  const posixVenv = join(process.cwd(), "scripts", "venv", "bin", "python");
  if (existsSync(winVenv)) return winVenv;
  if (existsSync(posixVenv)) return posixVenv;
  // Respect env override if set
  if (process.env.PYTHON_PATH) return process.env.PYTHON_PATH;
  return process.platform === "win32" ? "py" : "python3";
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { design, modelConfig, reference } = body ?? {};

    if (!design || !design.design_id) {
      return NextResponse.json({ success: false, error: "missing design or design.design_id" }, { status: 400 });
    }

    await ensureTempDir();
    const designPath = join(process.cwd(), "temp", `${design.design_id}.design.json`);
    await writeFile(designPath, JSON.stringify(design, null, 2), "utf-8");

    // Build absolute reference URL when provided (supports relative reference like /api/assets?...).
    let referenceUrl: string | undefined;
    if (reference) {
      // If reference already looks absolute, keep it. Otherwise build from host/proto.
      try {
        const r = new URL(reference);
        referenceUrl = r.toString();
      } catch {
        // Not absolute — build from request headers
        const proto =
          request.headers.get("x-forwarded-proto") ||
          request.headers.get("x-forwarded-protocol") ||
          (request.headers.get("referer") ? new URL(request.headers.get("referer") as string).protocol.replace(/:$/, "") : "http");
        const host = request.headers.get("host") || "localhost:3000";
        // ensure reference begins with slash
        const refPath = reference.startsWith("/") ? reference : `/${reference}`;
        referenceUrl = `${proto}://${host}${refPath}`;
      }
    }

    // Python executable selection
    const python = getPythonExecutable();

    // Build args: pass design path, model-attrs once, optional reference
    const args: string[] = [
      join("scripts", "agent3_virtual_showcase_demo.py"),
      "--design",
      designPath,
      "--out-dir",
      "output",
    ];

    if (modelConfig && Object.keys(modelConfig).length > 0) {
      args.push("--model-attrs", JSON.stringify(modelConfig));
    }

    if (referenceUrl) {
      args.push("--reference", referenceUrl);
    }

    const proc = spawn(python, args, { cwd: process.cwd(), env: { ...process.env } });

    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (d) => {
      const s = d.toString();
      stdout += s;
      console.log("[PYOUT]", s);
    });
    proc.stderr.on("data", (d) => {
      const s = d.toString();
      stderr += s;
      console.error("[PYERR]", s);
    });

    return await new Promise<NextResponse>((resolve) => {
      proc.on("close", (code) => {
        const combined = stdout + "\n" + stderr;
        if (code === 0) {
          // try common patterns: "Saved showcase image: ..." or "Saved: output/xxx.png"
          const m = combined.match(/Saved(?: showcase image)?:\s*([^\s'"]+\.(?:png|jpe?g))/i)
            || combined.match(/Saved:\s*(renders\/[^\s'"]+\.(?:png|jpe?g))/i)
            || combined.match(/Saved:\s*(output\/[^\s'"]+\.(?:png|jpe?g))/i);

          if (m && m[1]) {
            const savedPath = m[1].trim();
            return resolve(NextResponse.json({ success: true, imageUrl: normalizeForBrowser(savedPath), message: "Virtual showcase generated successfully" }));
          }

          // fallback: output/<design>_showcase.png
          const fallback = join("output", `${design.design_id}_showcase.png`);
          if (existsSync(join(process.cwd(), fallback))) {
            return resolve(NextResponse.json({ success: true, imageUrl: normalizeForBrowser(fallback), message: "Virtual showcase generated (fallback)" }));
          }

          // If no file found, still return success + raw logs for debugging
          return resolve(NextResponse.json({ success: true, message: "Virtual showcase script finished but no image parsed", raw_stdout: stdout, raw_stderr: stderr }));
        }

        // script failed
        return resolve(NextResponse.json({ success: false, error: `Script failed (code ${code})`, raw_stdout: stdout, raw_stderr: stderr }, { status: 500 }));
      });

      proc.on("error", (err) => {
        resolve(NextResponse.json({ success: false, error: `spawn error: ${err.message}` }, { status: 500 }));
      });
    });
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err?.message ?? String(err) }, { status: 500 });
  }
}
