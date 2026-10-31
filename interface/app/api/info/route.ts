import { getModel } from "@/lib/detector";
import { listSamples } from "@/lib/samples";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const { meta } = await getModel();
    return Response.json({
      ...meta,
      classes: Object.values(meta.names),
      device: "cpu",
      runtime: "ONNX Runtime",
      samples: listSamples(),
    });
  } catch (e) {
    return Response.json({ detail: (e as Error).message }, { status: 503 });
  }
}
