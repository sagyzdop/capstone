import { DEFAULT_MODEL, getModel, listModels } from "@/lib/detector";
import { listSamples } from "@/lib/samples";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const models = listModels();
    if (!models.length) throw new Error("no models in models/: run `npm run export-model -- --all`");
    // warm the default one up; the others load on first use
    await getModel(models.some((m) => m.name === DEFAULT_MODEL) ? DEFAULT_MODEL : models[0].name);
    return Response.json({
      models: models.map((m) => ({ ...m, classes: m.person.map((c) => m.names[c] ?? String(c)) })),
      device: "cpu",
      runtime: "ONNX Runtime",
      samples: listSamples(),
    });
  } catch (e) {
    return Response.json({ detail: (e as Error).message }, { status: 503 });
  }
}
