import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

// Inline the two build assets so WebView can load HTML without an HTTP server.
const inlineUi = {
  name: "moru-inline-ui",
  enforce: "post" as const,
  generateBundle: (_options: unknown, bundle: Record<string, any>) => {
    const html = bundle["index.html"];
    if (!html) throw new Error("Missing UI entry");
    let source = String(html.source);
    for (const [name, asset] of Object.entries(bundle)) {
      if (name === "index.html") continue;
      if (asset.type === "chunk") {
        source = source.replace(
          /<script\b[^>]*\bsrc="[^"]+"[^>]*><\/script>/,
          () =>
            `<script type="module">${asset.code.replace(/<\/script/gi, "<\\/script")}</script>`,
        );
      } else if (name.endsWith(".css")) {
        source = source.replace(
          /<link\b[^>]*\brel="stylesheet"[^>]*>/,
          () => `<style>${asset.source}</style>`,
        );
      } else {
        throw new Error(`Unexpected external UI asset: ${name}`);
      }
      delete bundle[name];
    }
    html.source = source;
  },
};

export default defineConfig({
  server: { fs: { allow: [fileURLToPath(new URL("..", import.meta.url))] } },
  plugins: [react(), inlineUi],
  base: "./",
  build: {
    outDir: "../src/moru/web",
    emptyOutDir: true,
    cssCodeSplit: false,
    modulePreload: false,
    rollupOptions: { output: { inlineDynamicImports: true } },
  },
  test: { environment: "jsdom", setupFiles: "./src/test-setup.ts" },
});
