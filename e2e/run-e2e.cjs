const { spawn } = require("node:child_process");
const http = require("node:http");
const path = require("node:path");

const root = path.resolve(__dirname, "..");

function waitForUrl(url, timeoutMs = 30_000) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const check = () => {
      const request = http.get(url, (response) => {
        response.resume();
        resolve();
      });
      request.on("error", () => {
        if (Date.now() - started > timeoutMs) {
          reject(new Error(`Timed out waiting for ${url}`));
          return;
        }
        setTimeout(check, 500);
      });
    };
    check();
  });
}

function killTree(child) {
  if (!child.pid) return Promise.resolve();
  if (process.platform === "win32") {
    return new Promise((resolve) => {
      const killer = spawn("taskkill", ["/PID", String(child.pid), "/T", "/F"], {
        stdio: "ignore",
      });
      killer.on("exit", resolve);
    });
  }
  child.kill("SIGTERM");
  return Promise.resolve();
}

async function main() {
  const server = spawn(process.execPath, [path.join(root, "e2e", "next-dev-server.cjs")], {
    cwd: root,
    stdio: "inherit",
    env: {
      ...process.env,
      NEXT_TELEMETRY_DISABLED: "1",
    },
  });

  try {
    await waitForUrl("http://localhost:3000");
    const testCommand = process.platform === "win32" ? "cmd.exe" : "npx";
    const testArgs = process.platform === "win32"
      ? ["/d", "/s", "/c", "npx.cmd playwright test"]
      : ["playwright", "test"];
    const tests = spawn(testCommand, testArgs, {
      cwd: root,
      stdio: "inherit",
      env: {
        ...process.env,
        PW_SKIP_WEB_SERVER: "1",
      },
    });

    const exitCode = await new Promise((resolve) => {
      tests.on("exit", (code) => resolve(code ?? 1));
    });
    await killTree(server);
    process.exit(exitCode);
  } catch (error) {
    console.error(error);
    await killTree(server);
    process.exit(1);
  }
}

main();
