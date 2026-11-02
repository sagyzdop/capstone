import { DEFAULT_MODEL, decode, detect, listModels } from "@/lib/detector";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const int = (v: FormDataEntryValue | null, dflt: number) => (v == null || v === "" ? dflt : Number.parseInt(String(v), 10));

export async function POST(req: Request) {
  let form: FormData;
  try {
    form = await req.formData();
  } catch {
    return Response.json({ detail: "expected multipart/form-data" }, { status: 400 });
  }
  const file = form.get("file");
  if (!(file instanceof Blob)) return Response.json({ detail: "missing file" }, { status: 400 });
  const imgsz = int(form.get("imgsz"), 640), tile = int(form.get("tile"), 0);
  if (!(imgsz >= 160 && imgsz <= 1920 && imgsz % 32 === 0)) return Response.json({ detail: "imgsz must be a multiple of 32 in 160..1920" }, { status: 400 });
  if (!(tile === 0 || (tile >= 160 && tile <= 1920 && tile % 32 === 0))) return Response.json({ detail: "tile must be 0 or a multiple of 32 in 160..1920" }, { status: 400 });
  // comma-separated model names, e.g. "visdrone,pose"
  const models = [...new Set(String(form.get("models") ?? DEFAULT_MODEL).split(",").map((s) => s.trim()).filter(Boolean))];
  const known = new Set(listModels().map((m) => m.name));
  const unknown = models.filter((m) => !known.has(m));
  if (!models.length || unknown.length) return Response.json({ detail: `unknown model ${unknown.join(", ") || "(none)"}; have ${[...known].join(", ")}` }, { status: 400 });

  let img;
  try {
    img = await decode(Buffer.from(await file.arrayBuffer()));
  } catch {
    return Response.json({ detail: "not an image" }, { status: 400 });
  }
  try {
    return Response.json(await detect(img, imgsz, tile, models));
  } catch (e) {
    return Response.json({ detail: (e as Error).message }, { status: 500 });
  }
}
