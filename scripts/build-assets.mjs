import { cp, mkdir, rm } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const destination = resolve(root, "static", "vendor");

await rm(resolve(destination, "tabler"), { recursive: true, force: true });
await mkdir(resolve(destination, "tabler"), { recursive: true });
await rm(resolve(destination, "htmx"), { recursive: true, force: true });
await mkdir(resolve(destination, "htmx"), { recursive: true });
await rm(resolve(destination, "xterm"), { recursive: true, force: true });
await mkdir(resolve(destination, "xterm"), { recursive: true });
await rm(resolve(destination, "novnc"), { recursive: true, force: true });
await mkdir(resolve(destination, "novnc"), { recursive: true });
await rm(resolve(destination, "cytoscape"), { recursive: true, force: true });
await mkdir(resolve(destination, "cytoscape"), { recursive: true });

const assets = [
  ["node_modules/@tabler/core/dist/css/tabler.min.css", "tabler/tabler.min.css"],
  ["node_modules/@tabler/core/dist/js/tabler.min.js", "tabler/tabler.min.js"],
  ["node_modules/htmx.org/dist/htmx.min.js", "htmx/htmx.min.js"],
  ["node_modules/@xterm/xterm/css/xterm.css", "xterm/xterm.css"],
  ["node_modules/@xterm/xterm/lib/xterm.js", "xterm/xterm.js"],
  ["node_modules/@xterm/addon-fit/lib/addon-fit.js", "xterm/addon-fit.js"],
  ["node_modules/@novnc/novnc/core", "novnc/core"],
  ["node_modules/@novnc/novnc/vendor", "novnc/vendor"],
  ["node_modules/cytoscape/dist/cytoscape.min.js", "cytoscape/cytoscape.min.js"]
];

for (const [source, target] of assets) {
  await cp(resolve(root, source), resolve(destination, target), { recursive: true });
}

const iconNames = [
  "home",
  "server",
  "device-desktop",
  "photo",
  "database",
  "network",
  "list-check",
  "shield-check",
  "settings"
];
await mkdir(resolve(destination, "tabler", "icons"), { recursive: true });
for (const name of iconNames) {
  await cp(
    resolve(root, "node_modules", "@tabler", "icons", "icons", "outline", `${name}.svg`),
    resolve(destination, "tabler", "icons", `${name}.svg`)
  );
}
