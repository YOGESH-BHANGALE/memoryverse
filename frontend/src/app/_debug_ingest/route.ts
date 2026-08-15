import { appendFile, mkdir } from "fs/promises";
import { dirname } from "path";
import { NextRequest, NextResponse } from "next/server";

const LOG_PATHS = [
  "e:\\MEMORYVERSE HAKATHPN\\debug-2cda69.log",
  "e:\\MEMORYVERSE HAKATHPN\\.cursor\\debug-2cda69.log",
];

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const line = JSON.stringify({ ...body, timestamp: body.timestamp || Date.now() }) + "\n";
    for (const logPath of LOG_PATHS) {
      await mkdir(dirname(logPath), { recursive: true });
      await appendFile(logPath, line);
    }
    return NextResponse.json({ ok: true });
  } catch (err) {
    return NextResponse.json({ ok: false, error: String(err) }, { status: 500 });
  }
}
