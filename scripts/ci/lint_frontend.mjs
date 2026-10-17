import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";
const frontendRequire = createRequire(path.resolve("../frontend/package.json"));
const ts = frontendRequire("typescript");

const root = path.resolve("src");
const failures = [];

async function visit(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const file = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      await visit(file);
    } else if (/\.(tsx?|jsx?)$/.test(entry.name) && !entry.name.endsWith(".d.ts")) {
      const sourceText = await readFile(file, "utf8");
      const source = ts.createSourceFile(file, sourceText, ts.ScriptTarget.Latest, true);
      const comments = sourceText.match(/\/\/[^\n]*|\/\*[\s\S]*?\*\//g) ?? [];
      for (const comment of comments) {
        if (/@ts-(?:ignore|nocheck|expect-error)/.test(comment)) failures.push(`${file}: suppression comment is not allowed`);
      }
      const inspect = (node) => {
        if (ts.isDebuggerStatement(node)) failures.push(`${file}: debugger statement is not allowed`);
        if (ts.isCallExpression(node) && ts.isPropertyAccessExpression(node.expression)
          && node.expression.expression.getText(source) === "console" && node.expression.name.text === "log") {
          failures.push(`${file}: console.log is not allowed`);
        }
        ts.forEachChild(node, inspect);
      };
      inspect(source);
      for (const diagnostic of source.parseDiagnostics) {
        const { line, character } = source.getLineAndCharacterOfPosition(diagnostic.start ?? 0);
        failures.push(`${file}:${line + 1}:${character + 1}: ${ts.flattenDiagnosticMessageText(diagnostic.messageText, " ")}`);
      }
    }
  }
}

await visit(root);
if (failures.length) {
  process.stderr.write(`${failures.join("\n")}\n`);
  process.exitCode = 1;
} else {
  process.stdout.write("Frontend lint checks passed.\n");
}
