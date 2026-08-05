import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  base: "/static/app/",
  build: {
    outDir: "../static/app",
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: "src/main.tsx",
      output: {
        manualChunks(id) {
          if (id.includes("node_modules/cytoscape")) {
            return "cytoscape-vendor";
          }
          if (id.includes("node_modules/@novnc")) {
            return "novnc-vendor";
          }
          if (id.includes("node_modules/@xterm")) {
            return "xterm-vendor";
          }
          if (id.includes("node_modules/react") || id.includes("node_modules/scheduler")) {
            return "react-vendor";
          }
          if (
            id.includes("node_modules/antd") ||
            id.includes("node_modules/@ant-design") ||
            id.includes("node_modules/@rc-component") ||
            id.includes("node_modules/rc-")
          ) {
            return "antd-vendor";
          }
          return undefined;
        },
      },
    },
  },
});
