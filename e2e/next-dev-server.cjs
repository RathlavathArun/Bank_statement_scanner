const { spawn } = require("node:child_process");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const webDir = path.join(root, "apps", "web");
const nextBin = path.join(webDir, "node_modules", "next", "dist", "bin", "next");

const child = spawn(process.execPath, [nextBin, "dev", "--webpack"], {
  cwd: webDir,
  stdio: "inherit",
  env: {
    ...process.env,
    NEXT_TELEMETRY_DISABLED: "1",
  },
});

let shuttingDown = false;

function stop(signal) {
  if (shuttingDown) return;
  shuttingDown = true;
  if (!child.killed) {
    child.kill(signal);
  }
}

process.on("SIGINT", () => stop("SIGINT"));
process.on("SIGTERM", () => stop("SIGTERM"));

child.on("exit", (code, signal) => {
  process.exit(code ?? (signal ? 1 : 0));
});

