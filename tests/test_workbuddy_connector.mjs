import assert from "node:assert/strict";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";


const base = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const child = spawn("node", [path.join(base, "workbuddy_connector", "server.mjs")], {
  cwd: path.join(base, "workbuddy_connector"),
  env: { ...process.env, RADAR_DATA_FILE: path.join(base, "static", "workbuddy", "latest.json") },
  stdio: ["pipe", "pipe", "inherit"],
});

const messages = [
  { jsonrpc: "2.0", id: 1, method: "initialize", params: { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "test", version: "1" } } },
  { jsonrpc: "2.0", id: 2, method: "tools/list", params: {} },
  { jsonrpc: "2.0", id: 3, method: "tools/call", params: { name: "get_daily_brief", arguments: { limit: 1 } } },
];

for (const message of messages) child.stdin.write(`${JSON.stringify(message)}\n`);
child.stdin.end();

let output = "";
for await (const chunk of child.stdout) output += chunk;
const exitCode = await new Promise((resolve) => child.on("close", resolve));
assert.equal(exitCode, 0);

const responses = output.trim().split("\n").map((line) => JSON.parse(line));
assert.equal(responses[0].result.serverInfo.name, "a-share-preopen-radar");
assert.deepEqual(responses[1].result.tools.map((tool) => tool.name), ["get_daily_brief", "analyze_watchlist", "analyze_stock"]);
assert.equal(responses[2].result.isError, false);
assert.equal(responses[2].result.structuredContent.top_signals.length, 1);
if (responses[2].result.structuredContent.stage === "morning_candidates") {
  assert.equal(responses[2].result.structuredContent.top_signals[0].targets[0].auction.status, "等待09:27竞价");
}

console.log("WORKBUDDY_CONNECTOR_TEST_OK");
