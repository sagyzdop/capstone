// Station UI server: Next.js on ONE explicit port, on both loopback addresses.
//
//   node server.mjs [--dev] [--port 8765] [--host 127.0.0.1 --host ::1]
//
// Why not `next dev` / `next start`:
// - `next dev` moves to the next port when the one asked for is busy, so the URL you
//   open and the URL the server is on drift apart. Here a busy port is a hard error.
// - Browsers try `localhost` as ::1 first. A server on 127.0.0.1 alone lets anything
//   holding ::1 or *:PORT answer instead (macOS AirPlay on 5000/7000 answers 403).
//   Listening on both loopbacks, and refusing ports someone already answers on,
//   makes http://localhost:PORT, http://127.0.0.1:PORT and http://[::1]:PORT the same server.
// - Node sets SO_REUSEADDR, which on macOS lets 127.0.0.1:PORT bind next to another
//   program's *:PORT, so the connect probe below is what catches that case.
import http from "node:http";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";
import next from "next";

const { values } = parseArgs({
  options: {
    dev: { type: "boolean", default: false },
    port: { type: "string" },
    host: { type: "string", multiple: true },
  },
});
const dev = values.dev;
const port = Number(values.port ?? process.env.PORT ?? 8765);
const hosts = values.host ?? ["127.0.0.1", "::1"];
const dir = path.dirname(fileURLToPath(import.meta.url));
// models/ and ../data/samples resolve from here, wherever the command was run from
process.chdir(dir);

function die(msg) {
  console.error(`\n  ✖ ${msg}\n`);
  process.exit(1);
}

if (!Number.isInteger(port) || port < 1 || port > 65535) die(`Bad port "${values.port ?? process.env.PORT}"`);

/** Does anything already accept connections on host:port? */
function answers(host, port) {
  return new Promise((resolve) => {
    const s = net.connect({ host, port });
    const done = (v) => {
      s.destroy();
      resolve(v);
    };
    s.setTimeout(500, () => done(false));
    s.once("connect", () => done(true));
    s.once("error", () => done(false));
  });
}

for (const host of hosts) {
  if (await answers(host, port)) {
    die(`Port ${port} is already in use on ${host} by another program. Pick a free one: npm run ${dev ? "dev" : "start"} -- --port ${port + 1}`);
  }
}

// one http.Server does the work; extra addresses hand their connections to it, so
// requests and dev-mode WebSocket upgrades all go through the same server
const server = http.createServer((req, res) => handle(req, res));
const app = next({ dev, dir, hostname: "localhost", port, httpServer: server });
const handle = app.getRequestHandler();
await app.prepare();

function listen(target, host) {
  return new Promise((resolve) => {
    target.once("error", (e) => {
      if (e.code === "EADDRINUSE") die(`Port ${port} on ${host} was taken while starting. Pick another: --port ${port + 1}`);
      // e.g. IPv6 switched off on this machine: serve the other address only
      if (e.code === "EADDRNOTAVAIL" || e.code === "EAFNOSUPPORT") {
        console.warn(`  ! ${host} is not available here (${e.code}), skipping it`);
        return resolve(false);
      }
      die(`Can't listen on ${host}:${port}: ${e.message}`);
    });
    target.listen({ host, port, ipv6Only: host.includes(":") }, () => resolve(true));
  });
}

const bound = [];
if (await listen(server, hosts[0])) bound.push(hosts[0]);
for (const host of hosts.slice(1)) {
  const relay = net.createServer((sock) => server.emit("connection", sock));
  if (await listen(relay, host)) bound.push(host);
}
if (!bound.length) die("Could not listen on any address");

const url = (h) => `http://${h.includes(":") ? `[${h}]` : h}:${port}`;
console.log(`\n  Station UI (${dev ? "dev" : "production"}) ready`);
console.log(`  → ${bound.includes("127.0.0.1") || bound.includes("::1") ? `http://localhost:${port}` : url(bound[0])}`);
console.log(`  → camera: http://localhost:${port}/#camera`);
console.log(`    listening on ${bound.map(url).join(", ")}\n`);
