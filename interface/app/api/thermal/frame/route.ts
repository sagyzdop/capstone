import { thermalError, thermalFrame, thermalPort } from "@/lib/thermal";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export function GET() {
  const f = thermalFrame();
  if (!f) {
    return Response.json(
      { detail: thermalError() ?? `waiting for MLX90640 frames on UDP ${thermalPort()}` },
      { status: 503, headers: { "cache-control": "no-store" } },
    );
  }
  return new Response(new Uint8Array(f.jpeg), {
    headers: {
      "content-type": "image/jpeg",
      "cache-control": "no-store",
      "x-thermal-frame": String(f.frameId),
      "x-thermal-min": f.min.toFixed(2),
      "x-thermal-max": f.max.toFixed(2),
      "x-thermal-ta": f.ta.toFixed(2),
      "x-thermal-age-ms": String(Date.now() - f.at),
      // boxes for this exact frame, in JPEG pixels; "null" when models/thermal.onnx is missing
      "x-thermal-detections": JSON.stringify(f.det),
    },
  });
}
