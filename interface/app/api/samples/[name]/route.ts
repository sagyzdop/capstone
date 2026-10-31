import fs from "node:fs/promises";
import path from "node:path";
import { listSamples, SAMPLES_DIR } from "@/lib/samples";

export const runtime = "nodejs";

const TYPES: Record<string, string> = { ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".bmp": "image/bmp", ".webp": "image/webp" };

export async function GET(_req: Request, { params }: { params: Promise<{ name: string }> }) {
  const { name } = await params;
  // only names from the listing, so no path can escape SAMPLES_DIR
  if (!listSamples().includes(name)) return new Response("not found", { status: 404 });
  const body = await fs.readFile(path.join(SAMPLES_DIR, name));
  return new Response(body, { headers: { "content-type": TYPES[path.extname(name).toLowerCase()] ?? "application/octet-stream" } });
}
