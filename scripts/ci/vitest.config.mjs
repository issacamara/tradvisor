import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const frontendRoot = path.join(repositoryRoot, "frontend");
const frontendRequire = createRequire(path.join(frontendRoot, "package.json"));
const { defineConfig } = frontendRequire("vitest/config");

export default defineConfig({
  root: repositoryRoot,
  resolve: {
    alias: [
      { find: "@", replacement: path.join(frontendRoot, "src") },
      { find: "@testing-library/react", replacement: frontendRequire.resolve("@testing-library/react") },
      { find: /^react$/, replacement: frontendRequire.resolve("react") },
      { find: /^react\/(.*)/, replacement: `${frontendRoot}/node_modules/react/$1` },
    ],
  },
  test: {
    environment: "jsdom",
    setupFiles: [path.join(frontendRoot, "src/test/setup.ts"), path.join(path.dirname(fileURLToPath(import.meta.url)), "vitest.setup.ts")],
    include: ["frontend/src/**/*.test.{ts,tsx}", "tests/frontend/**/*.test.{ts,tsx}"],
  },
});
