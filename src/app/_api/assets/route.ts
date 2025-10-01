// src/app/api/asset/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { join, normalize, resolve, sep } from 'path'
import { existsSync, readFileSync } from 'fs'
import mime from 'mime'

// Allow only these folders (relative to project root)
const ALLOWED_DIRS = new Set(['renders', 'output', 'public'])

export async function GET(req: NextRequest) {
    try {
        const url = new URL(req.url)
        const rawPath = url.searchParams.get('path')
        if (!rawPath) {
            return NextResponse.json({ success: false, error: 'Missing path param' }, { status: 400 })
        }

        // Normalize slashes to forward slash and remove any leading slash
        let requested = rawPath.replace(/\\/g, '/').replace(/^\/+/, '')

        // Prevent traversal: if it contains ".." it's rejected
        if (requested.includes('..')) {
            return NextResponse.json({ success: false, error: 'Invalid path' }, { status: 400 })
        }

        // Determine which allowed folder the path starts with
        const firstSegment = requested.split('/')[0]
        if (!ALLOWED_DIRS.has(firstSegment)) {
            return NextResponse.json({ success: false, error: 'Folder not allowed' }, { status: 403 })
        }

        // Build absolute path from project root (process.cwd())
        const abs = resolve(join(process.cwd(), requested))

        // Extra safety: ensure resolved path is inside project root
        const projectRoot = resolve(process.cwd())
        if (!abs.startsWith(projectRoot + sep) && abs !== projectRoot) {
            return NextResponse.json({ success: false, error: 'Invalid resolved path' }, { status: 400 })
        }

        if (!existsSync(abs)) {
            return NextResponse.json({ success: false, error: 'File not found', path: requested }, { status: 404 })
        }

        const data = readFileSync(abs)
        const contentType = mime.getType(abs) || 'application/octet-stream'

        return new NextResponse(data, {
            status: 200,
            headers: {
                'Content-Type': contentType,
                'Cache-Control': 'no-cache'
            }
        })
    } catch (err: any) {
        return NextResponse.json({ success: false, error: String(err?.message ?? err) }, { status: 500 })
    }
}
