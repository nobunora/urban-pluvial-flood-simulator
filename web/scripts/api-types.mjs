import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";

const webRoot = resolve(import.meta.dirname, "..");
const repositoryRoot = resolve(webRoot, "..");
const openapiPath = resolve(webRoot, "openapi.json");
const generatedPath = resolve(webRoot, "src", "api", "generated.ts");
const checkMode = process.argv[2] === "--check";
const pythonCandidates = process.platform === "win32"
  ? [resolve(repositoryRoot, ".venv", "Scripts", "python.exe"), "python"]
  : [resolve(repositoryRoot, ".venv", "bin", "python"), "python3", "python"];
const python = pythonCandidates.find((candidate) => candidate === "python" || candidate === "python3" || existsSync(candidate));
const openapiCli = resolve(webRoot, "node_modules", "openapi-typescript", "bin", "cli.js");

function run(command, args, cwd) {
  try {
    execFileSync(command, args, { cwd, stdio: "inherit" });
  } catch (error) {
    process.exit(typeof error.status === "number" ? error.status : 1);
  }
}

function generateTypes(inputPath, outputPath) {
  mkdirSync(dirname(outputPath), { recursive: true });
  run(process.execPath, [openapiCli, inputPath, "-o", outputPath], webRoot);
}

function currentOpenApi(outputPath) {
  run(python, ["-m", "scripts.export_openapi", "--output", outputPath], repositoryRoot);
}

if (!python) {
  console.error("No project Python interpreter was found.");
  process.exit(1);
}

if (!checkMode) {
  currentOpenApi(openapiPath);
  generateTypes(openapiPath, generatedPath);
  process.exit(0);
}

const temporaryDirectory = mkdtempSync(join(tmpdir(), "urban-pluvial-flood-api-"));
const temporaryOpenApi = join(temporaryDirectory, "openapi.json");
const temporaryGenerated = join(temporaryDirectory, "generated.ts");
try {
  currentOpenApi(temporaryOpenApi);
  if (!existsSync(openapiPath) || readFileSync(temporaryOpenApi, "utf8") !== readFileSync(openapiPath, "utf8")) {
    console.error("web/openapi.json is out of date; run npm run api:generate.");
    process.exit(1);
  }
  generateTypes(temporaryOpenApi, temporaryGenerated);
  if (!existsSync(generatedPath) || readFileSync(temporaryGenerated, "utf8") !== readFileSync(generatedPath, "utf8")) {
    console.error("web/src/api/generated.ts is out of date; run npm run api:generate.");
    process.exit(1);
  }
} finally {
  rmSync(temporaryDirectory, { recursive: true, force: true });
}
