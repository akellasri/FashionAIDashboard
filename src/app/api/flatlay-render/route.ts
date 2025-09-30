// src/app/api/flatlay-render/route.ts
import { NextRequest, NextResponse } from "next/server";
import { spawn } from "child_process";
import { writeFile, mkdir } from "fs/promises";
import { join } from "path";
import { existsSync } from "fs";

async function ensureTempDir() {
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
  return process.env.PYTHON_PATH || (process.platform === "win32" ? "py" : "python3");
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const design = body.design;
    if (!design) {
      return NextResponse.json({ success: false, error: "missing design" }, { status: 400 });
    }

    const tempDir = await ensureTempDir();
    const designPath = join(tempDir, `design_${Date.now()}.json`);
    await writeFile(designPath, JSON.stringify(design, null, 2));

    const pythonPath = getPythonExecutable();
    const script = join(process.cwd(), "scripts", "render_utils.py");
    const args = [script, "--input", designPath, "--variant", "flatlay"];

    const proc = spawn(pythonPath, args, { cwd: process.cwd(), env: { ...process.env } });

    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (d) => {
      stdout += d.toString();
      console.log("[PYOUT]", d.toString());
    });

    proc.stderr.on("data", (d) => {
      stderr += d.toString();
      console.error("[PYERR]", d.toString());
    });

    return await new Promise((resolve) => {
      proc.on("close", (code) => {
        const combined = stdout + "\n" + stderr;
        const match = combined.match(/Saved:? (.+\.(?:png|jpg|jpeg))/i);

        if (code === 0 && match && match[1]) {
          resolve(
            NextResponse.json({
              success: true,
              imageUrl: normalizeForBrowser(match[1].trim()),
              message: "Flatlay render generated successfully",
            })
          );
        } else if (code === 0) {
          resolve(
            NextResponse.json(
              { success: false, error: "Could not parse script output", raw_stdout: stdout, raw_stderr: stderr },
              { status: 500 }
            )
          );
        } else {
          resolve(
            NextResponse.json(
              { success: false, error: `Script failed (code ${code})`, raw_stdout: stdout, raw_stderr: stderr },
              { status: 500 }
            )
          );
        }
      });

      proc.on("error", (err) => {
        resolve(NextResponse.json({ success: false, error: `spawn error: ${err.message}` }, { status: 500 }));
      });
    });
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}
