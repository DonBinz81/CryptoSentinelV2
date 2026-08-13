#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

function fail(message, code = 1) {
  console.error(message);
  process.exit(code);
}

const separatorIndex = process.argv.indexOf("--");
if (separatorIndex === -1) {
  fail("Usage: node scripts/twak-password-file.cjs --password-file <path> -- <twak args...>");
}

const wrapperArgs = process.argv.slice(2, separatorIndex);
const twakArgs = process.argv.slice(separatorIndex + 1);
const passwordFileIndex = wrapperArgs.indexOf("--password-file");

if (passwordFileIndex === -1 || !wrapperArgs[passwordFileIndex + 1]) {
  fail("Missing --password-file <path>");
}
if (twakArgs.length === 0) {
  fail("Missing TWAK command after --");
}

const passwordPath = path.resolve(wrapperArgs[passwordFileIndex + 1]);
let password;
try {
  password = fs.readFileSync(passwordPath, "utf8");
} catch (error) {
  fail(`Unable to read password file: ${error.message}`);
}

// Allow a standard text-file newline without changing any other character.
password = password.replace(/\r?\n$/, "");
if (!password) {
  fail("Password file is empty");
}

const resolvedTwakArgs = [];
for (const arg of twakArgs) {
  if (arg === "--password-from-file") {
    resolvedTwakArgs.push("--password", password);
  } else {
    resolvedTwakArgs.push(arg);
  }
}

const globalRootResult = spawnSync(process.platform === "win32" ? "npm.cmd" : "npm", ["root", "-g"], {
  encoding: "utf8",
});
const globalRoots = [];
if (globalRootResult.status === 0 && globalRootResult.stdout.trim()) {
  globalRoots.push(globalRootResult.stdout.trim());
}
if (process.platform === "win32" && process.env.APPDATA) {
  globalRoots.push(path.join(process.env.APPDATA, "npm", "node_modules"));
}
globalRoots.push(path.join(process.env.HOME || "", ".npm-global", "lib", "node_modules"));

const cliEntrypoint = globalRoots
  .map((root) => path.join(root, "@trustwallet", "cli", "dist", "index.js"))
  .find((candidate) => fs.existsSync(candidate));
if (!cliEntrypoint) {
  fail("TWAK CLI entrypoint not found. Install @trustwallet/cli globally.");
}

const result = spawnSync(process.execPath, [cliEntrypoint, ...resolvedTwakArgs], {
  env: {
    ...process.env,
    TWAK_WALLET_PASSWORD: password,
  },
  encoding: "utf8",
  stdio: ["ignore", "inherit", "inherit"],
});

process.exit(result.status ?? 1);
