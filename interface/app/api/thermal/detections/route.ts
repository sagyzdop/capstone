import { thermalError, thermalFrame, thermalModelError, thermalPort } from "@/lib/thermal";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Boxes for the latest MLX90640 frame, same shape as POST /api/detect plus the frame's temperatures. */
export function GET() {
  const f = thermalFrame();
  const headers = { "cache-control": "no-store" };
  if (!f) return Response.json({ detail: thermalError() ?? `waiting for MLX90640 frames on UDP ${thermalPort()}` }, { status: 503, headers });
  if (!f.det) return Response.json({ detail: thermalModelError() ?? "no thermal model" }, { status: 503, headers });
  return Response.json({ frame: f.frameId, age_ms: Date.now() - f.at, min: f.min, max: f.max, ta: f.ta, ...f.det }, { headers });
}
