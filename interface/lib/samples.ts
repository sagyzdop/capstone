// One-click example frames: images in SAMPLES_DIR (default ../data/samples), if it exists.
import fs from "node:fs";
import path from "node:path";

const IMAGE_EXT = new Set([".jpg", ".jpeg", ".png", ".bmp", ".webp"]);
// runtime path, not a build input: keep the bundler from tracing it
export const SAMPLES_DIR = path.resolve(/* turbopackIgnore: true */ process.env.SAMPLES_DIR ?? path.join(process.cwd(), "..", "data", "samples"));

export function listSamples(): string[] {
  if (!fs.existsSync(SAMPLES_DIR)) return [];
  return fs
    .readdirSync(SAMPLES_DIR)
    .filter((f) => IMAGE_EXT.has(path.extname(f).toLowerCase()))
    .sort()
    .slice(0, 24);
}
