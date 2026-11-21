import { piFrame } from "@/lib/picam";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Newest JPEG from the Pi webcam. ?src=<host[:port] or URL> picks the Pi, default PICAM_URL. 503 until frames arrive. */
export function GET(req: Request) {
  let st;
  try {
    st = piFrame(new URL(req.url).searchParams.get("src"));
  } catch (e) {
    return Response.json({ detail: (e as Error).message }, { status: 400 });
  }
  const headers = { "cache-control": "no-store", "x-picam-url": st.url, "x-picam-fps": st.fps.toFixed(1) };
  if (!st.frame) return Response.json({ detail: st.error }, { status: 503, headers });
  return new Response(new Uint8Array(st.frame.jpeg), {
    headers: { ...headers, "content-type": "image/jpeg", "x-picam-frame": String(st.frame.n), "x-picam-age-ms": String(Date.now() - st.frame.at) },
  });
}
