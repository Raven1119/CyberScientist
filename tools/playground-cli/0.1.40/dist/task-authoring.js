import { createHash } from "node:crypto";
import * as fs from "node:fs/promises";
import * as path from "node:path";
export const PREFLIGHT_SCHEMA = "playground-task-preflight/v1";
export const PACKAGE_SCHEMA = "playground-task-package/v1";
export const MAX_FILE_BYTES = 64 * 1024 * 1024;
export const MAX_TOTAL_BYTES = 512 * 1024 * 1024;
const REQUIRED_FILES = ["instruction.md", "task.toml", "tests/test.sh"];
const OPTIONAL = ["environment/resources.yaml", "task_spec.json", "tests/verification_plan.json", "solution", "calibration", "paper"];
const HIDDEN = new Set(["tests", "solution", "calibration", "paper"]);
const GENERATED_BAD = /(^|\/)(__pycache__|\.DS_Store|\.AppleDouble|\.Spotlight-V100|\.Trashes)(\/|$)|\.py[co]$/;
const FORGE_HEADINGS = ["Task and scope", "Method and steps", "Environment and assets", "Deliverables", "Scoring and constraints"];
function classify(rel) {
    const top = rel.split("/")[0];
    if (rel === "instruction.md" || top === "environment")
        return "public_agent_visible";
    if (rel === "task.toml" || rel === "README.md" || rel === "task_spec.json")
        return "trusted_runtime";
    if (HIDDEN.has(top))
        return "hidden_grading";
    return "unknown";
}
function sha(data) { return createHash("sha256").update(data).digest("hex"); }
function object(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value) ? value : undefined;
}
function safePublicString(value) {
    return typeof value === "string" && value.length <= 200 && !/[\r\n]/.test(value) ? value : undefined;
}
function add(findings, severity, code, message, fix, file) {
    findings.push({ severity, code, ...(file ? { path: file } : {}), message, fix });
}
async function readJson(root, rel, findings) {
    try {
        const parsed = JSON.parse(await fs.readFile(path.join(root, rel), "utf8"));
        const result = object(parsed);
        if (!result)
            add(findings, "error", "JSON_ROOT_INVALID", "JSON root must be an object.", "Replace the root value with a JSON object.", rel);
        return result;
    }
    catch (error) {
        if (error?.code !== "ENOENT")
            add(findings, "error", "JSON_MALFORMED", "File is not valid JSON.", "Correct the JSON syntax; preflight never executes or repairs it.", rel);
        return undefined;
    }
}
function tomlShape(text) {
    const sections = new Map();
    let current = "__root__";
    let malformed = false;
    sections.set(current, new Map());
    for (const raw of text.split(/\r?\n/)) {
        const line = raw.trim();
        if (!line || line.startsWith("#"))
            continue;
        if (line.startsWith("[")) {
            const match = line.match(/^\[([A-Za-z0-9_.-]+)\](?:\s*#.*)?$/);
            if (!match) {
                malformed = true;
                current = undefined;
            }
            else {
                current = match[1].split(".")[0];
                if (!sections.has(current))
                    sections.set(current, new Map());
            }
            continue;
        }
        const key = line.match(/^([A-Za-z0-9_-]+)\s*=\s*(.+?)(?:\s+#.*)?$/);
        if (!key || !current) {
            malformed = true;
            continue;
        }
        sections.get(current).set(key[1], key[2].trim());
    }
    return { sections, malformed };
}
function tomlString(raw) {
    if (!raw)
        return undefined;
    const match = raw.match(/^(?:"([^"\r\n]*)"|'([^'\r\n]*)')$/);
    return match ? (match[1] ?? match[2]) : undefined;
}
function scalarLeaks(spec) {
    const hits = [];
    const sensitiveKey = /(doi|url|provenance|expected|reference|tolerance|threshold|rel_tol|abs_tol|bound)/i;
    function visit(value, key = "") {
        if (Array.isArray(value)) {
            for (const item of value)
                visit(item, key);
            return;
        }
        const obj = object(value);
        if (obj) {
            for (const [k, v] of Object.entries(obj))
                visit(v, k);
            return;
        }
        if (!sensitiveKey.test(key))
            return;
        if (typeof value === "string" && value.trim().length >= 4)
            hits.push({ key, value: value.trim() });
        if (typeof value === "number" && Number.isFinite(value) && String(value).length >= 3)
            hits.push({ key, value: String(value) });
    }
    visit(spec);
    return hits;
}
function credentialOrSignedUrl(text) {
    const assignments = text.matchAll(/(?:api[_-]?key|access[_-]?key|secret|password|token)\s*[:=]\s*["']?([^\s"']{8,})/gi);
    for (const match of assignments) {
        const value = match[1];
        if (!/^\$\{?[A-Z][A-Z0-9_]*\}?$/.test(value) && !/^[A-Z][A-Z0-9_]*$/.test(value))
            return true;
    }
    const auth = /Authorization:\s*Bearer\s+\S+|\b(?:sk-|AKIA)[A-Za-z0-9_-]{16,}/i;
    const signed = /https?:\/\/\S+[?&](?:X-Amz-(?:Signature|Credential|Expires)|Signature|Expires|GoogleAccessId|sig|se|sp)=/i;
    return auth.test(text) || signed.test(text);
}
async function validateResources(root, text, findings) {
    if (credentialOrSignedUrl(text))
        add(findings, "error", "RESOURCE_CREDENTIAL", "resources.yaml contains a credential literal or expiring signed URL.", "Declare a credential source/environment-variable name only; never bundle its value or a signed URL.", "environment/resources.yaml");
    const lines = text.split(/\r?\n/);
    let sawResources = false;
    let sawItem = false;
    const paths = [];
    for (const raw of lines) {
        if (/^resources\s*:\s*(?:#.*)?$/.test(raw.trim())) {
            sawResources = true;
            continue;
        }
        if (/^\s*-\s+(?:name|id|path|url|description|credential_(?:source|env)|env)\s*:/.test(raw))
            sawItem = true;
        const match = raw.match(/^\s*(?:-\s*)?path\s*:\s*["']?([^\s#"']+)["']?\s*(?:#.*)?$/);
        if (match)
            paths.push(match[1]);
        if (/^\s*[^#\s][^:]*\s*:\s*[^#]*[{}\[\]&*!]/.test(raw))
            add(findings, "error", "RESOURCES_YAML_UNSUPPORTED", "resources.yaml uses YAML syntax outside the bounded structural subset.", "Use a resources list with plain scalar name, path/url, description, and credential source/env fields.", "environment/resources.yaml");
    }
    if (!sawResources || !sawItem)
        add(findings, "error", "RESOURCES_YAML_STRUCTURE", "resources.yaml must contain a non-empty top-level resources list.", "Add 'resources:' followed by one or more resource mappings.", "environment/resources.yaml");
    for (const ref of paths) {
        const normalized = ref.replace(/^environment\//, "");
        if (path.isAbsolute(normalized) || normalized.split(/[\\/]/).includes("..")) {
            add(findings, "error", "RESOURCE_PATH_ESCAPE", "A bundled resource path must stay under environment/.", "Use a relative path within environment/.", "environment/resources.yaml");
            continue;
        }
        try {
            if (!(await fs.stat(path.join(root, "environment", normalized))).isFile())
                throw new Error();
        }
        catch {
            add(findings, "error", "RESOURCE_PATH_MISSING", `A bundled resource path does not exist under environment/: ${normalized}.`, "Add the referenced file or correct its environment-relative path.", "environment/resources.yaml");
        }
    }
}
export async function preflightTask(taskDir, strict = false) {
    const root = path.resolve(taskDir);
    const findings = [];
    const inventory = [];
    const optionalPresent = [];
    let total = 0;
    let rootReal;
    try {
        rootReal = await fs.realpath(root);
    }
    catch {
        throw new Error(`task directory not found: ${root}`);
    }
    if (!(await fs.stat(rootReal)).isDirectory())
        throw new Error(`task path is not a directory: ${root}`);
    async function walk(current) {
        const entries = await fs.readdir(current, { withFileTypes: true });
        entries.sort((a, b) => a.name.localeCompare(b.name, "en"));
        for (const entry of entries) {
            const absolute = path.join(current, entry.name);
            const rel = path.relative(rootReal, absolute).split(path.sep).join("/");
            const lst = await fs.lstat(absolute);
            if (lst.isSymbolicLink()) {
                add(findings, "error", "SYMLINK_REJECTED", "Symlinks are not packageable because they can escape the task root.", "Replace the symlink with a regular in-root file or directory.", rel);
                continue;
            }
            const real = await fs.realpath(absolute);
            if (real !== rootReal && !real.startsWith(`${rootReal}${path.sep}`)) {
                add(findings, "error", "PATH_ESCAPE", "Path resolves outside the task root.", "Move the content inside the task root.", rel);
                continue;
            }
            if (lst.isDirectory()) {
                await walk(absolute);
                continue;
            }
            if (!lst.isFile()) {
                add(findings, "error", "SPECIAL_FILE", "Only regular files and directories are accepted.", "Remove sockets, devices, and other special files.", rel);
                continue;
            }
            const data = await fs.readFile(absolute);
            total += data.length;
            inventory.push({ path: rel, classification: classify(rel), size_bytes: data.length, sha256: sha(data) });
            if (data.length > MAX_FILE_BYTES)
                add(findings, "error", "FILE_TOO_LARGE", `File exceeds the ${MAX_FILE_BYTES}-byte local limit.`, "Reduce or externally provision this file.", rel);
            if (GENERATED_BAD.test(rel))
                add(findings, "error", "GENERATED_METADATA", "Generated cache or OS metadata is forbidden.", "Remove generated caches and OS metadata before packaging.", rel);
        }
    }
    await walk(rootReal);
    inventory.sort((a, b) => a.path.localeCompare(b.path, "en"));
    const paths = new Set(inventory.map((item) => item.path));
    for (const req of REQUIRED_FILES)
        if (!paths.has(req))
            add(findings, "error", "REQUIRED_PATH_MISSING", `Required path is missing: ${req}.`, `Create ${req} with the documented Paper2Task/LBG contract.`, req);
    try {
        if (!(await fs.stat(path.join(rootReal, "environment"))).isDirectory())
            throw new Error();
    }
    catch {
        add(findings, "error", "REQUIRED_PATH_MISSING", "Required directory is missing: environment/.", "Create environment/; it may be empty, although resources.yaml is recommended.", "environment");
    }
    for (const item of OPTIONAL)
        if (paths.has(item) || inventory.some((entry) => entry.path.startsWith(`${item}/`)))
            optionalPresent.push(item);
    if (!optionalPresent.includes("solution"))
        add(findings, "warning", "SOLUTION_RECOMMENDED", "Harbor permits omitting solution/, but Paper2Task publication should include an Oracle solution.", "Add solution/solve.sh before publication.", "solution");
    else if (!paths.has("solution/solve.sh"))
        add(findings, "error", "SOLUTION_ENTRY_MISSING", "solution/ is present without solution/solve.sh.", "Add the Harbor Oracle entrypoint solution/solve.sh.", "solution/solve.sh");
    for (const forbidden of ["environment/Dockerfile", "environment/docker-compose.yaml", "environment/docker-compose.yml"])
        if (paths.has(forbidden))
            add(findings, "error", "ENVIRONMENT_BUILD_FILE_FORBIDDEN", `${forbidden} is not allowed in the Paper2Task/LBG standard profile.`, "Use the fixed prebuilt [environment].docker_image in task.toml and remove this build file.", forbidden);
    if (paths.has("environment/setup.sh"))
        add(findings, "warning", "SETUP_NOT_AUTOMATIC", "environment/setup.sh has no automatic top-level setup semantics in this profile.", "Invoke it explicitly through the task workflow if needed; do not assume Harbor runs it.", "environment/setup.sh");
    if (inventory.some((entry) => entry.path.startsWith("paper/")))
        add(findings, "error", "ROOT_PAPER_NONSTANDARD", "Root paper/ is hidden grading material and is nonstandard for Agent resources.", "If the paper is an Agent input, move it to environment/reference/paper.pdf and enumerate it in environment/resources.yaml; otherwise keep the hidden source outside the publication package.", "paper");
    const unknownTop = [...new Set(inventory.filter((item) => item.classification === "unknown").map((item) => item.path.split("/")[0]))].sort();
    for (const top of unknownTop)
        add(findings, "warning", "UNKNOWN_TOP_LEVEL", `Unknown top-level path '${top}' has no projection rule.`, "Move public execution input under environment/, runtime metadata to a documented trusted path, or grading material under tests/ or solution/.", top);
    if (total > MAX_TOTAL_BYTES)
        add(findings, "error", "PACKAGE_TOO_LARGE", `Package exceeds the ${MAX_TOTAL_BYTES}-byte local limit.`, "Reduce package size; do not hide large public data inside the task.");
    const hasSpec = paths.has("task_spec.json");
    const hasPlan = paths.has("tests/verification_plan.json");
    if (hasSpec !== hasPlan)
        add(findings, "error", "FORGE_PAIR_INCOMPLETE", "task_spec.json and tests/verification_plan.json are optional but must appear together.", "Add the missing Forge file or remove the unpaired file.");
    const profile = hasSpec && hasPlan ? "standard+forge" : "standard";
    const spec = hasSpec ? await readJson(rootReal, "task_spec.json", findings) : undefined;
    const plan = hasPlan ? await readJson(rootReal, "tests/verification_plan.json", findings) : undefined;
    const outputs = [];
    let workflowSteps = 0;
    if (spec) {
        if (!safePublicString(spec.title))
            add(findings, "error", "TASK_SPEC_TITLE", "task_spec.title must be a short string.", "Add a non-empty title string.", "task_spec.json");
        if (!Array.isArray(spec.workflow) || spec.workflow.length === 0)
            add(findings, "error", "TASK_SPEC_WORKFLOW", "task_spec.workflow must be a non-empty array.", "Declare the complete ordered process and scored workflow.", "task_spec.json");
        else
            workflowSteps = spec.workflow.length;
        if (!Array.isArray(spec.outputs) || spec.outputs.length === 0)
            add(findings, "error", "TASK_SPEC_OUTPUTS", "task_spec.outputs must be a non-empty array.", "Declare each /app/outputs artifact.", "task_spec.json");
        else
            for (const [index, raw] of spec.outputs.entries()) {
                const out = object(raw);
                const file = safePublicString(out?.file);
                const format = safePublicString(out?.format);
                const schemaDeclared = object(out?.schema) !== undefined;
                if (!file || !format || !schemaDeclared)
                    add(findings, "error", "OUTPUT_CONTRACT", `Output ${index} must declare file, format, and object schema.`, "Add a relative output file, explicit format, and JSON schema-like object.", "task_spec.json");
                if (file && format)
                    outputs.push({ file, format, schema_declared: schemaDeclared });
            }
    }
    const claims = Array.isArray(plan?.claims) ? plan.claims.length : 0;
    const checks = Array.isArray(plan?.checks) ? plan.checks.length : 0;
    if (plan && (claims === 0 || checks === 0))
        add(findings, "error", "VERIFICATION_STRUCTURE", "Verification plan requires non-empty claims and checks arrays.", "Model claims and connect each scored check to a public output contract.", "tests/verification_plan.json");
    try {
        const parsed = tomlShape(await fs.readFile(path.join(rootReal, "task.toml"), "utf8"));
        if (parsed.malformed)
            add(findings, "error", "TOML_STRUCTURE_MALFORMED", "task.toml contains a malformed table header or key assignment.", "Use bounded [task], [environment], [agent], and [verifier] tables with simple key assignments.", "task.toml");
        for (const section of ["task", "environment", "agent", "verifier"]) {
            const keys = parsed.sections.get(section);
            if (!keys)
                add(findings, "error", "TOML_SECTION_MISSING", `task.toml is missing [${section}].`, `Add a [${section}] section.`, "task.toml");
            else if (keys.size === 0)
                add(findings, "error", "TOML_SECTION_EMPTY", `task.toml [${section}] has no keys.`, `Add the required runtime keys under [${section}].`, "task.toml");
        }
        const image = tomlString(parsed.sections.get("environment")?.get("docker_image"));
        if (!image)
            add(findings, "error", "DOCKER_IMAGE_REQUIRED", "[environment].docker_image must be a quoted prebuilt image reference.", "Set docker_image to a fixed prebuilt image with an explicit non-latest tag or digest.", "task.toml");
        else if (/\$\{|\{\{|:latest(?:$|@)/i.test(image) || (!image.includes("@sha256:") && !/:[^/]+$/.test(image)))
            add(findings, "error", "DOCKER_IMAGE_NOT_FIXED", "[environment].docker_image is not a fixed image reference.", "Use an explicit non-latest tag or sha256 digest; do not use templates.", "task.toml");
    }
    catch (error) {
        if (error?.code !== "ENOENT")
            throw error;
    }
    try {
        const testScript = await fs.readFile(path.join(rootReal, "tests/test.sh"), "utf8");
        if (!/\/logs\/verifier\/reward\.(?:json|txt)\b/.test(testScript))
            add(findings, "error", "VERIFIER_REWARD_OUTPUT_MISSING", "tests/test.sh does not visibly write the Harbor reward output path.", "Write /logs/verifier/reward.json or /logs/verifier/reward.txt from the verifier script.", "tests/test.sh");
    }
    catch (error) {
        if (error?.code !== "ENOENT")
            throw error;
    }
    if (paths.has("environment/resources.yaml"))
        await validateResources(rootReal, await fs.readFile(path.join(rootReal, "environment/resources.yaml"), "utf8"), findings);
    try {
        const instruction = await fs.readFile(path.join(rootReal, "instruction.md"), "utf8");
        const lower = instruction.toLowerCase();
        const concepts = [["goals", /\b(goal|objective|task)\b/i], ["inputs", /\b(input|resource|asset|data)\b/i], ["outputs", /\b(output|deliverable|artifact|result)\b/i], ["constraints", /\b(constraint|constraints|limit|limits|must|do not|required)\b/i], ["completion criteria", /\b(completion|complete|success|done|criteria|verify|scor)/i]];
        for (const [name, pattern] of concepts)
            if (!pattern.test(instruction))
                add(findings, "warning", "INSTRUCTION_GUIDANCE_MISSING", `instruction.md does not clearly mention ${name}.`, `State the task's ${name} in the public instruction.`, "instruction.md");
        if (paths.has("environment/resources.yaml") && !/(?:environment\/)?resources\.yaml/i.test(instruction))
            add(findings, "warning", "RESOURCE_ENTRY_UNMENTIONED", "instruction.md does not point the Agent to environment/resources.yaml.", "Mention the resource manifest as the entry point for provided inputs.", "instruction.md");
        if (profile === "standard+forge") {
            const actual = [...instruction.matchAll(/^##\s+(.+?)\s*$/gm)].map((m) => m[1]);
            const requiredOrder = FORGE_HEADINGS.every((heading, i) => actual[i] === heading);
            const allowed = new Set([...FORGE_HEADINGS, "Submission interface"]);
            if (!requiredOrder || actual.some((heading) => !allowed.has(heading)))
                add(findings, "error", "INSTRUCTION_SECTIONS", "The enhanced Forge profile requires its exact H2 sections in order.", `Use exactly these H2 sections in order: ${FORGE_HEADINGS.join("; ")}; optional Submission interface last.`, "instruction.md");
        }
        if (/(^|[\s`'"/])(tests|solution|calibration|paper)\//i.test(instruction))
            add(findings, "error", "HIDDEN_PATH_LEAK", "Instruction names a hidden task path.", "State positive deliverables and grading behavior without mapping hidden locations.", "instruction.md");
        if (credentialOrSignedUrl(instruction))
            add(findings, "error", "CREDENTIAL_PATTERN", "Instruction contains a credential literal or expiring signed URL.", "Remove credentials; declare credential source/environment-variable names only.", "instruction.md");
        if (spec)
            for (const leak of [...scalarLeaks(spec), ...(plan ? scalarLeaks(plan) : [])])
                if (lower.includes(leak.value.toLowerCase()))
                    add(findings, "error", "SENSITIVE_VALUE_LEAK", `Instruction appears to copy a hidden ${leak.key} value from trusted authoring data.`, "Remove source identity, reference values, thresholds, and tolerances from the public instruction.", "instruction.md");
    }
    catch (error) {
        if (error?.code !== "ENOENT")
            throw error;
    }
    findings.sort((a, b) => `${a.severity}:${a.code}:${a.path || ""}`.localeCompare(`${b.severity}:${b.code}:${b.path || ""}`, "en"));
    const errors = findings.filter((item) => item.severity === "error").length;
    const warnings = findings.length - errors;
    return { schema_version: PREFLIGHT_SCHEMA, status: errors ? "error" : warnings ? "warning" : "pass", profile, task_root: rootReal, strict, limits: { max_file_bytes: MAX_FILE_BYTES, max_total_bytes: MAX_TOTAL_BYTES }, summary: { files: inventory.length, total_bytes: total, errors, warnings, optional_present: optionalPresent.sort() }, public_metadata: { ...(safePublicString(spec?.title) ? { title: safePublicString(spec?.title) } : {}), workflow_steps: workflowSteps, outputs, checks, claims }, inventory, findings };
}
export function formatPreflight(report) {
    const lines = [`Paper2Task task preflight: ${report.status.toUpperCase()}`, `Profile: ${report.profile}`, `Root: ${report.task_root}`, `Files: ${report.summary.files}; bytes: ${report.summary.total_bytes}; errors: ${report.summary.errors}; warnings: ${report.summary.warnings}`, "", "Inventory (content is never printed):"];
    for (const item of report.inventory)
        lines.push(`  [${item.classification}] ${item.path}  ${item.size_bytes} B  sha256:${item.sha256}`);
    if (report.findings.length) {
        lines.push("", "Findings:");
        for (const item of report.findings)
            lines.push(`  ${item.severity.toUpperCase()} ${item.code}${item.path ? ` (${item.path})` : ""}: ${item.message}\n    Fix: ${item.fix}`);
    }
    else
        lines.push("", "No mechanical preflight findings. Run Harbor Oracle and calibration before publication.");
    lines.push("", "Boundary: instruction.md and environment/** are Agent-visible; task.toml, README.md, and full task_spec.json are trusted runtime metadata; tests/**, solution/**, calibration/**, and nonstandard root paper/** are hidden grading material.");
    lines.push("This check is bounded and mechanical; it does not claim deep semantic leak detection or scientific correctness.");
    return `${lines.join("\n")}\n`;
}
function crc32(data) { let crc = 0xffffffff; for (const byte of data) {
    crc ^= byte;
    for (let i = 0; i < 8; i++)
        crc = (crc >>> 1) ^ (0xedb88320 & -(crc & 1));
} return (crc ^ 0xffffffff) >>> 0; }
export async function writeTaskZip(report, outPath) {
    const local = [];
    const central = [];
    let offset = 0;
    const entries = report.inventory.map((item) => ({ name: item.path, data: Buffer.alloc(0), mode: 0o100644 }));
    if (!report.inventory.some((item) => item.path.startsWith("environment/")))
        entries.unshift({ name: "environment/", data: Buffer.alloc(0), mode: 0o40755 });
    for (const entry of entries) {
        const data = entry.name.endsWith("/") ? entry.data : await fs.readFile(path.join(report.task_root, entry.name));
        const name = Buffer.from(entry.name);
        const crc = crc32(data);
        const header = Buffer.alloc(30);
        header.writeUInt32LE(0x04034b50, 0);
        header.writeUInt16LE(20, 4);
        header.writeUInt16LE(0x800, 6);
        header.writeUInt32LE(crc, 14);
        header.writeUInt32LE(data.length, 18);
        header.writeUInt32LE(data.length, 22);
        header.writeUInt16LE(name.length, 26);
        local.push(header, name, data);
        const record = Buffer.alloc(46);
        record.writeUInt32LE(0x02014b50, 0);
        record.writeUInt16LE(20, 4);
        record.writeUInt16LE(20, 6);
        record.writeUInt16LE(0x800, 8);
        record.writeUInt32LE(crc, 16);
        record.writeUInt32LE(data.length, 20);
        record.writeUInt32LE(data.length, 24);
        record.writeUInt16LE(name.length, 28);
        record.writeUInt32LE((entry.mode << 16) >>> 0, 38);
        record.writeUInt32LE(offset, 42);
        central.push(record, name);
        offset += header.length + name.length + data.length;
    }
    const centralSize = central.reduce((sum, b) => sum + b.length, 0);
    const end = Buffer.alloc(22);
    end.writeUInt32LE(0x06054b50, 0);
    end.writeUInt16LE(entries.length, 8);
    end.writeUInt16LE(entries.length, 10);
    end.writeUInt32LE(centralSize, 12);
    end.writeUInt32LE(offset, 16);
    const zip = Buffer.concat([...local, ...central, end]);
    await fs.mkdir(path.dirname(path.resolve(outPath)), { recursive: true });
    await fs.writeFile(path.resolve(outPath), zip);
    return { sha256: sha(zip), size_bytes: zip.length };
}
