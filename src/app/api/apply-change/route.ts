// src/app/api/apply-change/route.ts
import { NextRequest, NextResponse } from "next/server";
import { spawn } from "child_process";
import { writeFile, mkdir } from "fs/promises";
import { join } from "path";
import path from "path";
import { existsSync, readFileSync } from "fs";

/** Prefer venv python if present (Windows) */
function getPythonExecutable(): string {
  const winVenv = join(process.cwd(), "scripts", "venv", "Scripts", "python.exe");
  const posixVenv = join(process.cwd(), "scripts", "venv", "bin", "python");
  if (existsSync(winVenv)) return winVenv;
  if (existsSync(posixVenv)) return posixVenv;
  return process.platform === "win32" ? "py" : "python3";
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { design, textChange } = body;

    if (!design || !textChange) {
      return NextResponse.json({ success: false, error: "Missing design or textChange" }, { status: 400 });
    }

    const tempDir = join(process.cwd(), "temp");
    await mkdir(tempDir, { recursive: true });

    const designPath = join(tempDir, `design_${Date.now()}.json`);
    const changePath = join(tempDir, `change_${Date.now()}.txt`);

    await writeFile(designPath, JSON.stringify(design, null, 2), "utf8");
    await writeFile(changePath, String(textChange), "utf8");

    const pythonCmd = getPythonExecutable();
    const scriptPath = join(process.cwd(), "scripts", "apply_text_change.py");

    return new Promise((resolvePromise) => {
      const pythonProcess = spawn(
        pythonCmd,
        [scriptPath, designPath, changePath],
        { stdio: ["ignore", "pipe", "pipe"], env: { ...process.env }, shell: false }
      );

      let stdout = "";
      let stderr = "";

      pythonProcess.stdout.on("data", (d) => {
        const s = d.toString();
        stdout += s;
        console.log("[PYOUT]", s.trim());
      });
      pythonProcess.stderr.on("data", (d) => {
        const s = d.toString();
        stderr += s;
        console.error("[PYERR]", s.trim());
      });

      pythonProcess.on("close", (code) => {
        if (code !== 0) {
          return resolvePromise(NextResponse.json({
            success: false,
            error: `Python script exited with code ${code}`,
            raw_stdout: stdout.slice(0, 2000),
            raw_stderr: stderr.slice(0, 8000)
          }, { status: 500 }));
        }

        const wroteMatch = stdout.match(/Wrote:\s*(.+)/);
        if (wroteMatch && wroteMatch[1]) {
          let modifiedPath = wroteMatch[1].trim().replace(/^["']|["']$/g, "");

          // build candidate paths; use join/path.resolve to avoid TS typing issues
          const candidatePaths: string[] = [];
          if (path.isAbsolute(modifiedPath)) candidatePaths.push(modifiedPath);
          candidatePaths.push(path.join(process.cwd(), modifiedPath));
          candidatePaths.push(path.join(process.cwd(), "scripts", modifiedPath));
          candidatePaths.push(path.join(process.cwd(), "temp", modifiedPath));
          candidatePaths.push(path.join(process.cwd(), "output", modifiedPath));
          candidatePaths.push(path.join(process.cwd(), modifiedPath.replace(/\\/g, "/")));

          let finalPath: string | null = null;
          for (const p of candidatePaths) {
            if (existsSync(p)) {
              finalPath = p;
              break;
            }
          }

          if (!finalPath) {
            return resolvePromise(NextResponse.json({
              success: false,
              error: "Python reported Wrote: path but file not found",
              reportedPath: modifiedPath,
              tried: candidatePaths.slice(0, 10),
              raw_stdout: stdout.slice(0, 2000),
              raw_stderr: stderr.slice(0, 8000)
            }, { status: 500 }));
          }

          try {
            const fileContents = readFileSync(finalPath, "utf8");
            const updatedDesign = JSON.parse(fileContents);
            return resolvePromise(NextResponse.json({ success: true, design: updatedDesign, message: "Design updated successfully" }));
          } catch (err: any) {
            return resolvePromise(NextResponse.json({
              success: false,
              error: "Failed to read/parse updated design file",
              details: String(err),
              finalPath,
              raw_stdout: stdout.slice(0, 2000),
              raw_stderr: stderr.slice(0, 8000)
            }, { status: 500 }));
          }
        }

        // Fallback: maybe Python printed JSON to stdout
        try {
          const parsed = JSON.parse(stdout.trim());
          return resolvePromise(NextResponse.json({ success: true, design: parsed, message: "Design updated from stdout" }));
        } catch (e) {
          return resolvePromise(NextResponse.json({
            success: false,
            error: "Could not find written file path and stdout was not parseable JSON",
            raw_stdout: stdout.slice(0, 2000),
            raw_stderr: stderr.slice(0, 8000)
          }, { status: 500 }));
        }
      });

      pythonProcess.on("error", (err) => {
        resolvePromise(NextResponse.json({ success: false, error: `Failed to spawn python: ${err.message}` }, { status: 500 }));
      });
    });

  } catch (err: any) {
    console.error("apply-change route error:", err);
    return NextResponse.json({ success: false, error: String(err) }, { status: 500 });
  }
}
