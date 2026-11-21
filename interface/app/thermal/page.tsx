"use client";

import { useEffect, useRef, useState } from "react";
import type { ThermalDetections } from "@/lib/thermal";

const EMPTY = { frame: "—", min: "—", max: "—", ta: "—", age: "—", error: "" };

export default function Thermal() {
  const [src, setSrc] = useState("");
  const [st, setSt] = useState(EMPTY);
  const [det, setDet] = useState<ThermalDetections | null>(null);
  const urlRef = useRef("");

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      try {
        const r = await fetch("/api/thermal/frame", { cache: "no-store" });
        if (r.ok) {
          const url = URL.createObjectURL(await r.blob());
          const old = urlRef.current;
          urlRef.current = url;
          setSrc(url);
          if (old) URL.revokeObjectURL(old);
          setSt({
            frame: r.headers.get("x-thermal-frame") ?? "—",
            min: r.headers.get("x-thermal-min") ?? "—",
            max: r.headers.get("x-thermal-max") ?? "—",
            ta: r.headers.get("x-thermal-ta") ?? "—",
            age: r.headers.get("x-thermal-age-ms") ?? "—",
            error: "",
          });
          setDet(JSON.parse(r.headers.get("x-thermal-detections") ?? "null"));
        } else {
          const j = await r.json().catch(() => ({}));
          setSt((s) => ({ ...s, error: j.detail ?? `HTTP ${r.status}` }));
        }
      } catch (e) {
        setSt((s) => ({ ...s, error: (e as Error).message }));
      }
      if (alive) timer = setTimeout(tick, 250);
    };
    void tick();
    return () => {
      alive = false;
      clearTimeout(timer);
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    };
  }, []);

  const cell = { background: "#0f141b", border: "1px solid #2a3441", borderRadius: 8, padding: "8px 12px" };
  return (
    <main style={{ minHeight: "100vh", background: "#080b10", color: "#e6edf3", font: "14px ui-sans-serif, system-ui, sans-serif", padding: 24, boxSizing: "border-box" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 16 }}>
        <h1 style={{ fontSize: 18, margin: 0 }}>MLX90640 · live thermal</h1>
        <a href="/" style={{ color: "#58a6ff", textDecoration: "none", fontSize: 13 }}>← Station</a>
      </div>
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "flex-start" }}>
        <div style={{ flex: "1 1 640px", maxWidth: 800, background: "#0f141b", border: "1px solid #2a3441", borderRadius: 10, overflow: "hidden" }}>
          {src ? (
            <div style={{ position: "relative" }}>
              <img src={src} alt="live thermal" style={{ display: "block", width: "100%" }} />
              {det?.detections.map((d, i) => {
                const [x1, y1, x2, y2] = d.bbox_xyxy;
                const pct = (v: number, of: number) => `${(v / of) * 100}%`;
                return (
                  <div key={i} style={{ position: "absolute", left: pct(x1, det.width), top: pct(y1, det.height), width: pct(x2 - x1, det.width), height: pct(y2 - y1, det.height), border: "2px solid #3fb950", boxSizing: "border-box" }}>
                    <span style={{ position: "absolute", top: -20, left: -2, background: "#3fb950", color: "#000", fontSize: 12, fontWeight: 600, padding: "1px 5px", whiteSpace: "nowrap" }}>
                      {d.name} {Math.round(d.conf * 100)}%
                    </span>
                  </div>
                );
              })}
            </div>
          ) : (
            <div style={{ aspectRatio: "4/3", display: "grid", placeItems: "center", color: "#8b949e" }}>
              {st.error || "waiting for UDP frames on port 5005…"}
            </div>
          )}
        </div>
        <div style={{ display: "grid", gap: 8, minWidth: 190 }}>
          {([["frame", st.frame], ["min", `${st.min} °C`], ["max", `${st.max} °C`], ["sensor", `${st.ta} °C`], ["age", `${st.age} ms`], ["persons", det ? String(det.detections.length) : "no model"], ["model", det ? `${det.ms} ms` : "—"]] as const).map(([k, v]) => (
            <div key={k} style={cell}><span style={{ color: "#8b949e" }}>{k} </span><b>{v}</b></div>
          ))}
        </div>
      </div>
    </main>
  );
}
