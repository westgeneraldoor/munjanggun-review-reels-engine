const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const args = ["-m", "unittest", "discover", "-s", "tests"];
const workspaceDeps = path.join(process.cwd(), ".codex_deps");
const basePythonEnv = { ...process.env };

function bundledPythonEnv() {
  const pythonPathEntries = [];
  if (fs.existsSync(workspaceDeps)) {
    pythonPathEntries.push(workspaceDeps);
  }
  if (process.env.PYTHONPATH) {
    pythonPathEntries.push(process.env.PYTHONPATH);
  }
  return {
    ...basePythonEnv,
    ...(pythonPathEntries.length > 0
      ? { PYTHONPATH: pythonPathEntries.join(path.delimiter) }
      : {}),
  };
}

const candidates = [];

if (process.env.PYTHON) {
  candidates.push({ command: process.env.PYTHON, args });
}

candidates.push({ command: "python", args });

if (process.platform === "win32") {
  candidates.push({ command: "py", args: ["-3", ...args] });

  const codexPython = path.join(
    os.homedir(),
    ".cache",
    "codex-runtimes",
    "codex-primary-runtime",
    "dependencies",
    "python",
    "python.exe",
  );
  if (fs.existsSync(codexPython)) {
    candidates.push({ command: codexPython, args, env: bundledPythonEnv() });
  }
}

const failures = [];

for (const candidate of candidates) {
  const result = spawnSync(candidate.command, candidate.args, {
    cwd: process.cwd(),
    encoding: "utf8",
    stdio: "pipe",
    env: candidate.env || basePythonEnv,
  });

  if (result.error && result.error.code === "ENOENT") {
    failures.push(`${candidate.command}: not found`);
    continue;
  }

  const stdout = result.stdout || "";
  const stderr = result.stderr || "";

  if (result.status === 0) {
    process.stdout.write(stdout);
    process.stderr.write(stderr);
    process.exit(0);
  }

  failures.push(`${candidate.command}: exit ${result.status}\n${stdout}${stderr}`);

  if (/FAILED \(|ERROR:|FAIL:/.test(stdout + stderr)) {
    process.stdout.write(stdout);
    process.stderr.write(stderr);
    process.exit(result.status || 1);
  }
}

console.error("Could not run Python tests with any known interpreter.");
console.error(failures.join("\n\n"));
process.exit(1);
