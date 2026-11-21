import { piSubscribe, piUrl, type PiFrame } from "@/lib/picam";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const BOUNDARY = "picamframe";

/** The Pi's MJPEG feed re-served from this origin, for an <img> on the stage. Slow readers get frames dropped, not queued. */
export function GET(req: Request) {
  const src = new URL(req.url).searchParams.get("src");
  try {
    piUrl(src);
  } catch (e) {
    return Response.json({ detail: (e as Error).message }, { status: 400 });
  }
  let stop = () => {};
  const body = new ReadableStream<Uint8Array>(
    {
      start(ctrl) {
        const unsub = piSubscribe(src, (f: PiFrame) => {
          if ((ctrl.desiredSize ?? 0) <= 0) return;
          const head = Buffer.from(`--${BOUNDARY}\r\nContent-Type: image/jpeg\r\nContent-Length: ${f.jpeg.length}\r\n\r\n`);
          try {
            ctrl.enqueue(new Uint8Array(Buffer.concat([head, f.jpeg, Buffer.from("\r\n")])));
          } catch {
            stop();
          }
        });
        stop = () => {
          unsub();
          try {
            ctrl.close();
          } catch {}
        };
        req.signal.addEventListener("abort", () => stop());
      },
      cancel() {
        stop();
      },
    },
    { highWaterMark: 2 },
  );
  return new Response(body, {
    headers: { "content-type": `multipart/x-mixed-replace; boundary=${BOUNDARY}`, "cache-control": "no-store" },
  });
}
