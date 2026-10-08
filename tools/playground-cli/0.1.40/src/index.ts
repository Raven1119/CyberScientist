#!/usr/bin/env node
import { createHash, randomBytes } from "node:crypto";
import { spawn } from "node:child_process";
import * as fs from "node:fs/promises";
import { createReadStream, type Dirent } from "node:fs";
import * as http from "node:http";
import * as https from "node:https";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { PACKAGE_SCHEMA, formatPreflight, preflightTask, writeTaskZip } from "./task-authoring.js";

type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
type OptValue = string | boolean | string[];

const VERSION = "0.1.40";
const DEFAULT_PLAY_API = "https://play.bohrium.com/";
const DEFAULT_WORKER_API = "http://47.92.88.121:443/api";
const WORKER_MAX_UPLOAD_BYTES = 512 * 1024 * 1024;
const WORKER_MAX_TASK_PACKAGE_BYTES = 128 * 1024 * 1024;
const WORKER_MAX_RESPONSE_BYTES = 1024 * 1024;
const DEFAULT_CONFIG_PATH = path.resolve(
  process.env.PLAYGROUND_CONFIG_PATH || path.join(os.homedir(), ".playground", "config.json"),
);
const DEFAULT_CREDENTIALS_PATH = path.resolve(
  process.env.PLAYGROUND_CREDENTIALS_PATH || path.join(os.homedir(), ".config", "playground", "credentials.env"),
);
const DEFAULT_UPDATE_URL = "https://play.bohrium.com/latest.json";
const UPDATE_CACHE_PATH = path.join(os.homedir(), ".config", "playground", "update-check.json");
const UPDATE_CACHE_TTL_MS = 24 * 60 * 60 * 1000;
const DEFAULT_WENYON_INSTALLER = "https://wenyon.dp.tech/install.sh";
const DEFAULT_DATA_LIST_LIMIT = 20;
const LOADED_SAVED_CREDENTIALS = new Set<string>();
const SECRET_PATTERNS = [
  /BOHRIUM_ACCESS_KEY\s*=/i,
  /Authorization:\s*Bearer\s+[A-Za-z0-9._-]{16,}/i,
  /\bsk-[A-Za-z0-9_-]{20,}\b/,
  /\bAKIA[0-9A-Z]{16}\b/,
];
const TRACE_SECRET_PATTERNS = [
  /asp_[a-zA-Z0-9]{40,}/g,
  /(Bearer\s+)[A-Za-z0-9._-]{20,}/gi,
];
const ARM_STEP_TYPES = new Set([
  "thought",
  "tool_call",
  "tool_result",
  "artifact",
  "decision",
  "error",
  "observation",
]);
const PRICE_IN: Record<string, number> = {
  "deepseek-v4-pro": 0.27,
  "deepseek-v3": 0.14,
  "claude-opus-4-7": 15.0,
  "claude-sonnet-4-6": 3.0,
  "claude-opus-4-5": 15.0,
  "claude-sonnet-4-5": 3.0,
  "gpt-4o": 2.5,
  "gpt-4o-mini": 0.15,
  "gpt-5": 5.0,
};
const PRICE_OUT: Record<string, number> = {
  "deepseek-v4-pro": 1.10,
  "deepseek-v3": 0.28,
  "claude-opus-4-7": 75.0,
  "claude-sonnet-4-6": 15.0,
  "claude-opus-4-5": 75.0,
  "claude-sonnet-4-5": 15.0,
  "gpt-4o": 10.0,
  "gpt-4o-mini": 0.60,
  "gpt-5": 15.0,
};

interface ParsedArgs {
  commands: string[];
  opts: Record<string, OptValue>;
}

interface BundleResult {
  bundlePath: string;
  manifest: Record<string, Json>;
  traceSteps: Record<string, Json>[];
  rawMessagesData?: Buffer;
  rawMessagesFilename?: string;
}

interface SkillEvidence {
  name: string;
  bundled_path: string;
  detection: "explicit" | "trace-path" | "trace-tool-call";
  evidence: string[];
  skill_md_sha256: string;
  files: Array<{ path: string; sha256: string; size_bytes: number }>;
}

interface ClaudeAtifBundle {
  trajectory: Record<string, Json>;
  subagentPaths: string[];
}

interface MultipartFile {
  name: string;
  filename: string;
  contentType: string;
  data: Buffer;
}

interface DatasetRef {
  dataset: string;
  version?: string;
  prefix?: string;
  paths?: string[];
  path?: string;
  sha256?: string;
  bytes?: number;
}

class CliError extends Error {
  exitCode: number;
  constructor(message: string, exitCode = 1) {
    super(message);
    this.exitCode = exitCode;
  }
}

function utcNow(): string {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}

async function loadSavedCredentials(): Promise<void> {
  try {
    const text = await fs.readFile(DEFAULT_CREDENTIALS_PATH, "utf8");
    for (const name of ["PLAYGROUND_TOKEN", "PLAYGROUND_PASSWORD", "PLAYGROUND_EMAIL"]) {
      if (process.env[name]) continue;
      const match = text.match(new RegExp(`^${name}=(.*)$`, "m"));
      if (match?.[1]) {
        process.env[name] = decodeEnvValue(match[1].trim());
        LOADED_SAVED_CREDENTIALS.add(name);
      }
    }
  } catch (error: any) {
    if (error?.code !== "ENOENT") throw error;
  }
}

function encodeEnvValue(value: string): string {
  if (/^[A-Za-z0-9_@%+=:,./-]+$/.test(value)) return value;
  return `'${value.replace(/'/g, `'\"'\"'`)}'`;
}

function decodeEnvValue(value: string): string {
  if (value.startsWith("'") && value.endsWith("'")) {
    return value.slice(1, -1).replace(/'\"'\"'/g, "'");
  }
  if (value.startsWith('"') && value.endsWith('"')) {
    return value.slice(1, -1);
  }
  return value;
}

async function readCredentialsFileEnv(credentialsPath: string): Promise<Record<string, string>> {
  try {
    const text = await fs.readFile(credentialsPath, "utf8");
    const env: Record<string, string> = {};
    for (const line of text.split(/\r?\n/)) {
      const match = line.match(/^([A-Z0-9_]+)=(.*)$/);
      if (!match) continue;
      env[match[1]] = decodeEnvValue(match[2].trim());
    }
    return env;
  } catch (error: any) {
    if (error?.code === "ENOENT") return {};
    throw error;
  }
}

async function saveCredentialsFile(
  credentialsPath: string,
  token: string,
  details: { email?: string; password?: string } = {},
  activate = false,
): Promise<void> {
  const lines = [`PLAYGROUND_TOKEN=${encodeEnvValue(token)}`];
  if (details.email) lines.push(`PLAYGROUND_EMAIL=${encodeEnvValue(details.email)}`);
  if (details.password) lines.push(`PLAYGROUND_PASSWORD=${encodeEnvValue(details.password)}`);
  const credentialsDir = path.dirname(credentialsPath);
  await fs.mkdir(credentialsDir, { recursive: true, mode: 0o700 });
  await fs.chmod(credentialsDir, 0o700);
  await fs.writeFile(credentialsPath, `${lines.join("\n")}\n`, { mode: 0o600 });
  await fs.chmod(credentialsPath, 0o600);
  if (activate) {
    process.env.PLAYGROUND_TOKEN = token;
    if (details.email) process.env.PLAYGROUND_EMAIL = details.email;
    if (details.password) process.env.PLAYGROUND_PASSWORD = details.password;
  }
}

async function savePlaygroundCredentials(
  token: string,
  details: { email?: string; password?: string } = {},
): Promise<void> {
  await saveCredentialsFile(DEFAULT_CREDENTIALS_PATH, token, details, true);
}

function generateRegistrationPassword(): string {
  // base64url is shell/.env-safe; the suffix guarantees common complexity rules.
  return `${randomBytes(32).toString("base64url")}Aa1`;
}

function parseArgs(argv: string[]): ParsedArgs {
  const commands: string[] = [];
  const opts: Record<string, OptValue> = {};
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "-h") {
      opts.help = true;
      continue;
    }
    if (!arg.startsWith("--")) {
      commands.push(arg);
      continue;
    }
    const eq = arg.indexOf("=");
    const key = eq >= 0 ? arg.slice(2, eq) : arg.slice(2);
    let value: string | boolean = eq >= 0 ? arg.slice(eq + 1) : true;
    if (eq < 0 && argv[i + 1] && !argv[i + 1].startsWith("--")) {
      value = argv[i + 1];
      i += 1;
    }
    const existing = opts[key];
    if (existing === undefined) {
      opts[key] = value;
    } else if (Array.isArray(existing)) {
      existing.push(String(value));
    } else {
      opts[key] = [String(existing), String(value)];
    }
  }
  return { commands, opts };
}

function opt(opts: Record<string, OptValue>, key: string): string | undefined {
  const value = opts[key];
  if (value === undefined || typeof value === "boolean") return undefined;
  if (Array.isArray(value)) return value[value.length - 1];
  return value;
}

function optAll(opts: Record<string, OptValue>, key: string): string[] {
  const value = opts[key];
  if (value === undefined || typeof value === "boolean") return [];
  return Array.isArray(value) ? value : [value];
}

function flag(opts: Record<string, OptValue>, key: string): boolean {
  return opts[key] === true || opts[key] === "true";
}

function required(opts: Record<string, OptValue>, key: string): string {
  const value = opt(opts, key);
  if (!value) throw new CliError(`missing --${key}`);
  return value;
}

function asPlainObject(value: unknown): Record<string, any> | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, any> : undefined;
}

function isPlainRecord(value: unknown): value is Record<string, any> {
  return Boolean(asPlainObject(value));
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}

function timestampValue(value: unknown): string | undefined {
  const text = stringValue(value);
  if (text) return text;
  if (typeof value !== "number" || !Number.isFinite(value)) return undefined;
  const millis = value > 1_000_000_000_000 ? value : value * 1000;
  try {
    return new Date(millis).toISOString().replace(/\.\d{3}Z$/, "Z");
  } catch {
    return undefined;
  }
}

function numberValue(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return 0;
}

function stableStepId(prefix: string, source: string, index: number): string {
  const digest = createHash("sha1").update(`${source}:${index}`).digest("hex").slice(0, 8);
  return `${prefix}_${index}_${digest}`;
}

function tracePrice(model: string | undefined, kind: "in" | "out"): number {
  const lower = (model || "").toLowerCase();
  const table = kind === "in" ? PRICE_IN : PRICE_OUT;
  for (const [name, price] of Object.entries(table)) {
    if (lower.includes(name)) return price;
  }
  return kind === "in" ? 0.50 : 1.50;
}

function estimateCostUsd(model: string | undefined, tokensIn: number, tokensOut: number): number {
  return Number(((tokensIn * tracePrice(model, "in") + tokensOut * tracePrice(model, "out")) / 1_000_000).toFixed(6));
}

function isoNoMillis(millis: number): string {
  return new Date(millis).toISOString().replace(/\.\d{3}Z$/, "Z");
}

function timestampMillis(value: unknown): number | undefined {
  if (typeof value !== "string" || !value.trim()) return undefined;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function redactTraceText(text: string): { text: string; redactions: number } {
  let redactions = 0;
  let clean = text;
  clean = clean.replace(TRACE_SECRET_PATTERNS[0], () => {
    redactions += 1;
    return "<asp_TOKEN_REDACTED>";
  });
  clean = clean.replace(TRACE_SECRET_PATTERNS[1], (_match, prefix: string) => {
    redactions += 1;
    return `${prefix}<REDACTED>`;
  });
  return { text: clean, redactions };
}

function objectRowsFromJsonl(text: string): Record<string, any>[] {
  const rows: Record<string, any>[] = [];
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      const parsed = JSON.parse(trimmed);
      const obj = asPlainObject(parsed);
      if (obj) rows.push(obj);
    } catch {
      // Ignore non-JSON diagnostic lines in native trajectory logs.
    }
  }
  return rows;
}

function normalizeArmSteps(rows: Record<string, any>[]): Record<string, Json>[] {
  const steps: Record<string, Json>[] = [];
  for (const [index, row] of rows.entries()) {
    const stepType = stringValue(row.step_type) || stringValue(row.type);
    if (!stepType || !ARM_STEP_TYPES.has(stepType)) continue;
    const step: Record<string, Json> = { ...(row as Record<string, Json>) };
    step.step_type = stepType;
    step.type = stepType;
    step.step_order = numberValue(step.step_order) || index + 1;
    if (!step.timestamp) step.timestamp = utcNow();
    steps.push(step);
  }
  return steps;
}

function nativeTraceLike(rows: Record<string, any>[]): boolean {
  return rows.some((row) => {
    const type = stringValue(row.type);
    return Boolean(type && type.includes(".") && !ARM_STEP_TYPES.has(type));
  });
}

function bodyFromContent(content: unknown): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content.map((item) => {
      const obj = asPlainObject(item);
      if (obj) return String(obj.text ?? obj.content ?? JSON.stringify(obj));
      return String(item);
    }).join("\n");
  }
  if (content === undefined || content === null) return "";
  return typeof content === "object" ? JSON.stringify(content) : String(content);
}

function contentTextFromRow(row: Record<string, any>): string {
  return bodyFromContent(row.content ?? row.text ?? row.message ?? row.body);
}

function jsonValue(value: unknown): Json {
  if (value === undefined) return null;
  try {
    return JSON.parse(JSON.stringify(value)) as Json;
  } catch {
    return String(value);
  }
}

function attachResourceSignals(
  step: Record<string, Json>,
  modelId: string | undefined,
  tokensIn: number,
  tokensOut: number,
  costUsd: number,
): void {
  if (modelId) step.model_id = modelId;
  if (tokensIn) step.tokens_in = tokensIn;
  if (tokensOut) step.tokens_out = tokensOut;
  if (costUsd) step.cost_usd = costUsd;
  else if (tokensIn || tokensOut) step.cost_usd = estimateCostUsd(modelId, tokensIn, tokensOut);
}

function metricsSignals(metrics: Record<string, any> | undefined, modelId: string | undefined): {
  tokensIn: number;
  tokensOut: number;
  costUsd: number;
} {
  const tokensIn = numberValue(metrics?.prompt_tokens ?? metrics?.prompt ?? metrics?.input_tokens ?? metrics?.input ?? metrics?.tokens_in);
  const tokensOut = numberValue(metrics?.completion_tokens ?? metrics?.completion ?? metrics?.output_tokens ?? metrics?.output ?? metrics?.tokens_out);
  const costUsd = numberValue(metrics?.cost_usd);
  return { tokensIn, tokensOut, costUsd: costUsd || estimateCostUsd(modelId, tokensIn, tokensOut) };
}

function appendToolBlocks(
  steps: Record<string, Json>[],
  messages: unknown,
  timestamp: string,
  source: string,
  rowIndex: number,
): void {
  if (!Array.isArray(messages)) return;
  let blockIndex = 0;
  for (const message of messages) {
    const msg = asPlainObject(message);
    if (!msg || !Array.isArray(msg.content)) continue;
    const msgTs = stringValue(msg.timestamp) || timestamp;
    for (const blockRaw of msg.content) {
      const block = asPlainObject(blockRaw);
      if (!block) continue;
      const type = stringValue(block.type);
      if (type === "tool_use") {
        const id = stringValue(block.id) || stableStepId("tool", source, rowIndex + blockIndex);
        steps.push({
          step_type: "tool_call",
          type: "tool_call",
          step_id: stableStepId("tc", source, rowIndex + blockIndex),
          step_order: steps.length + 1,
          tool_call_id: id,
          tool_name: stringValue(block.name) || "unknown",
          tool_args: (asPlainObject(block.input) || {}) as unknown as Json,
          timestamp: msgTs,
        });
      } else if (type === "tool_result") {
        steps.push({
          step_type: "tool_result",
          type: "tool_result",
          step_id: stableStepId("tr", source, rowIndex + blockIndex),
          step_order: steps.length + 1,
          tool_call_id: stringValue(block.tool_use_id) || "",
          tool_output: bodyFromContent(block.content).slice(0, 8000),
          timestamp: msgTs,
        });
      }
      blockIndex += 1;
    }
  }
}

function convertHarborAtifRows(
  rows: Record<string, any>[],
  source: string,
  root: Record<string, any> = {},
): Record<string, Json>[] {
  const steps: Record<string, Json>[] = [];
  const agent = asPlainObject(root.agent) || {};
  const defaultModel = stringValue(agent.model_name);

  for (const [index, row] of rows.entries()) {
    const sourceRole = stringValue(row.source) || stringValue(row.role);
    const hasAtifShape = Boolean(sourceRole || row.message !== undefined || row.text !== undefined || row.tool_calls || row.toolCalls || row.observation || row.metrics || row.tokens);
    if (!hasAtifShape) continue;

    const timestamp = timestampValue(row.timestamp) || "";
    const modelId = stringValue(row.model_name) || defaultModel;
    const metrics = metricsSignals(asPlainObject(row.metrics) || asPlainObject(row.tokens), modelId);
    const message = bodyFromContent(row.message ?? row.content ?? row.text).trim();
    const reasoning = stringValue(row.reasoning_content) || stringValue(row.reasoning);
    const toolCalls = Array.isArray(row.tool_calls) ? row.tool_calls : Array.isArray(row.toolCalls) ? row.toolCalls : [];
    const observation = asPlainObject(row.observation);
    const observationResults = Array.isArray(observation?.results) ? observation?.results : [];
    const observationText = typeof row.observation === "string" ? row.observation : bodyFromContent(row.observation_text ?? row.tool_output).trim();
    const role = sourceRole || (toolCalls.length ? "agent" : "user");

    if (role !== "agent") {
      const body = message || contentTextFromRow(row);
      if (body) {
        steps.push({
          step_type: "observation",
          type: "observation",
          step_id: stableStepId("obs", source, index),
          step_order: steps.length + 1,
          title: role,
          body: body.slice(0, 8000),
          timestamp,
        });
      }
      continue;
    }

    const thoughtBody = [
      reasoning ? `[reasoning]\n${reasoning}` : "",
      message,
    ].filter(Boolean).join("\n\n").trim();
    let metricsAttached = false;
    if (thoughtBody || (!toolCalls.length && !observationResults.length)) {
      const step: Record<string, Json> = {
        step_type: "thought",
        type: "thought",
        step_id: stableStepId("thought", source, index),
        step_order: steps.length + 1,
        title: "agent",
        body: (thoughtBody || "(agent step)").slice(0, 8000),
        timestamp,
      };
      attachResourceSignals(step, modelId, metrics.tokensIn, metrics.tokensOut, metrics.costUsd);
      metricsAttached = true;
      steps.push(step);
    }

    for (const [toolIndex, toolRaw] of toolCalls.entries()) {
      const tool = asPlainObject(toolRaw);
      if (!tool) continue;
      const id = stringValue(tool.tool_call_id) || stringValue(tool.id) || stableStepId("tool", source, index * 1000 + toolIndex);
      const rawArgs = asPlainObject(tool.arguments) || tool.arguments || asPlainObject(tool.args) || tool.args || {};
      const step: Record<string, Json> = {
        step_type: "tool_call",
        type: "tool_call",
        step_id: stableStepId("tc", source, index * 1000 + toolIndex),
        step_order: steps.length + 1,
        tool_call_id: id,
        tool_name: stringValue(tool.function_name) || stringValue(tool.name) || "unknown",
        tool_args: jsonValue(rawArgs),
        timestamp,
      };
      if (!metricsAttached) {
        attachResourceSignals(step, modelId, metrics.tokensIn, metrics.tokensOut, metrics.costUsd);
        metricsAttached = true;
      }
      steps.push(step);
    }

    if (observationText && toolCalls.length) {
      const firstTool = asPlainObject(toolCalls[0]);
      steps.push({
        step_type: "tool_result",
        type: "tool_result",
        step_id: stableStepId("tr", source, index * 1000),
        step_order: steps.length + 1,
        tool_call_id: firstTool
          ? stringValue(firstTool.tool_call_id) || stringValue(firstTool.id) || stableStepId("tool", source, index * 1000)
          : stableStepId("tool", source, index * 1000),
        tool_output: observationText.slice(0, 8000),
        timestamp,
      });
    }

    for (const [resultIndex, resultRaw] of observationResults.entries()) {
      const result = asPlainObject(resultRaw);
      if (!result) continue;
      const output = bodyFromContent(result.content).slice(0, 8000);
      if (!output) continue;
      steps.push({
        step_type: "tool_result",
        type: "tool_result",
        step_id: stableStepId("tr", source, index * 1000 + resultIndex),
        step_order: steps.length + 1,
        tool_call_id: stringValue(result.source_call_id) || "",
        tool_output: output,
        timestamp,
      });
    }
  }

  return steps;
}

function convertNativeTrajectoryRows(rows: Record<string, any>[], source: string): Record<string, Json>[] {
  const steps: Record<string, Json>[] = [];
  let modelId: string | undefined;
  for (const [index, row] of rows.entries()) {
    const recordType = stringValue(row.type) || "";
    const timestamp = timestampValue(row.ts) || timestampValue(row.timestamp) || utcNow();
    const data = asPlainObject(row.data) || {};
    modelId = modelId || stringValue(row.modelId) || stringValue(data.modelId) || stringValue(data.model);

    if (recordType === "prompt.submitted") {
      const prompt = stringValue(data.prompt)?.trim();
      if (prompt) {
        steps.push({
          step_type: "observation",
          type: "observation",
          step_id: stableStepId("obs", source, index),
          step_order: steps.length + 1,
          timestamp,
          body: `[user prompt] ${prompt.slice(0, 8000)}`,
        });
      }
      continue;
    }

    if (recordType === "model.completed") {
      const usage = asPlainObject(data.usage) || {};
      const tokensIn = numberValue(usage.input ?? usage.input_tokens ?? usage.prompt_tokens);
      const tokensOut = numberValue(usage.output ?? usage.output_tokens ?? usage.completion_tokens);
      const texts = Array.isArray(data.assistantTexts) ? data.assistantTexts : [];
      let usedUsage = false;
      for (const textRaw of texts) {
        const text = String(textRaw || "").trim();
        if (!text) continue;
        const step: Record<string, Json> = {
          step_type: "thought",
          type: "thought",
          step_id: stableStepId("thought", source, index + steps.length),
          step_order: steps.length + 1,
          timestamp,
          body: text.slice(0, 8000),
        };
        if (modelId) step.model_id = modelId;
        if (!usedUsage && (tokensIn || tokensOut)) {
          step.tokens_in = tokensIn;
          step.tokens_out = tokensOut;
          step.cost_usd = estimateCostUsd(modelId, tokensIn, tokensOut);
          usedUsage = true;
        }
        steps.push(step);
      }
      if (texts.length === 0 && (tokensIn || tokensOut)) {
        steps.push({
          step_type: "thought",
          type: "thought",
          step_id: stableStepId("thought", source, index),
          step_order: steps.length + 1,
          timestamp,
          body: "(no assistant text)",
          model_id: modelId || "",
          tokens_in: tokensIn,
          tokens_out: tokensOut,
          cost_usd: estimateCostUsd(modelId, tokensIn, tokensOut),
        });
      }
      appendToolBlocks(steps, data.messagesSnapshot, timestamp, source, index * 1000);
      if (data.aborted || data.timedOut || data.idleTimedOut) {
        steps.push({
          step_type: "error",
          type: "error",
          step_id: stableStepId("err", source, index),
          step_order: steps.length + 1,
          timestamp,
          body: `model run failed: aborted=${Boolean(data.aborted)} timedOut=${Boolean(data.timedOut)} idleTimedOut=${Boolean(data.idleTimedOut)}`,
        });
      }
      continue;
    }

    if (recordType === "session.ended" && data.status && data.status !== "success") {
      steps.push({
        step_type: "error",
        type: "error",
        step_id: stableStepId("err", source, index),
        step_order: steps.length + 1,
        timestamp,
        body: `session ended with status=${String(data.status)}`,
      });
    }
  }
  return steps;
}

function opencodeEventLike(rows: Record<string, any>[]): boolean {
  return rows.some((row) => ["step_start", "step_finish", "text", "tool_use", "error"].includes(stringValue(row.type) || ""));
}

function convertOpenCodeEvents(rows: Record<string, any>[], source: string): Record<string, Json>[] {
  const steps: Record<string, Json>[] = [];
  const turns: { timestamp: string; parts: Record<string, any>[]; finish?: Record<string, any> }[] = [];
  let current: { timestamp: string; parts: Record<string, any>[]; finish?: Record<string, any> } | undefined;

  for (const [index, row] of rows.entries()) {
    const type = stringValue(row.type) || "";
    const timestamp = timestampValue(row.timestamp) || timestampValue(row.ts) || utcNow();
    if (type === "step_start") {
      current = { timestamp, parts: [] };
      continue;
    }
    if (type === "step_finish") {
      if (current) {
        current.finish = asPlainObject(row.part) || {};
        turns.push(current);
        current = undefined;
      }
      continue;
    }
    if (current && (type === "text" || type === "tool_use")) {
      current.parts.push(asPlainObject(row.part) || row);
      continue;
    }
    if (!current && (type === "text" || type === "tool_use")) {
      turns.push({ timestamp, parts: [asPlainObject(row.part) || row] });
      continue;
    }
    if (type === "error") {
      steps.push({
        step_type: "error",
        type: "error",
        step_id: stableStepId("err", source, index),
        step_order: steps.length + 1,
        body: bodyFromContent(row.error ?? row.message ?? row.part ?? row).slice(0, 8000),
        timestamp,
      });
    }
  }

  for (const [turnIndex, turn] of turns.entries()) {
    const finish = turn.finish || {};
    const tokens = asPlainObject(finish.tokens) || {};
    const cache = asPlainObject(tokens.cache) || {};
    const modelId = stringValue(finish.model) || stringValue(finish.modelID) || stringValue(finish.modelId);
    const tokensIn = numberValue(tokens.input) + numberValue(cache.read);
    const tokensOut = numberValue(tokens.output);
    const costUsd = numberValue(finish.cost) || estimateCostUsd(modelId, tokensIn, tokensOut);
    let metricsAttached = false;
    const textParts: string[] = [];

    for (const part of turn.parts) {
      if (stringValue(part.type) === "text" && stringValue(part.text)) {
        textParts.push(String(part.text).trim());
      }
    }

    const body = textParts.join("\n\n").trim();
    if (body) {
      const step: Record<string, Json> = {
        step_type: "thought",
        type: "thought",
        step_id: stableStepId("thought", source, turnIndex),
        step_order: steps.length + 1,
        body: body.slice(0, 8000),
        timestamp: turn.timestamp,
      };
      attachResourceSignals(step, modelId, tokensIn, tokensOut, costUsd);
      metricsAttached = true;
      steps.push(step);
    }

    for (const [partIndex, part] of turn.parts.entries()) {
      const type = stringValue(part.type);
      if (type === "text") continue;
      if (type !== "tool" && type !== "tool_use") continue;
      const state = asPlainObject(part.state) || {};
      const id = stringValue(part.callID) || stringValue(part.callId) || stringValue(part.id) || stableStepId("tool", source, turnIndex * 1000 + partIndex);
      const step: Record<string, Json> = {
        step_type: "tool_call",
        type: "tool_call",
        step_id: stableStepId("tc", source, turnIndex * 1000 + partIndex),
        step_order: steps.length + 1,
        tool_call_id: id,
        tool_name: stringValue(part.tool) || stringValue(part.name) || "unknown",
        tool_args: jsonValue(asPlainObject(state.input) || state.input || {}),
        timestamp: turn.timestamp,
      };
      if (!metricsAttached) {
        attachResourceSignals(step, modelId, tokensIn, tokensOut, costUsd);
        metricsAttached = true;
      }
      steps.push(step);
      if (state.output !== undefined) {
        steps.push({
          step_type: "tool_result",
          type: "tool_result",
          step_id: stableStepId("tr", source, turnIndex * 1000 + partIndex),
          step_order: steps.length + 1,
          tool_call_id: id,
          tool_output: bodyFromContent(state.output).slice(0, 8000),
          timestamp: turn.timestamp,
        });
      }
    }
  }

  return steps;
}

function openCodeExportLike(obj: Record<string, any>): boolean {
  const info = asPlainObject(obj.info);
  return Boolean(info && stringValue(info.id)?.startsWith("ses_") && Array.isArray(obj.messages));
}

function convertOpenCodeExport(obj: Record<string, any>, source: string): Record<string, Json>[] {
  const steps: Record<string, Json>[] = [];
  const messages = Array.isArray(obj.messages) ? obj.messages : [];

  for (const [messageIndex, messageRaw] of messages.entries()) {
    const message = asPlainObject(messageRaw);
    if (!message) continue;

    const info = asPlainObject(message.info) || {};
    const role = stringValue(info.role) || "unknown";
    const time = asPlainObject(info.time) || {};
    const created = numberValue(time.created);
    const timestamp = created ? isoNoMillis(created) : utcNow();
    const model = asPlainObject(info.model) || {};
    const modelId = stringValue(info.modelID) || stringValue(model.modelID) || stringValue(model.id);
    const providerId = stringValue(info.providerID) || stringValue(model.providerID);
    const fullModelId = providerId && modelId && !modelId.includes("/") ? `${providerId}/${modelId}` : modelId;
    const tokens = asPlainObject(info.tokens) || {};
    const cache = asPlainObject(tokens.cache) || {};
    const tokensIn = numberValue(tokens.input) + numberValue(cache.read);
    const tokensOut = numberValue(tokens.output) + numberValue(tokens.reasoning);
    const costUsd = numberValue(info.cost) || estimateCostUsd(fullModelId, tokensIn, tokensOut);
    const parts = Array.isArray(message.parts) ? message.parts : [];
    let metricsAttached = false;

    for (const [partIndex, partRaw] of parts.entries()) {
      const part = asPlainObject(partRaw);
      if (!part) continue;
      const type = stringValue(part.type) || "part";

      if (type === "step-start") continue;

      if (type === "tool") {
        const state = asPlainObject(part.state) || {};
        const id = stringValue(part.callID) || stringValue(part.callId) || stringValue(part.id) || stableStepId("tool", source, messageIndex * 1000 + partIndex);
        const callStep: Record<string, Json> = {
          step_type: "tool_call",
          type: "tool_call",
          step_id: stableStepId("tc", source, messageIndex * 1000 + partIndex),
          step_order: steps.length + 1,
          title: stringValue(state.title) || `${stringValue(part.tool) || "tool"} call`,
          tool_call_id: id,
          tool_name: stringValue(part.tool) || stringValue(part.name) || "unknown",
          tool_args: jsonValue(asPlainObject(state.input) || state.input || {}),
          timestamp,
        };
        if (!metricsAttached) {
          attachResourceSignals(callStep, fullModelId, tokensIn, tokensOut, costUsd);
          metricsAttached = true;
        }
        steps.push(callStep);

        if (state.output !== undefined) {
          steps.push({
            step_type: "tool_result",
            type: "tool_result",
            step_id: stableStepId("tr", source, messageIndex * 1000 + partIndex),
            step_order: steps.length + 1,
            title: `${stringValue(part.tool) || "tool"} result`,
            tool_call_id: id,
            tool_output: bodyFromContent(state.output).slice(0, 8000),
            timestamp,
          });
        }
        continue;
      }

      const text = bodyFromContent(part.text ?? part.content ?? part.summary ?? part).trim();
      if (!text) continue;
      const stepType = role === "assistant" || type === "reasoning" ? "thought" : "observation";
      const step: Record<string, Json> = {
        step_type: stepType,
        type: stepType,
        step_id: stableStepId(stepType, source, messageIndex * 1000 + partIndex),
        step_order: steps.length + 1,
        title: type === "reasoning" ? "assistant reasoning" : `${role} message`,
        body: text.slice(0, 8000),
        timestamp,
      };
      if (!metricsAttached) {
        attachResourceSignals(step, fullModelId, tokensIn, tokensOut, costUsd);
        metricsAttached = true;
      }
      steps.push(step);
    }

    if (!metricsAttached && (tokensIn || tokensOut)) {
      const step: Record<string, Json> = {
        step_type: "observation",
        type: "observation",
        step_id: stableStepId("usage", source, messageIndex),
        step_order: steps.length + 1,
        title: `${role} message token usage`,
        body: "(no exportable message parts)",
        timestamp,
      };
      attachResourceSignals(step, fullModelId, tokensIn, tokensOut, costUsd);
      steps.push(step);
    }
  }

  return steps;
}

function claudeCodeEventLike(rows: Record<string, any>[]): boolean {
  return rows.some((row) => ["assistant", "user", "system"].includes(stringValue(row.type) || "") && asPlainObject(row.message));
}

function extractClaudeContent(content: unknown): { text: string; reasoning: string; toolUses: Record<string, any>[]; toolResults: Record<string, any>[] } {
  const textParts: string[] = [];
  const reasoningParts: string[] = [];
  const toolUses: Record<string, any>[] = [];
  const toolResults: Record<string, any>[] = [];
  if (typeof content === "string") {
    textParts.push(content);
  } else if (Array.isArray(content)) {
    for (const raw of content) {
      const block = asPlainObject(raw);
      if (!block) {
        textParts.push(String(raw));
        continue;
      }
      const type = stringValue(block.type);
      if (type === "tool_use") toolUses.push(block);
      else if (type === "tool_result") toolResults.push(block);
      else if (["thinking", "reasoning", "analysis"].includes(type || "")) reasoningParts.push(bodyFromContent(block.text ?? block.thinking));
      else textParts.push(bodyFromContent(block.text ?? block.content ?? block));
    }
  } else if (content !== undefined && content !== null) {
    textParts.push(bodyFromContent(content));
  }
  return {
    text: textParts.map((part) => part.trim()).filter(Boolean).join("\n\n"),
    reasoning: reasoningParts.map((part) => part.trim()).filter(Boolean).join("\n\n"),
    toolUses,
    toolResults,
  };
}

function convertClaudeCodeEvents(rows: Record<string, any>[], source: string): Record<string, Json>[] {
  const steps: Record<string, Json>[] = [];
  const pendingTools = new Map<string, string>();
  const sorted = [...rows].sort((a, b) => String(a.timestamp || "").localeCompare(String(b.timestamp || "")));

  for (const [index, row] of sorted.entries()) {
    const eventType = stringValue(row.type) || "";
    const message = asPlainObject(row.message);
    if (!message) continue;
    const timestamp = timestampValue(row.timestamp) || utcNow();
    const role = stringValue(message.role) || eventType;
    const content = extractClaudeContent(message.content);
    const usage = asPlainObject(message.usage);
    const modelId = stringValue(message.model);
    const metrics = metricsSignals({
      prompt_tokens: numberValue(usage?.input_tokens) + numberValue(usage?.cache_read_input_tokens) + numberValue(usage?.cache_creation_input_tokens),
      completion_tokens: numberValue(usage?.output_tokens),
      cost_usd: usage?.cost_usd,
    }, modelId);
    let metricsAttached = false;

    if (eventType === "assistant") {
      const thoughtBody = [
        content.reasoning ? `[reasoning]\n${content.reasoning}` : "",
        content.text,
      ].filter(Boolean).join("\n\n").trim();
      if (thoughtBody || !content.toolUses.length) {
        const step: Record<string, Json> = {
          step_type: "thought",
          type: "thought",
          step_id: stableStepId("thought", source, index),
          step_order: steps.length + 1,
          body: (thoughtBody || "(assistant message)").slice(0, 8000),
          timestamp,
        };
        attachResourceSignals(step, modelId, metrics.tokensIn, metrics.tokensOut, metrics.costUsd);
        metricsAttached = true;
        steps.push(step);
      }
      for (const [toolIndex, tool] of content.toolUses.entries()) {
        const id = stringValue(tool.id) || stringValue(tool.tool_use_id) || stableStepId("tool", source, index * 1000 + toolIndex);
        pendingTools.set(id, stringValue(tool.name) || "unknown");
        const step: Record<string, Json> = {
          step_type: "tool_call",
          type: "tool_call",
          step_id: stableStepId("tc", source, index * 1000 + toolIndex),
          step_order: steps.length + 1,
          tool_call_id: id,
          tool_name: stringValue(tool.name) || "unknown",
          tool_args: jsonValue(asPlainObject(tool.input) || tool.input || {}),
          timestamp,
        };
        if (!metricsAttached) {
          attachResourceSignals(step, modelId, metrics.tokensIn, metrics.tokensOut, metrics.costUsd);
          metricsAttached = true;
        }
        steps.push(step);
      }
      continue;
    }

    for (const [resultIndex, result] of content.toolResults.entries()) {
      const id = stringValue(result.tool_use_id) || stringValue(result.id) || stableStepId("tool", source, index * 1000 + resultIndex);
      pendingTools.delete(id);
      const resultBody = bodyFromContent(result.content ?? row.toolUseResult ?? result).slice(0, 8000);
      steps.push({
        step_type: "tool_result",
        type: "tool_result",
        step_id: stableStepId("tr", source, index * 1000 + resultIndex),
        step_order: steps.length + 1,
        tool_call_id: id,
        tool_output: resultBody,
        timestamp,
      });
    }

    const text = content.text || (!content.toolResults.length ? bodyFromContent(message.content) : "");
    if (text.trim()) {
      steps.push({
        step_type: "observation",
        type: "observation",
        step_id: stableStepId("obs", source, index),
        step_order: steps.length + 1,
        title: role,
        body: text.slice(0, 8000),
        timestamp,
      });
    }
  }

  for (const [id, name] of pendingTools.entries()) {
    steps.push({
      step_type: "error",
      type: "error",
      step_id: stableStepId("err", source, steps.length + 1),
      step_order: steps.length + 1,
      tool_call_id: id,
      body: `Claude Code tool call ${name} (${id}) has no matching result in raw session log.`,
      timestamp: utcNow(),
    });
  }

  return steps;
}

function convertMessageRows(rows: Record<string, any>[], source: string): Record<string, Json>[] {
  const steps: Record<string, Json>[] = [];
  for (const [index, row] of rows.entries()) {
    const role = stringValue(row.role) || stringValue(row.source) || "message";
    const toolCalls = Array.isArray(row.tool_calls) ? row.tool_calls : [];
    const stepType = toolCalls.length > 0 ? "tool_call" : role === "tool" ? "tool_result" : ["assistant", "agent"].includes(role) ? "thought" : "observation";
    steps.push({
      step_type: stepType,
      type: stepType,
      step_id: stableStepId(stepType, source, index),
      step_order: index + 1,
      title: toolCalls.length > 0 ? "tool call" : role,
      body: contentTextFromRow(row).slice(0, 8000),
      timestamp: timestampValue(row.timestamp) || timestampValue(row.created_at) || utcNow(),
      cost_usd: 0,
    });
  }
  return steps;
}

function codexEventLike(rows: Record<string, any>[]): boolean {
  return rows.some((row) => row.type === "thread.started")
    && rows.some((row) => row.type === "item.started" || row.type === "item.completed" || row.type === "turn.completed");
}

function modernCodexEventLike(rows: Record<string, any>[]): boolean {
  return rows.some((row) => row.type === "response_item" && [
    "function_call", "function_call_output", "custom_tool_call", "custom_tool_call_output",
    "message", "agent_message", "reasoning",
  ].includes(stringValue(asPlainObject(row.payload)?.type) || ""));
}

function convertModernCodexEvents(rows: Record<string, any>[], source: string): Record<string, Json>[] {
  const steps: Record<string, Json>[] = [];
  for (const [index, row] of rows.entries()) {
    const payload = asPlainObject(row.payload);
    if (!payload) continue;
    const eventType = stringValue(payload.type) || "";
    const timestamp = timestampValue(row.timestamp) || utcNow();
    const callId = stringValue(payload.call_id) || stringValue(payload.id) || stableStepId("codex", source, index);
    if (["function_call", "custom_tool_call"].includes(eventType)) {
      const name = stringValue(payload.name) || "tool";
      const args = payload.arguments ?? payload.input ?? {};
      steps.push({ step_type: "tool_call", type: "tool_call", step_id: stableStepId("tc", source, index),
        step_order: steps.length + 1, tool_call_id: callId, tool_name: name,
        tool_args: typeof args === "string" ? args : jsonValue(args), timestamp });
    } else if (["function_call_output", "custom_tool_call_output"].includes(eventType)) {
      const output = payload.output ?? payload.result ?? payload.content ?? "";
      steps.push({ step_type: "tool_result", type: "tool_result", step_id: stableStepId("tr", source, index),
        step_order: steps.length + 1, tool_call_id: callId,
        tool_output: bodyFromContent(output).slice(0, 8000), timestamp });
    } else if (["message", "agent_message", "reasoning"].includes(eventType)) {
      const role = stringValue(payload.role) || (eventType === "agent_message" ? "assistant" : eventType);
      const body = stringValue(payload.message) || stringValue(payload.text) || bodyFromContent(payload.content ?? payload.summary ?? "");
      if (body.trim()) steps.push({ step_type: role === "assistant" ? "thought" : "observation", type: role === "assistant" ? "thought" : "observation",
        step_id: stableStepId("msg", source, index), step_order: steps.length + 1, title: role, body: body.slice(0, 8000), timestamp });
    }
  }
  return steps;
}

function convertCodexEvents(rows: Record<string, any>[], source: string): Record<string, Json>[] {
  const steps: Record<string, Json>[] = [];
  const pending = new Set<string>();
  for (const [index, row] of rows.entries()) {
    const eventType = stringValue(row.type) || "event";
    const item = asPlainObject(row.item) || {};
    const itemType = stringValue(item.type) || "";
    const id = stringValue(item.id) || stableStepId("codex", source, index);
    const timestamp = timestampValue(row.timestamp) || utcNow();
    if (eventType === "item.started" && itemType === "command_execution") {
      pending.add(id);
      steps.push({ step_type: "tool_call", type: "tool_call", step_id: stableStepId("tc", source, index),
        step_order: steps.length + 1, tool_call_id: id, tool_name: "shell",
        tool_args: { command: stringValue(item.command) || "" }, timestamp });
    } else if (eventType === "item.completed" && itemType === "command_execution") {
      pending.delete(id);
      steps.push({ step_type: "tool_result", type: "tool_result", step_id: stableStepId("tr", source, index),
        step_order: steps.length + 1, tool_call_id: id,
        tool_output: stringValue(item.aggregated_output) || "", timestamp });
    } else if (eventType === "item.completed" && ["agent_message", "reasoning"].includes(itemType)) {
      steps.push({ step_type: "thought", type: "thought", step_id: stableStepId("thought", source, index),
        step_order: steps.length + 1, body: (stringValue(item.text) || stringValue(item.message) || bodyFromContent(item)).slice(0, 8000), timestamp });
    } else if (eventType === "item.completed" && itemType === "error") {
      steps.push({ step_type: "error", type: "error", step_id: stableStepId("err", source, index),
        step_order: steps.length + 1, body: (stringValue(item.message) || bodyFromContent(item)).slice(0, 8000), timestamp });
    }
  }
  for (const id of pending) {
    steps.push({ step_type: "error", type: "error", step_id: stableStepId("err", source, steps.length),
      step_order: steps.length + 1, tool_call_id: id, body: `Codex command ${id} has no result at capture time.`, timestamp: utcNow() });
  }
  return steps;
}

function parseTraceSteps(text: string, source = "trace"): Record<string, Json>[] {
  try {
    const parsed = JSON.parse(text);
    if (Array.isArray(parsed)) {
      const rows = parsed.map((item) => asPlainObject(item)).filter((item): item is Record<string, any> => Boolean(item));
      const normalized = normalizeArmSteps(rows);
      if (normalized.length) return normalized;
    }
    const obj = asPlainObject(parsed);
    if (obj && openCodeExportLike(obj)) {
      const exported = convertOpenCodeExport(obj, source);
      if (exported.length) return exported;
    }
    if (obj && Array.isArray(obj.steps)) {
      const rows = obj.steps.map((item: unknown) => asPlainObject(item)).filter((item: unknown): item is Record<string, any> => Boolean(item));
      const normalized = normalizeArmSteps(rows);
      if (normalized.length) return normalized;
      const harborAtif = convertHarborAtifRows(rows, source, obj);
      if (harborAtif.length) return harborAtif;
      if (rows.some((row) => row.role || row.source || row.content || row.text || row.message)) return convertMessageRows(rows, source);
    }
  } catch {
    // Most native traces are JSONL, not a single JSON document.
  }

  const rows = objectRowsFromJsonl(text);
  if (!rows.length) return [];
  if (modernCodexEventLike(rows)) return convertModernCodexEvents(rows, source);
  const normalized = normalizeArmSteps(rows);
  if (normalized.length >= Math.max(1, Math.floor(rows.length * 0.8))) return normalized;
  if (opencodeEventLike(rows)) return convertOpenCodeEvents(rows, source);
  if (claudeCodeEventLike(rows)) return convertClaudeCodeEvents(rows, source);
  if (codexEventLike(rows)) return convertCodexEvents(rows, source);
  if (nativeTraceLike(rows)) return convertNativeTrajectoryRows(rows, source);
  if (rows.some((row) => row.role || row.source || row.content)) return convertMessageRows(rows, source);
  return [];
}

function validateTraceSteps(steps: Record<string, Json>[]): Record<string, Json> {
  const failures: string[] = [];
  const warnings: string[] = [];
  const byType: Record<string, number> = {};
  const calls = new Set<string>();
  const results = new Set<string>();
  const timestamps: string[] = [];
  const ids: string[] = [];
  let totalCost = 0;
  let totalTokens = 0;
  let longThoughts = 0;
  let badTypes = 0;

  for (const step of steps) {
    const stepType = String(step.step_type || step.type || "");
    byType[stepType] = (byType[stepType] || 0) + 1;
    if (!ARM_STEP_TYPES.has(stepType)) badTypes += 1;
    if (stepType === "tool_call" && step.tool_call_id) calls.add(String(step.tool_call_id));
    if (stepType === "tool_result" && step.tool_call_id) results.add(String(step.tool_call_id));
    if (step.timestamp) timestamps.push(String(step.timestamp));
    if (step.step_id) ids.push(String(step.step_id));
    const cost = numberValue(step.cost_usd);
    const tokensIn = numberValue(step.tokens_in);
    const tokensOut = numberValue(step.tokens_out);
    totalCost += cost;
    totalTokens += tokensIn + tokensOut;
    if (stepType === "thought" && String(step.body || "").length >= 80) longThoughts += 1;
  }

  const unpaired = [...calls].filter((id) => !results.has(id));
  const duplicateIds = ids.length - new Set(ids).size;
  const monotonic = timestamps.every((ts, index) => index === 0 || timestamps[index - 1] <= ts);
  if (!steps.length) failures.push("no_steps: trace is empty");
  if (badTypes) failures.push(`typed_step_type: ${badTypes} steps use invalid step_type`);
  if (unpaired.length) failures.push(`tool_call_pairing: ${unpaired.length} tool_calls lack matching tool_result`);
  if (totalCost < 0.01) failures.push(`cost_floor: total_cost_usd=${totalCost.toFixed(6)} < 0.01`);
  if (longThoughts < 3) failures.push(`thought_chain_thin: ${longThoughts} thoughts >=80 chars (need 3)`);
  if (!steps.some((step) => numberValue(step.cost_usd) > 0 || numberValue(step.tokens_in) > 0 || numberValue(step.tokens_out) > 0)) {
    failures.push("zero_resource_signals: every step has cost=0 and tokens=0");
  }
  if (!monotonic) failures.push("timestamp_monotonic: step timestamps not non-decreasing");
  if (duplicateIds) failures.push(`step_id_unique: ${duplicateIds} duplicate step_id values`);
  warnings.push("timestamp_window/artifact_existence/stdout_anchor need bundle context and are not checked here.");
  return {
    total_steps: steps.length,
    by_type: byType,
    paired_tool_calls: `${[...calls].filter((id) => results.has(id)).length}/${calls.size}`,
    total_cost_usd: Number(totalCost.toFixed(6)),
    total_tokens: totalTokens,
    failures,
    warnings,
    valid: failures.length === 0,
  };
}

async function readJsonFile<T = Record<string, Json>>(file: string): Promise<T> {
  return JSON.parse(await fs.readFile(file, "utf8")) as T;
}

async function writeJsonFile(file: string, data: Json): Promise<void> {
  await fs.mkdir(path.dirname(file), { recursive: true });
  await fs.writeFile(file, `${JSON.stringify(data, null, 2)}\n`);
}

function compareVersions(a: string, b: string): number {
  const parse = (value: string) => value.replace(/^v/i, "").split(".").map((part) => Number.parseInt(part, 10) || 0);
  const left = parse(a); const right = parse(b);
  for (let i = 0; i < Math.max(left.length, right.length); i += 1) {
    if ((left[i] || 0) !== (right[i] || 0)) return (left[i] || 0) > (right[i] || 0) ? 1 : -1;
  }
  return 0;
}

async function checkForUpdate(force = false): Promise<{ current: string; latest?: string; checked: boolean; error?: string }> {
  const current = VERSION;
  if (process.env.PLAYGROUND_NO_UPDATE_CHECK === "1" && !force) return { current, checked: false };
  let cached: any = {};
  if (!force && await exists(UPDATE_CACHE_PATH)) {
    try { cached = await readJsonFile(UPDATE_CACHE_PATH); } catch { cached = {}; }
  }
  if (!force && cached.checked_at && Date.now() - Number(cached.checked_at) < UPDATE_CACHE_TTL_MS) {
    return { current, latest: typeof cached.latest === "string" ? cached.latest : undefined, checked: false };
  }
  const url = process.env.PLAYGROUND_UPDATE_URL || DEFAULT_UPDATE_URL;
  try {
    const response = await fetch(url, { headers: { Accept: "application/json" }, signal: AbortSignal.timeout(2500) });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json() as any;
    const latest = typeof payload.latest === "string" ? payload.latest : undefined;
    await writeJsonFile(UPDATE_CACHE_PATH, { checked_at: Date.now(), latest: latest || null });
    return { current, latest, checked: true };
  } catch (error) {
    return { current, checked: true, error: error instanceof Error ? error.message : String(error) };
  }
}

async function printUpdateStatus(force = true): Promise<void> {
  const result = await checkForUpdate(force);
  console.log(JSON.stringify({ ...result, update_available: Boolean(result.latest && compareVersions(result.latest, result.current) > 0) }, null, 2));
}

async function maybePrintUpdateNotice(): Promise<void> {
  const result = await checkForUpdate(false);
  if (result.latest && compareVersions(result.latest, result.current) > 0) {
    const install = process.env.PLAYGROUND_UPDATE_INSTALL || "curl -fsSL https://play.bohrium.com/install.sh | bash";
    console.error(
      `Playground CLI ${result.current} is outdated; latest is ${result.latest}.\n`
      + "Please update as soon as possible; otherwise, your score may be affected.\n"
      + "请尽快更新，否则会影响评分。\n"
      + `Upgrade with / 更新命令：\n  ${install}`,
    );
  }
}

async function exists(file: string): Promise<boolean> {
  try {
    await fs.access(file);
    return true;
  } catch {
    return false;
  }
}

async function loadConfig(opts: Record<string, OptValue>): Promise<Record<string, Json>> {
  const configPath = opt(opts, "config") || DEFAULT_CONFIG_PATH;
  if (!(await exists(configPath))) return {};
  return readJsonFile(configPath);
}

async function saveConfig(configPath: string, data: Record<string, Json>): Promise<void> {
  await writeJsonFile(configPath, data);
}

function isObsoletePlayApiBase(value: unknown): boolean {
  if (typeof value !== "string") return false;
  try {
    const url = new URL(value);
    return url.hostname === "vxzj1507371.bohrium.tech" && url.port === "50001";
  } catch {
    return false;
  }
}

async function migrateDefaultConfig(): Promise<void> {
  if (!(await exists(DEFAULT_CONFIG_PATH))) return;
  const config = await readJsonFile<Record<string, Json>>(DEFAULT_CONFIG_PATH);
  if (!isObsoletePlayApiBase(config.apiBase)) return;
  config.apiBase = DEFAULT_PLAY_API;
  config.migratedAt = utcNow();
  config.migratedFrom = "http://vxzj1507371.bohrium.tech:50001/api";
  await saveConfig(DEFAULT_CONFIG_PATH, config);
}

async function runProcess(
  file: string,
  args: string[],
  options: { cwd?: string; env?: NodeJS.ProcessEnv } = {},
): Promise<{ stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const child = spawn(file, args, {
      cwd: options.cwd,
      env: options.env ? { ...process.env, ...options.env } : process.env,
      stdio: ["ignore", "pipe", "pipe"],
    });
    const stdout: Buffer[] = [];
    const stderr: Buffer[] = [];
    child.stdout.on("data", (chunk: Buffer | string) => stdout.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)));
    child.stderr.on("data", (chunk: Buffer | string) => stderr.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk)));
    child.on("error", (error: NodeJS.ErrnoException) => {
      if (error.code === "ENOENT") {
        reject(new CliError(`missing executable '${file}'. Install the latest Bohrium CLI, ensure 'bohr' is on PATH, then run 'bohr update'`));
        return;
      }
      reject(error);
    });
    child.on("close", (code) => {
      const out = Buffer.concat(stdout).toString("utf8");
      const err = Buffer.concat(stderr).toString("utf8");
      if (code === 0) {
        resolve({ stdout: out, stderr: err });
        return;
      }
      reject(new CliError(`${file} ${args.join(" ")} failed with exit ${code}\n${err || out}`.trim()));
    });
  });
}

interface WenyonCommand {
  file: string;
  prefix: string[];
}

function wenyonCommand(opts: Record<string, OptValue>): WenyonCommand {
  const legacyBin = opt(opts, "wenyon-bin") || process.env.PLAYGROUND_WENYON_BIN;
  if (legacyBin) return { file: legacyBin, prefix: [] };
  return {
    file: opt(opts, "bohr-bin") || process.env.PLAYGROUND_BOHR_BIN || "bohr",
    prefix: ["wenyon"],
  };
}

function wenyonCommandArgs(opts: Record<string, OptValue>, args: string[] = []): string[] {
  return [...wenyonCommand(opts).prefix, ...args];
}

function wenyonCommandDisplay(opts: Record<string, OptValue>, args: string[] = []): string {
  const command = wenyonCommand(opts);
  return [command.file, ...command.prefix, ...args].join(" ");
}

function wenyonError(error: unknown): CliError {
  const message = error instanceof Error ? error.message : String(error);
  if (/401|403|unauthenticated|not authenticated|auth(?:entication)? required|login required/i.test(message)) {
    return new CliError([
      "Wenyon dataset access is not authenticated.",
      "Run 'bohr auth login' locally or 'bohr auth login --device' on a remote/headless machine.",
      "",
      message,
    ].join("\n"));
  }
  if (error instanceof CliError) return error;
  return new CliError(message);
}

async function runWenyon(opts: Record<string, OptValue>, args: string[]): Promise<{ stdout: string; stderr: string }> {
  try {
    const command = wenyonCommand(opts);
    return await runProcess(command.file, [...command.prefix, ...args]);
  } catch (error) {
    throw wenyonError(error);
  }
}

async function installWenyon(opts: Record<string, OptValue>): Promise<void> {
  if (!opt(opts, "wenyon-bin") && !process.env.PLAYGROUND_WENYON_BIN) {
    const command = wenyonCommand(opts);
    await runProcess(command.file, ["update"]);
    return;
  }
  const installer = opt(opts, "wenyon-installer") || DEFAULT_WENYON_INSTALLER;
  await runProcess("bash", ["-lc", `curl -fsSL ${JSON.stringify(installer)} | bash`]);
}

function parseJsonOutput<T = unknown>(stdout: string, command: string): T {
  try {
    return JSON.parse(stdout) as T;
  } catch {
    throw new CliError(`${command} did not return JSON:\n${stdout.slice(0, 2000)}`);
  }
}

function targetName(opts: Record<string, OptValue>, config: Record<string, Json>): string {
  return opt(opts, "target") || String(config.defaultTarget || process.env.PLAYGROUND_TARGET || "play");
}

function normalizePlayApiBase(base: string): string {
  const trimmed = base.replace(/\/+$/, "");
  try {
    const url = new URL(trimmed || base);
    if (url.hostname === "vxzj1507371.bohrium.tech" && url.port === "50001") {
      return "https://play.bohrium.com/api";
    }
    if (url.hostname === "play.bohrium.com" && (url.pathname === "" || url.pathname === "/")) {
      url.pathname = "/api";
      return url.toString().replace(/\/+$/, "");
    }
  } catch {
    // Keep non-URL custom API bases untouched; fetch will report invalid values.
  }
  return trimmed;
}

function apiBase(opts: Record<string, OptValue>, config: Record<string, Json>): string {
  const target = targetName(opts, config);
  if (target === "worker") {
    if (process.env.PLAYGROUND_ALLOW_WORKER_API_OVERRIDE === "1" && process.env.PLAYGROUND_WORKER_API_BASE) {
      return normalizePlayApiBase(process.env.PLAYGROUND_WORKER_API_BASE);
    }
    return DEFAULT_WORKER_API;
  }
  if (opt(opts, "api-base")) return normalizePlayApiBase(required(opts, "api-base"));
  return normalizePlayApiBase(String(config.apiBase || process.env.PLAYGROUND_API_BASE || DEFAULT_PLAY_API));
}

function publicBaseFromApi(base: string): string {
  return base.replace(/\/api\/?$/, "");
}

function workerToken(opts: Record<string, OptValue>, config: Record<string, Json>): string | undefined {
  const explicitEnv = opt(opts, "worker-token-env");
  if (explicitEnv) return process.env[explicitEnv];
  const configured = config.workerTokenEnv;
  if (typeof configured === "string" && process.env[configured]) return process.env[configured];
  return process.env.PLAYGROUND_WORKER_TOKEN;
}

function bearerToken(opts: Record<string, OptValue>, config: Record<string, Json>): string | undefined {
  const target = targetName(opts, config);
  if (target === "worker") return workerToken(opts, config);
  const explicitEnv = opt(opts, "token-env");
  if (explicitEnv) return process.env[explicitEnv];
  const configured = config.tokenEnv;
  if (typeof configured === "string" && process.env[configured]) return process.env[configured];
  return process.env.PLAYGROUND_TOKEN;
}

async function requestJson<T = Record<string, Json>>(
  url: string,
  init: RequestInit = {},
  token?: string,
): Promise<T> {
  const headers = new Headers(init.headers || {});
  headers.set("Accept", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(url, { ...init, headers });
  const text = await response.text();
  if (!response.ok) {
    throw new CliError(`HTTP ${response.status} ${response.statusText}: ${text}`);
  }
  if (!text.trim()) return {} as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    return { raw: text } as T;
  }
}

function isHttpStatus(error: unknown, status: number): boolean {
  return error instanceof CliError && error.message.startsWith(`HTTP ${status} `);
}

async function resolveApiToken(
  base: string,
  sessionToken: string,
  name: string,
): Promise<{ token: string; prefix: string | null; credential_type: "api" | "session" }> {
  let last401: CliError | undefined;
  for (let attempt = 1; attempt <= 4; attempt += 1) {
    try {
      const created = await requestJson<Record<string, any>>(`${base}/auth/tokens`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      }, sessionToken);
      const token = typeof created.token === "string" ? created.token : "";
      if (!token) throw new CliError("Playground did not return an API token");
      return {
        token,
        prefix: typeof created.prefix === "string" ? created.prefix : token.slice(0, 12),
        credential_type: "api",
      };
    } catch (error) {
      if (!(error instanceof CliError) || !error.message.startsWith("HTTP 401 ")) throw error;
      last401 = error;
      if (attempt < 4) await sleep(500 * attempt);
    }
  }

  try {
    const created = await requestJson<Record<string, any>>(`${base}/auth/tokens`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }, sessionToken);
    const token = typeof created.token === "string" ? created.token : "";
    if (!token) throw new CliError("Playground did not return an API token");
    return {
      token,
      prefix: typeof created.prefix === "string" ? created.prefix : token.slice(0, 12),
      credential_type: "api",
    };
  } catch (error) {
    // Some Playground deployments return a valid login/register session token
    // but reject API-token creation. Keep auth usable instead of discarding the
    // valid session; future login/register calls will retry API-token creation.
    if (!(error instanceof CliError) || !error.message.startsWith("HTTP 401 ")) throw error;
    void last401;
    return {
      token: sessionToken,
      prefix: sessionToken.slice(0, 12),
      credential_type: "session",
    };
  }
}

async function cmdAuthLogin(opts: Record<string, OptValue>): Promise<void> {
  const config = await loadConfig(opts);
  const base = apiBase(opts, config);
  const email = required(opts, "email");
  const passwordEnv = opt(opts, "password-env") || "PLAYGROUND_PASSWORD";
  const password = process.env[passwordEnv];
  if (!password) {
    throw new CliError(`set ${passwordEnv} to your Playground password; passwords are not accepted as CLI arguments`);
  }
  const login = await requestJson<Record<string, any>>(`${base}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (typeof login.token !== "string") throw new CliError("Playground login did not return a session token");
  const created = await resolveApiToken(base, login.token, opt(opts, "token-name") || `CLI ${os.hostname()}`);
  await savePlaygroundCredentials(created.token, { email, password });
  console.log(JSON.stringify({
    status: "authenticated",
    email,
    api_base: base,
    credentials: DEFAULT_CREDENTIALS_PATH,
    token_prefix: created.prefix || null,
  }, null, 2));
}

async function cmdAuthRegister(opts: Record<string, OptValue>): Promise<void> {
  const config = await loadConfig(opts);
  const base = apiBase(opts, config);
  const name = required(opts, "name");
  const email = required(opts, "email");
  const passwordEnv = opt(opts, "password-env") || "PLAYGROUND_PASSWORD";
  const suppliedPassword = LOADED_SAVED_CREDENTIALS.has(passwordEnv) ? undefined : process.env[passwordEnv];
  const password = suppliedPassword || generateRegistrationPassword();
  const registered = await requestJson<Record<string, any>>(`${base}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, password, affiliation: opt(opts, "affiliation") || "" }),
  });
  if (typeof registered.token !== "string") throw new CliError("Playground registration did not return a session token");
  const created = await resolveApiToken(base, registered.token, opt(opts, "token-name") || `CLI ${os.hostname()}`);
  await savePlaygroundCredentials(created.token, { email, password });
  console.log(JSON.stringify({
    status: "registered",
    email,
    api_base: base,
    credentials: DEFAULT_CREDENTIALS_PATH,
    token_prefix: created.prefix || null,
    password_generated: !suppliedPassword,
  }, null, 2));
}

function normalizeOperatorId(value: string): string {
  const operatorId = value.trim().replace(/^@/, "");
  if (!operatorId) throw new CliError("--operator must name a Playground user, for example @osgood");
  return operatorId;
}

async function resolveHumanOperator(base: string, value: string): Promise<{ id: string; name: string }> {
  const operatorId = normalizeOperatorId(value);
  const payload = await requestJson<unknown>(`${base}/users`);
  const root = asPlainObject(payload);
  const users = asPlainObject(root?.users) || root;
  const operator = asPlainObject(users?.[operatorId]);
  if (!operator) {
    throw new CliError(`Playground user @${operatorId} was not found; --operator requires an exact user id`);
  }
  const userType = stringValue(operator.userType) || stringValue(operator.user_type) || "human";
  if (userType !== "human") {
    throw new CliError(`Playground user @${operatorId} is ${userType}, not a human operator`);
  }
  return { id: operatorId, name: stringValue(operator.name) || operatorId };
}

function defaultAgentCredentialsPath(name: string, email: string): string {
  const stem = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64) || `agent-${createHash("sha256").update(email).digest("hex").slice(0, 10)}`;
  return path.join(os.homedir(), ".config", "playground", "agents", `${stem}.env`);
}

async function cmdAgentClaim(opts: Record<string, OptValue>): Promise<void> {
  const config = await loadConfig(opts);
  const base = apiBase({ ...opts, target: "play" }, config);
  const name = required(opts, "name").trim();
  const email = required(opts, "email").trim();
  const framework = (opt(opts, "framework") || "Custom").trim();
  if (!name) throw new CliError("--name cannot be empty");
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) throw new CliError("--email must be a valid email address");
  if (!framework) throw new CliError("--framework cannot be empty");
  if (framework.length > 100) throw new CliError("--framework must be at most 100 characters");

  const operator = await resolveHumanOperator(base, required(opts, "operator"));
  const credentialsPath = path.resolve(
    opt(opts, "credentials-out") || defaultAgentCredentialsPath(name, email),
  );
  const credentialsExist = await exists(credentialsPath);
  const personaId = opt(opts, "persona-id");
  const passwordEnv = opt(opts, "password-env") || "PLAYGROUND_AGENT_PASSWORD";
  const suppliedPassword = LOADED_SAVED_CREDENTIALS.has(passwordEnv) ? undefined : process.env[passwordEnv];
  const password = suppliedPassword || generateRegistrationPassword();
  const requestBody: Record<string, string> = {
    name,
    email,
    password,
    user_type: "agent",
    claimed_operator_id: operator.id,
    framework,
  };
  if (personaId) requestBody.persona_id = personaId;

  async function reportExistingAgentClaimState(
    token: string,
    credentialType: string,
    tokenPrefix: string | null,
  ): Promise<void> {
    const user = await requestJson<Record<string, any>>(`${base}/auth/me`, {}, token);
    const agentId = stringValue(user?.id);
    const returnedUserType = stringValue(user?.userType) || stringValue(user?.user_type);
    const returnedEmail = stringValue(user?.email);
    if (returnedUserType !== "agent") {
      throw new CliError(`credentials at ${credentialsPath} authenticate ${agentId || "a user"} as ${returnedUserType || "unknown"}, not an agent`);
    }
    if (returnedEmail && returnedEmail.toLowerCase() !== email.toLowerCase()) {
      throw new CliError(`credentials at ${credentialsPath} are for ${returnedEmail}, not ${email}; pass --force to replace that file`);
    }
    const returnedOperatorId = stringValue(user?.operatorId) || stringValue(user?.operator_id);
    const operatorConfirmed = user?.operatorConfirmed === true || user?.operator_confirmed === true;
    if (returnedOperatorId !== operator.id) {
      throw new CliError([
        `Existing agent ${agentId || email} is not pending for @${operator.id}.`,
        returnedOperatorId ? `Current operator is @${returnedOperatorId}.` : "Current operator is empty.",
        "This Playground version has no CLI-callable API that creates a new pending claim for an existing agent account.",
        "Use a fresh agent email to create a new pending claim, or ask a platform maintainer/admin to create the pending claim server-side.",
      ].join(" "));
    }
    console.log(JSON.stringify({
      schema_version: "playground-agent-claim/v1",
      status: operatorConfirmed ? "claim_confirmed" : "claim_pending",
      api_base: base,
      agent_id: agentId || null,
      agent_name: stringValue(user?.name) || name,
      framework: stringValue(user?.agentFramework) || stringValue(user?.agent_framework) || framework,
      claimed_operator_id: operator.id,
      operator_name: operator.name,
      operator_confirmed: operatorConfirmed,
      credentials: credentialsPath,
      credentials_env: "PLAYGROUND_CREDENTIALS_PATH",
      token_prefix: tokenPrefix,
      credential_type: credentialType,
      reused_existing_credentials: credentialsExist,
      existing_agent_only: true,
      confirm_url: `${publicBaseFromApi(base)}/#profile`,
      next_step: operatorConfirmed
        ? "Use PLAYGROUND_CREDENTIALS_PATH with this credentials file for agent submissions."
        : `Ask @${operator.id} to open Agents & API > Pending Agent Claims and confirm this agent.`,
    }, null, 2));
  }

  if (flag(opts, "dry-run")) {
    const { password: _password, ...safeRequest } = requestBody;
    console.log(JSON.stringify({
      schema_version: "playground-agent-claim/v1",
      status: "dry_run",
      api_base: base,
      request: safeRequest,
      operator,
      credentials: credentialsPath,
      credentials_exist: credentialsExist,
      password_generated: !suppliedPassword,
      confirm_url: `${publicBaseFromApi(base)}/#profile`,
    }, null, 2));
    return;
  }

  if (credentialsExist && !flag(opts, "force")) {
    const existingEnv = await readCredentialsFileEnv(credentialsPath);
    const existingToken = stringValue(existingEnv.PLAYGROUND_TOKEN);
    if (!existingToken) {
      throw new CliError(`agent credentials already exist at ${credentialsPath} but do not contain PLAYGROUND_TOKEN; pass --force to replace that file`);
    }
    const existingEmail = stringValue(existingEnv.PLAYGROUND_EMAIL);
    if (existingEmail && existingEmail.toLowerCase() !== email.toLowerCase()) {
      throw new CliError(`agent credentials at ${credentialsPath} are for ${existingEmail}, not ${email}; pass --force to replace that file`);
    }
    await reportExistingAgentClaimState(
      existingToken,
      existingToken.startsWith("asp_") ? "api" : "session",
      existingToken.slice(0, 12),
    );
    return;
  }

  let registered: Record<string, any>;
  try {
    registered = await requestJson<Record<string, any>>(`${base}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestBody),
    });
  } catch (error) {
    if (!isHttpStatus(error, 409)) throw error;
    if (!suppliedPassword) {
      throw new CliError([
        `An agent account already exists for ${email}.`,
        `Set ${passwordEnv} to the existing password to inspect its current claim state, or use a fresh email to create a new pending claim.`,
        "This Playground version cannot create a new pending claim for an existing agent account through CLI-only API calls.",
      ].join(" "));
    }
    let sessionToken = "";
    try {
      const login = await requestJson<Record<string, any>>(`${base}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      sessionToken = stringValue(login.token) || "";
    } catch (loginError) {
      throw new CliError([
        `An agent account already exists for ${email}, but login with ${passwordEnv} failed.`,
        loginError instanceof Error ? loginError.message : String(loginError),
      ].join(" "));
    }
    if (!sessionToken) throw new CliError("Playground login did not return a session token for the existing agent");
    await saveCredentialsFile(credentialsPath, sessionToken, { email, password });
    const created = await resolveApiToken(base, sessionToken, opt(opts, "token-name") || `Agent CLI ${os.hostname()}`);
    await saveCredentialsFile(credentialsPath, created.token, { email, password });
    await reportExistingAgentClaimState(created.token, created.credential_type, created.prefix || null);
    return;
  }
  const user = asPlainObject(registered.user);
  const agentId = stringValue(user?.id);
  let sessionToken = stringValue(registered.token);
  if (!sessionToken) {
    const login = await requestJson<Record<string, any>>(`${base}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    sessionToken = stringValue(login.token);
  }
  if (!sessionToken) throw new CliError("Playground created the agent but did not return a recoverable session token");

  // Preserve the first usable credential before requesting a long-lived API token.
  await saveCredentialsFile(credentialsPath, sessionToken, { email, password });
  let created: Awaited<ReturnType<typeof resolveApiToken>>;
  try {
    created = await resolveApiToken(base, sessionToken, opt(opts, "token-name") || `Agent CLI ${os.hostname()}`);
    await saveCredentialsFile(credentialsPath, created.token, { email, password });
  } catch (error) {
    throw new CliError([
      `Agent ${agentId || name} was registered and session credentials were saved to ${credentialsPath},`,
      `but API-token creation failed: ${error instanceof Error ? error.message : String(error)}`,
    ].join(" "));
  }

  const returnedUserType = stringValue(user?.userType) || stringValue(user?.user_type);
  const returnedOperatorId = stringValue(user?.operatorId) || stringValue(user?.operator_id);
  if (returnedUserType !== "agent" || returnedOperatorId !== operator.id) {
    throw new CliError([
      `Agent ${agentId || name} was registered, but Playground did not attach the requested operator @${operator.id}.`,
      `Credentials were preserved at ${credentialsPath}; do not treat this identity as claimed.`,
    ].join(" "));
  }

  const operatorConfirmed = user?.operatorConfirmed === true || user?.operator_confirmed === true;
  console.log(JSON.stringify({
    schema_version: "playground-agent-claim/v1",
    status: operatorConfirmed ? "claim_confirmed" : "claim_pending",
    api_base: base,
    agent_id: agentId || null,
    agent_name: stringValue(user?.name) || name,
    framework: stringValue(user?.agentFramework) || stringValue(user?.agent_framework) || framework,
    claimed_operator_id: operator.id,
    operator_name: operator.name,
    operator_confirmed: operatorConfirmed,
    credentials: credentialsPath,
    credentials_env: "PLAYGROUND_CREDENTIALS_PATH",
    token_prefix: created.prefix || null,
    credential_type: created.credential_type,
    password_generated: !suppliedPassword,
    confirm_url: `${publicBaseFromApi(base)}/#profile`,
    next_step: operatorConfirmed
      ? "Use PLAYGROUND_CREDENTIALS_PATH with this credentials file for agent submissions."
      : `Ask @${operator.id} to open Agents & API > Pending Agent Claims and confirm this agent.`,
  }, null, 2));
}

async function cmdAuthStatus(opts: Record<string, OptValue>): Promise<void> {
  const config = await loadConfig(opts);
  const base = apiBase(opts, config);
  const token = bearerToken(opts, config);
  if (!token) {
    console.log(JSON.stringify({ authenticated: false, api_base: base, login_url: publicBaseFromApi(base) }, null, 2));
    return;
  }
  await requestJson(`${base}/challenges?limit=1`, {}, token);
  console.log(JSON.stringify({ authenticated: true, api_base: base, credentials: DEFAULT_CREDENTIALS_PATH }, null, 2));
}

function challengeRowsFromPayload(payload: unknown): Record<string, any>[] {
  const rowsFromArray = (items: unknown[]): Record<string, any>[] =>
    items.map(asPlainObject).filter((row): row is Record<string, any> => Boolean(row && row.id));

  if (Array.isArray(payload)) return rowsFromArray(payload);

  const obj = asPlainObject(payload);
  if (!obj) return [];

  for (const key of ["challenges", "tasks", "items", "data"]) {
    const value = obj[key];
    if (Array.isArray(value)) return rowsFromArray(value);
    const dict = asPlainObject(value);
    if (dict) {
      return Object.entries(dict)
        .map(([id, row]) => ({ ...(asPlainObject(row) || {}), id: stringValue((row as any)?.id) || id }))
        .filter((row) => Boolean(row.id));
    }
  }

  return Object.entries(obj)
    .map(([id, row]) => ({ ...(asPlainObject(row) || {}), id: stringValue((row as any)?.id) || id }))
    .filter((row) => Boolean(row.id));
}

function tagsFromRow(row: Record<string, any>): string[] {
  const rawTags = Array.isArray(row.tags) ? row.tags : [];
  const tags = rawTags
    .map((tag) => String(tag).trim())
    .filter(Boolean);
  const origin = stringValue(row.origin);
  const journal = stringValue(row.journal);
  if (origin) tags.push(origin);
  if (journal && journal.toLowerCase().includes("harbor")) tags.push("harbor");
  if (String(row.id || "").toLowerCase().startsWith("harbor-")) tags.push("harbor");
  return Array.from(new Set(tags));
}

function matchesTagFilter(row: Record<string, any>, wantedTags: string[]): boolean {
  if (wantedTags.length === 0) return true;
  const tags = tagsFromRow(row).map((tag) => tag.toLowerCase());
  return wantedTags.every((wanted) => {
    const needle = wanted.toLowerCase();
    return tags.some((tag) => tag === needle || tag.includes(needle));
  });
}

interface ChallengeRowsResult {
  rows: Record<string, any>[];
  total: number;
}

async function fetchChallengeRows(base: string, token?: string, maxRows = Number.POSITIVE_INFINITY): Promise<ChallengeRowsResult> {
  const requestedRows = Number.isFinite(maxRows) ? Math.max(1, Math.floor(maxRows)) : Number.POSITIVE_INFINITY;
  const apiUrl = `${base}/challenges`;
  const errors: string[] = [];

  try {
    const rows: Record<string, any>[] = [];
    const seenIds = new Set<string>();
    const perPage = Number.isFinite(requestedRows) ? Math.min(200, requestedRows) : 200;
    let page = 1;
    let reportedTotal = 0;
    while (rows.length < requestedRows) {
      const payload = await requestJson<unknown>(`${apiUrl}?page=${page}&per_page=${perPage}`, {}, token);
      const pageRows = challengeRowsFromPayload(payload);
      if (pageRows.length === 0) {
        if (page === 1) throw new CliError("empty challenge list");
        break;
      }

      let added = 0;
      for (const row of pageRows) {
        const id = String(row.id);
        if (seenIds.has(id)) continue;
        seenIds.add(id);
        rows.push(row);
        added += 1;
        if (rows.length >= requestedRows) break;
      }

      const meta = asPlainObject(payload);
      const total = numberValue(meta?.total);
      if (total > 0) reportedTotal = total;
      const currentPage = numberValue(meta?.page) || page;
      const pages = numberValue(meta?.pages);
      const hasMore = typeof meta?.has_more === "boolean"
        ? meta.has_more
        : pages > 0
          ? currentPage < pages
          : false;
      if (!hasMore || (reportedTotal > 0 && rows.length >= reportedTotal)) break;
      if (added === 0) throw new CliError(`challenge page ${page} repeated without new rows`);
      page = currentPage + 1;
    }
    if (rows.length > 0) return { rows, total: reportedTotal || rows.length };
  } catch (error) {
    errors.push(`${apiUrl}: ${error instanceof Error ? error.message : String(error)}`);
  }

  const fallbackUrl = `${publicBaseFromApi(base)}/data/challenges.json`;
  try {
    const payload = await requestJson<unknown>(fallbackUrl, {}, token);
    const allRows = challengeRowsFromPayload(payload);
    if (allRows.length > 0) {
      return {
        rows: Number.isFinite(requestedRows) ? allRows.slice(0, requestedRows) : allRows,
        total: allRows.length,
      };
    }
    errors.push(`${fallbackUrl}: empty challenge list`);
  } catch (error) {
    errors.push(`${fallbackUrl}: ${error instanceof Error ? error.message : String(error)}`);
  }
  throw new CliError(`Could not load challenge list.\n${errors.join("\n")}`);
}

async function resolveChallengeId(base: string, token: string | undefined, input: string): Promise<string> {
  if (!/^\d+$/.test(input)) return input;
  const index = Number(input);
  if (!Number.isSafeInteger(index) || index < 1) return input;
  const { rows } = await fetchChallengeRows(base, token, index);
  const row = rows[index - 1];
  if (!row || !stringValue(row.id)) {
    throw new CliError(`No challenge at numeric index ${input}. Run 'playground task list --limit 20' to see available challenge ids.`);
  }
  return String(row.id);
}

function encodeMultipart(
  fields: Record<string, string | undefined>,
  files: MultipartFile[],
): { body: Buffer; contentType: string } {
  const boundary = `----playground-cli-ts-${Math.random().toString(16).slice(2)}`;
  const chunks: Buffer[] = [];
  const line = (value: string) => chunks.push(Buffer.from(`${value}\r\n`, "utf8"));
  for (const [name, value] of Object.entries(fields)) {
    if (value === undefined) continue;
    line(`--${boundary}`);
    line(`Content-Disposition: form-data; name="${name}"`);
    line("");
    line(value);
  }
  for (const file of files) {
    line(`--${boundary}`);
    line(`Content-Disposition: form-data; name="${file.name}"; filename="${file.filename}"`);
    line(`Content-Type: ${file.contentType}`);
    line("");
    chunks.push(file.data);
    chunks.push(Buffer.from("\r\n", "utf8"));
  }
  line(`--${boundary}--`);
  return { body: Buffer.concat(chunks), contentType: `multipart/form-data; boundary=${boundary}` };
}

async function postMultipartJson<T = Record<string, Json>>(
  url: string,
  fields: Record<string, string | undefined>,
  files: MultipartFile[],
  token?: string,
): Promise<T> {
  const { body, contentType } = encodeMultipart(fields, files);
  return requestJson<T>(
    url,
    {
      method: "POST",
      headers: { "Content-Type": contentType },
      body: body as unknown as BodyInit,
    },
    token,
  );
}

async function sha256File(file: string): Promise<string> {
  const hash = createHash("sha256");
  await new Promise<void>((resolve, reject) => {
    const stream = createReadStream(file);
    stream.on("data", (chunk) => hash.update(chunk));
    stream.on("error", reject);
    stream.on("end", resolve);
  });
  return hash.digest("hex");
}

async function listFiles(root: string): Promise<string[]> {
  const out: string[] = [];
  async function walk(current: string): Promise<void> {
    const stat = await fs.stat(current);
    if (stat.isFile()) {
      out.push(current);
      return;
    }
    if (!stat.isDirectory()) return;
    const entries = await fs.readdir(current);
    for (const entry of entries) {
      if ([".git", "node_modules", "__pycache__", ".venv", "venv"].includes(entry)) continue;
      await walk(path.join(current, entry));
    }
  }
  await walk(root);
  return out.sort();
}

async function copyPath(src: string, dest: string): Promise<void> {
  const stat = await fs.stat(src);
  if (stat.isDirectory()) {
    const files = await listFiles(src);
    for (const file of files) {
      const rel = path.relative(src, file);
      await copyPath(file, path.join(dest, rel));
    }
    return;
  }
  await fs.mkdir(path.dirname(dest), { recursive: true });
  await fs.copyFile(src, dest);
}

async function scanForSecrets(paths: string[]): Promise<string[]> {
  const hits: string[] = [];
  for (const root of paths) {
    if (!root) continue;
    const files = await listFiles(root);
    for (const file of files) {
      const stat = await fs.stat(file);
      if (stat.size > 2 * 1024 * 1024) continue;
      const buf = await fs.readFile(file);
      if (buf.includes(0)) continue;
      const text = buf.toString("utf8");
      if (SECRET_PATTERNS.some((pattern) => pattern.test(text))) hits.push(file);
    }
  }
  return hits;
}

function traceSkillReferences(text: string): Array<{
  name?: string;
  skillPath?: string;
  embeddedContent?: string;
  detection: "trace-path" | "trace-tool-call";
  evidence: string;
}> {
  const refs: Array<{ name?: string; skillPath?: string; embeddedContent?: string; detection: "trace-path" | "trace-tool-call"; evidence: string }> = [];
  const pathPattern = /(?:[A-Za-z]:)?\/[^\s"'<>]+\/SKILL\.md/g;
  for (const row of objectRowsFromJsonl(text)) {
    const payload = asPlainObject(row.payload) || row;
    const part = asPlainObject(row.part) || asPlainObject(payload.part);
    const state = asPlainObject(part?.state);
    const partInput = asPlainObject(state?.input);
    const skillStateStatus = stringValue(state?.status)?.toLowerCase();
    if (stringValue(part?.type) === "tool" && stringValue(part?.tool)?.toLowerCase() === "skill"
      && skillStateStatus === "completed") {
      const name = stringValue(partInput?.name) || stringValue(partInput?.skill);
      const output = stringValue(state?.output);
      if (name) {
        const wrapped = output?.match(/<skill_content\b[^>]*>\s*([\s\S]*?)\s*<\/skill_content>/i)?.[1];
        refs.push({
          name,
          ...(wrapped ? { embeddedContent: wrapped } : {}),
          detection: "trace-tool-call",
          evidence: `OpenCode skill tool invoked ${name}`,
        });
      }
    }
    const callName = (
      stringValue(payload.name)
      || stringValue(asPlainObject(payload.function)?.name)
      || stringValue(row.name)
      || ""
    ).toLowerCase();
    let args = asPlainObject(payload.arguments) || asPlainObject(payload.input) || asPlainObject(payload.tool_arguments)
      || asPlainObject(row.arguments) || asPlainObject(row.tool_arguments);
    const encodedArgs = stringValue(payload.arguments) || stringValue(payload.input) || stringValue(payload.tool_arguments)
      || stringValue(row.arguments) || stringValue(row.tool_arguments);
    if (!args && encodedArgs) {
      try { args = asPlainObject(JSON.parse(encodedArgs)); } catch { /* Non-JSON tool arguments. */ }
    }
    args ||= {};
    const argumentText = (encodedArgs || JSON.stringify(args)).replaceAll("\\/", "/").replaceAll("\\\\", "\\");
    for (const match of argumentText.matchAll(pathPattern)) {
      const skillPath = match[0].trim();
      if (skillPath.includes("${")) continue;
      refs.push({
        name: path.basename(path.dirname(skillPath)),
        skillPath,
        detection: "trace-path",
        evidence: `tool ${callName || "unknown"} references ${skillPath}`,
      });
    }
    if (!/(^|[._-])skills?($|[._-])/.test(callName)) continue;
    const name = stringValue(args.skill) || stringValue(args.skill_name) || stringValue(args.name);
    if (name && /^[A-Za-z0-9_.:-]+$/.test(name)) {
      refs.push({ name, detection: "trace-tool-call", evidence: `tool ${callName} invoked skill ${name}` });
    }
  }
  const seen = new Set<string>();
  return refs.filter((ref) => {
    const key = `${ref.name || ""}\u0000${ref.skillPath || ""}\u0000${ref.detection}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

async function resolveSkillPath(name: string, roots: string[]): Promise<string | undefined> {
  const candidates = roots.flatMap((root) => [
    path.join(root, name, "SKILL.md"),
    path.join(root, name.replace(/^.*:/, ""), "SKILL.md"),
  ]);
  for (const candidate of candidates) {
    if (await exists(candidate)) return candidate;
  }
  return undefined;
}

async function collectSkillEvidence(
  opts: Record<string, OptValue>,
  tracePath: string | undefined,
  stage: string,
): Promise<{ skills: SkillEvidence[]; warnings: string[] }> {
  if (flag(opts, "no-auto-skills") && !optAll(opts, "skill").length) return { skills: [], warnings: [] };
  const warnings: string[] = [];
  const refs: Array<{ name?: string; skillPath?: string; embeddedContent?: string; detection: "explicit" | "trace-path" | "trace-tool-call"; evidence: string }> = [];
  for (const value of optAll(opts, "skill")) {
    const resolved = path.resolve(value);
    const stat = await fs.stat(resolved).catch(() => undefined);
    if (!stat) throw new CliError(`explicit skill does not exist: ${resolved}`);
    const skillPath = stat?.isDirectory() ? path.join(resolved, "SKILL.md") : resolved;
    if (!(await exists(skillPath))) throw new CliError(`explicit skill has no SKILL.md: ${resolved}`);
    refs.push({ name: path.basename(path.dirname(skillPath)), skillPath, detection: "explicit", evidence: `--skill ${value}` });
  }
  if (!flag(opts, "no-auto-skills") && tracePath) {
    refs.push(...traceSkillReferences(await fs.readFile(tracePath, "utf8")));
  }
  const home = os.homedir();
  const roots = [
    ...optAll(opts, "skill-root").map((root) => path.resolve(root)),
    path.join(process.cwd(), ".agents", "skills"),
    path.join(process.cwd(), ".codex", "skills"),
    path.join(process.cwd(), ".opencode", "skills"),
    path.join(home, ".agents", "skills"),
    path.join(home, ".codex", "skills"),
    path.join(home, ".codex", "skills", ".system"),
    path.join(home, ".opencode", "skills"),
  ];
  const grouped = new Map<string, { path?: string; embeddedContent?: string; name: string; detection: "explicit" | "trace-path" | "trace-tool-call"; evidence: string[] }>();
  for (const ref of refs) {
    let skillPath = ref.skillPath ? path.resolve(ref.skillPath) : undefined;
    if (skillPath && !(await exists(skillPath))) skillPath = undefined;
    if (!skillPath && ref.name) skillPath = await resolveSkillPath(ref.name, roots);
    if (!skillPath && !ref.embeddedContent) {
      warnings.push(`skill_not_resolved: ${ref.name || ref.skillPath || "unknown"}`);
      continue;
    }
    if (skillPath && path.basename(skillPath) !== "SKILL.md") {
      warnings.push(`skill_entrypoint_not_skill_md: ${skillPath}`);
      continue;
    }
    const root = skillPath ? path.dirname(skillPath) : undefined;
    const key = root ? await fs.realpath(root) : `embedded:${ref.name}:${createHash("sha256").update(ref.embeddedContent || "").digest("hex")}`;
    const current = grouped.get(key);
    if (current) {
      current.evidence.push(ref.evidence);
      if (current.detection !== "explicit" && ref.detection === "explicit") current.detection = "explicit";
    } else {
      grouped.set(key, {
        ...(root ? { path: root } : {}),
        ...(ref.embeddedContent ? { embeddedContent: ref.embeddedContent } : {}),
        name: ref.name || (root ? path.basename(root) : "skill"),
        detection: ref.detection,
        evidence: [ref.evidence],
      });
    }
  }
  const skills: SkillEvidence[] = [];
  const usedSlugs = new Set<string>();
  for (const item of grouped.values()) {
    const files = item.path ? await listFiles(item.path) : [];
    if (files.length > 200) throw new CliError(`skill has too many files (>200): ${item.path}`);
    let total = 0;
    for (const file of files) {
      const stat = await fs.stat(file);
      if (stat.size > 2 * 1024 * 1024) throw new CliError(`skill file exceeds 2 MiB: ${file}`);
      total += stat.size;
    }
    if (total > 10 * 1024 * 1024) throw new CliError(`skill exceeds 10 MiB: ${item.path}`);
    let slug = slugify(item.name);
    for (let suffix = 2; usedSlugs.has(slug); suffix += 1) slug = `${slugify(item.name)}-${suffix}`;
    usedSlugs.add(slug);
    const targetRoot = path.join(stage, "skills", slug);
    if (item.path) await copyPath(item.path, targetRoot);
    else {
      await fs.mkdir(targetRoot, { recursive: true });
      await fs.writeFile(path.join(targetRoot, "SKILL.md"), `${item.embeddedContent || ""}\n`);
    }
    const bundledFiles = await listFiles(targetRoot);
    skills.push({
      name: item.name,
      bundled_path: `skills/${slug}/SKILL.md`,
      detection: item.detection,
      evidence: Array.from(new Set(item.evidence)),
      skill_md_sha256: await sha256File(path.join(targetRoot, "SKILL.md")),
      files: await Promise.all(bundledFiles.map(async (file) => {
        const stat = await fs.stat(file);
        return {
          path: path.relative(stage, file).replaceAll(path.sep, "/"),
          sha256: await sha256File(file),
          size_bytes: stat.size,
        };
      })),
    });
  }
  if (skills.length) {
    const secretHits = flag(opts, "allow-secrets") ? [] : await scanForSecrets(skills.map((skill) => path.join(stage, path.dirname(skill.bundled_path))));
    if (secretHits.length) throw new CliError(`possible secrets found in skill content; refusing to package:\n${secretHits.slice(0, 20).map((hit) => `  - ${hit}`).join("\n")}`);
    await writeJsonFile(path.join(stage, "skills", "manifest.json"), {
      schema_version: "playground-skill-evidence/v1",
      generated_at: utcNow(),
      skills: skills as unknown as Json,
      warnings,
    });
  }
  return { skills, warnings };
}

function slugify(raw: string): string {
  return raw
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 96) || "harbor-task";
}

function parseTags(raw?: string): string[] {
  if (!raw) return [];
  const trimmed = raw.trim();
  if (!trimmed) return [];
  if (trimmed.startsWith("[")) {
    const data = JSON.parse(trimmed);
    if (!Array.isArray(data)) throw new CliError("--tags JSON must be an array");
    return data.map(String).filter(Boolean);
  }
  return trimmed.split(",").map((item) => item.trim()).filter(Boolean);
}

function parseExpectedOutputs(values: string[]): Record<string, Json>[] {
  if (values.length === 0) {
    return [{ path: "outputs/*", description: "Scored Harbor output artifacts", required: true }];
  }
  return values.map((item) => {
    const [outputPath, description = "Scored Harbor output artifact"] = item.split(":", 2);
    return { path: outputPath, description, required: true };
  });
}

function parseDatasetOption(raw: string): DatasetRef {
  const [dataset, version, ...prefixParts] = raw.split(":");
  if (!dataset || !version) {
    throw new CliError("--dataset must be DATASET:VERSION or DATASET:VERSION:PREFIX");
  }
  return { dataset, version, prefix: prefixParts.length ? prefixParts.join(":") : undefined };
}

function parseDatasetOptions(values: string[]): DatasetRef[] {
  return values.map(parseDatasetOption);
}

function stringList(value: unknown): string[] | undefined {
  if (Array.isArray(value)) {
    const values = value.map(stringValue).filter(Boolean) as string[];
    return values.length ? values : undefined;
  }
  const single = stringValue(value);
  if (!single) return undefined;
  const values = single.split(",").map((item) => item.trim()).filter(Boolean);
  return values.length ? values : undefined;
}

function datasetRefFromObject(obj: Record<string, any>): DatasetRef[] {
  const type = stringValue(obj.type)?.toLowerCase();
  if (type && !["dataset", "data", "resource", "asset"].includes(type)) return [];
  const dataset = stringValue(obj.resource)
    || stringValue(obj.dataset)
    || stringValue(obj.dataset_id)
    || stringValue(obj.datasetId)
    || stringValue(obj.id);
  if (!dataset) return [];
  const version = stringValue(obj.version)
    || stringValue(obj.version_id)
    || stringValue(obj.versionId);
  const prefix = stringValue(obj.prefix);
  const paths = stringList(obj.paths);
  const pathValue = stringValue(obj.path);
  const sha256 = stringValue(obj.sha256);
  const bytesValue = numberValue(obj.bytes) || numberValue(obj.size_bytes);
  return [{ dataset, version, prefix, paths, path: pathValue, sha256, bytes: bytesValue || undefined }];
}

function collectDatasetRefs(value: unknown): DatasetRef[] {
  if (typeof value === "string" && value.trim()) {
    const [dataset, version] = value.split(":", 2);
    return [{ dataset, version: version || undefined }];
  }
  if (Array.isArray(value)) return value.flatMap(collectDatasetRefs);
  const obj = asPlainObject(value);
  if (!obj) return [];
  const direct = datasetRefFromObject(obj);
  if (direct.length) return direct;
  return ["wenyon", "datasets", "data", "resources", "assets"]
    .filter((key) => obj[key] !== value)
    .flatMap((key) => collectDatasetRefs(obj[key]));
}

function configFromChallenge(challenge: Record<string, any>): Record<string, any> | undefined {
  const candidates = [
    challenge.config,
    challenge.config_json,
    challenge.configJson,
    challenge.task_config,
    challenge.taskConfig,
    asPlainObject(challenge.meta)?.config,
    asPlainObject(challenge.metadata)?.config,
  ];
  for (const candidate of candidates) {
    const obj = asPlainObject(candidate);
    if (obj) return obj;
    if (typeof candidate === "string" && candidate.trim().startsWith("{")) {
      try {
        const parsedObj = asPlainObject(JSON.parse(candidate));
        if (parsedObj) return parsedObj;
      } catch {
        // Keep looking; malformed optional config should not hide other sources.
      }
    }
  }
  return undefined;
}

function datasetRefsFromChallenge(challenge: Record<string, any>): DatasetRef[] {
  const config = configFromChallenge(challenge);
  const containers = [challenge, asPlainObject(challenge.meta), asPlainObject(challenge.metadata), config];
  const refs = containers.flatMap((container) => {
    if (!container) return [];
    return ["wenyon", "datasets", "data", "resources", "assets"]
      .flatMap((key) => collectDatasetRefs(container[key]));
  });
  const seen = new Set<string>();
  return refs.filter((ref) => {
    const key = `${ref.dataset}\u0000${ref.version || ""}\u0000${ref.prefix || ""}\u0000${(ref.paths || []).join(",")}\u0000${ref.path || ""}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function requirePinnedDatasetVersion(ref: DatasetRef): string {
  if (!ref.version) {
    throw new CliError(
      `dataset '${ref.dataset}' requires an explicit immutable pinned version for automatic download; add version, version_id, or versionId to the task metadata`,
    );
  }
  return ref.version;
}

interface WenyonDatasetFile {
  path: string;
  output: string;
  bytes: number;
  sha256: string;
}

async function getWenyonDatasetPayload(opts: Record<string, OptValue>, dataset: string): Promise<string> {
  const { stdout } = await runWenyon(opts, ["dataset", "get", dataset]);
  return stdout;
}

function simplifyDatasetGet(payload: string, dataset: string): Json {
  return {
    schema_version: "playground-data-get/v1",
    source: "wenyon",
    dataset,
    output: payload.trim(),
  };
}

async function downloadWenyonDataset(
  opts: Record<string, OptValue>,
  ref: DatasetRef,
  outPath: string,
): Promise<{ dataset: string; version: string; output: string; files: WenyonDatasetFile[] }> {
  const version = requirePinnedDatasetVersion(ref);
  await fs.mkdir(outPath, { recursive: true });
  const args = ["dataset", "download", ref.dataset, "--version", version];
  if (ref.prefix) args.push("--prefix", ref.prefix);
  if (ref.paths?.length) args.push("--paths", ref.paths.join(","));
  args.push("--output-dir", outPath, "--output", "json");
  if (!flag(opts, "dry-run")) await runWenyon(opts, args);
  const files: WenyonDatasetFile[] = [];
  if (!flag(opts, "dry-run")) {
    for (const file of await listFiles(outPath)) {
      const stat = await fs.stat(file);
      files.push({
        path: path.relative(outPath, file),
        output: file,
        bytes: stat.size,
        sha256: await sha256File(file),
      });
    }
    if (ref.sha256) {
      if (files.length !== 1) {
        throw new CliError(`dataset '${ref.dataset}@${version}' declares one package SHA-256 but downloaded ${files.length} files`);
      }
      if (files[0].sha256.toLowerCase() !== ref.sha256.toLowerCase()) {
        throw new CliError(`dataset '${ref.dataset}@${version}' SHA-256 mismatch: expected ${ref.sha256}, got ${files[0].sha256}`);
      }
    }
    if (ref.bytes !== undefined) {
      const downloadedBytes = files.reduce((sum, file) => sum + file.bytes, 0);
      if (downloadedBytes !== ref.bytes) {
        throw new CliError(`dataset '${ref.dataset}@${version}' size mismatch: expected ${ref.bytes} bytes, got ${downloadedBytes}`);
      }
    }
  }
  return {
    dataset: ref.dataset,
    version,
    output: outPath,
    files,
  };
}

function parseTomlStringField(text: string, field: string): string | undefined {
  const match = text.match(new RegExp(`^\\s*${field}\\s*=\\s*"([^"\\\\]*(?:\\\\.[^"\\\\]*)*)"\\s*$`, "m"));
  if (!match) return undefined;
  return match[1]
    .replace(/\\"/g, "\"")
    .replace(/\\n/g, "\n")
    .replace(/\\t/g, "\t")
    .trim();
}

async function readHarborTaskMeta(taskDir: string): Promise<{ name?: string; description?: string }> {
  const taskToml = path.join(taskDir, "task.toml");
  if (!(await exists(taskToml))) return {};
  const text = await fs.readFile(taskToml, "utf8");
  return {
    name: parseTomlStringField(text, "name"),
    description: parseTomlStringField(text, "description"),
  };
}

function publicHarborTaskRef(taskDir: string): string {
  const parts = path.resolve(taskDir).split(path.sep);
  const tasksIndex = parts.lastIndexOf("tasks");
  if (tasksIndex >= 0 && tasksIndex < parts.length - 1) {
    return parts.slice(tasksIndex + 1).join("/");
  }
  return path.basename(taskDir);
}

async function discoverInstruction(taskDir: string): Promise<{ file?: string; content: string }> {
  const candidates = [
    "README.md",
    "readme.md",
    "task.md",
    "TASK.md",
    "prompt.md",
    "instructions.md",
    "instruction.md",
    "problem.md",
    "statement.md",
    "description.md",
  ];
  for (const candidate of candidates) {
    const file = path.join(taskDir, candidate);
    if (await exists(file)) {
      return { file, content: await fs.readFile(file, "utf8") };
    }
  }
  for (const candidate of ["task.json", "metadata.json", "config.json"]) {
    const file = path.join(taskDir, candidate);
    if (await exists(file)) {
      const json = await readJsonFile<Record<string, Json>>(file);
      const content =
        String(json.instruction || json.prompt || json.description || json.content || "").trim() ||
        `Harbor task metadata:\n\n\`\`\`json\n${JSON.stringify(json, null, 2)}\n\`\`\``;
      return { file, content };
    }
  }
  const files = (await listFiles(taskDir)).map((file) => path.relative(taskDir, file));
  return {
    content: [
      `# Harbor task ${path.basename(taskDir)}`,
      "",
      "No canonical markdown instruction file was found. The converted task keeps the Harbor directory as the executable source of truth.",
      "",
      "## Files",
      ...files.slice(0, 200).map((file) => `- ${file}`),
    ].join("\n"),
  };
}

async function cmdConfigInit(opts: Record<string, OptValue>): Promise<void> {
  const configPath = opt(opts, "config") || DEFAULT_CONFIG_PATH;
  const data: Record<string, Json> = {
    schema_version: "playground-cli-ts-config/v0",
    apiBase: opt(opts, "api-base") || DEFAULT_PLAY_API,
    defaultTarget: "play",
    tokenEnv: opt(opts, "token-env") || "PLAYGROUND_TOKEN",
    bohrBin: opt(opts, "bohr-bin") || process.env.PLAYGROUND_BOHR_BIN || "bohr",
    createdAt: utcNow(),
  };
  await saveConfig(configPath, data);
  console.log(JSON.stringify({ status: "configured", configPath, config: data }, null, 2));
}

async function cmdHarborConvert(opts: Record<string, OptValue>): Promise<void> {
  const harborTask = path.resolve(required(opts, "harbor-task"));
  const outDir = path.resolve(opt(opts, "out") || path.join(process.cwd(), "playground-challenge"));
  const taskMeta = await readHarborTaskMeta(harborTask);
  const taskRef = publicHarborTaskRef(harborTask);
  const title = opt(opts, "title") || taskMeta.description || path.basename(harborTask);
  const challengeId = opt(opts, "challenge-id") || slugify(title);
  const tags = ["harbor", "paper2arm", ...parseTags(opt(opts, "tags"))];
  const instruction = await discoverInstruction(harborTask);
  const expectedOutputs = parseExpectedOutputs(optAll(opts, "expected-output"));
  const datasetRefs = parseDatasetOptions(optAll(opts, "dataset"));
  const instructionText = instruction.content.trim();
  const content = [
    ...(instructionText.match(/^#\s+/) ? [instructionText] : [`# ${title}`, "", instructionText]),
    "",
    "## Submission",
    "",
    "Submit an ARM v1.1 bundle that contains:",
    "",
    "- `outputs/` with the files required by the Harbor checker",
    "- `execution/run.log` or equivalent run log",
    "- `traces/trace.jsonl` and, when available, raw agent messages",
    "- `arm_manifest.json` and `characterization.json`",
    "",
    "## Expected outputs",
    "",
    ...expectedOutputs.map((item) => `- \`${item.path}\`: ${item.description}`),
  ].join("\n");
  const challenge: Record<string, Json> = {
    id: challengeId,
    title,
    title_zh: opt(opts, "title-zh") || title,
    abstract: opt(opts, "abstract") || "Solve the task and submit the required output artifacts for automated Harbor evaluation.",
    author: opt(opts, "author") || "Harbor / Paper2ARM",
    year: Number(opt(opts, "year") || "2026"),
    journal: opt(opts, "journal") || "Harbor",
    disc: opt(opts, "disc") || "physics",
    difficulty: Number(opt(opts, "difficulty") || "3"),
    tags,
    content,
    hasContent: true,
    status: "open",
    reviewStatus: "draft",
    origin: "harbor",
    attempts: 0,
    bestScore: null,
    scoring: {
      strategy: "harbor_hidden_verifier",
      score_range: [0, 100],
      formula_summary: "Score is produced by the Harbor/LBG checker after submission.",
      protocol_url: "/api/protocol",
    },
    meta: {
      source: "harbor",
      harborTaskRef: taskRef,
      harborTaskName: taskMeta.name || null,
      expectedOutputs,
      datasets: datasetRefs as unknown as Json,
      gettingStarted: "Open the Guide tab, solve the Harbor task, then submit an ARM v1.1 bundle with outputs and trace evidence.",
      generatedBy: `@paper2arm/playground-cli ${VERSION}`,
      generatedAt: utcNow(),
    },
  };
  const manifest: Record<string, Json> = {
    schema_version: "playground-harbor-task/v0",
    task_id: challengeId,
    domain: String(challenge.disc),
    title,
    harbor_task_path: taskRef,
    display: {
      instruction_md: "task.md",
      expected_outputs: expectedOutputs,
    },
    submission: {
      bundle_format: "zip",
      max_bytes: 256 * 1024 * 1024,
      required_paths: ["outputs/", "arm_manifest.json", "traces/trace.jsonl"],
      optional_paths: ["execution/run.log", "characterization.json", "traces/raw_messages.jsonl"],
    },
    evaluation: {
      result_checker: "harbor hidden verifier",
      process_checker: "Playground trace/bundle validation",
    },
    datasets: datasetRefs as unknown as Json,
  };
  await fs.mkdir(outDir, { recursive: true });
  await writeJsonFile(path.join(outDir, "challenge.json"), challenge);
  const suppliedConfig = configFromChallenge(challenge);
  const portableConfig: Record<string, Json> = suppliedConfig || {
    id: challengeId,
    wenyon: {
      datasets: datasetRefs as unknown as Json,
    },
  };
  if (!portableConfig.id) portableConfig.id = challengeId;
  await writeJsonFile(path.join(outDir, "config.json"), portableConfig);
  await fs.writeFile(path.join(outDir, "task.md"), content);
  await fs.writeFile(path.join(outDir, "rubric.md"), [
    "# Rubric",
    "",
    "The original Harbor checker/verifier evaluates the submitted `outputs/`.",
    "Process evidence is inspected from the ARM bundle trace and logs.",
    "",
  ].join("\n"));
  await writeJsonFile(path.join(outDir, "playground_manifest.json"), manifest);
  console.log(JSON.stringify({
    status: "converted",
    challenge_id: challengeId,
    outDir,
    upload: `playground task upload --challenge-dir ${outDir} --target play`,
    workerUpload: `playground task upload --challenge-dir ${outDir} --target worker`,
  }, null, 2));
}

async function cmdTaskGuide(opts: Record<string, OptValue>): Promise<void> {
  const skillPath = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "skill", "paper2arm-forge", "SKILL.md");
  if (flag(opts, "path")) {
    console.log(skillPath);
    return;
  }
  console.log(await fs.readFile(skillPath, "utf8"));
}

async function cmdTaskPreflight(opts: Record<string, OptValue>): Promise<void> {
  const strict = flag(opts, "strict");
  const report = await preflightTask(required(opts, "task-dir"), strict);
  if (flag(opts, "json")) console.log(JSON.stringify(report, null, 2));
  else process.stdout.write(formatPreflight(report));
  if (report.summary.errors > 0 || (strict && report.summary.warnings > 0)) process.exitCode = 1;
}

async function cmdTaskPackage(opts: Record<string, OptValue>): Promise<void> {
  const strict = flag(opts, "strict");
  const out = path.resolve(required(opts, "out"));
  const manifestPath = `${out}.manifest.json`;
  const report = await preflightTask(required(opts, "task-dir"), strict);
  if (out === report.task_root || out.startsWith(`${report.task_root}${path.sep}`)) {
    throw new CliError("--out must be outside the task directory so packaging cannot change its inventory");
  }
  if (report.summary.errors > 0 || (strict && report.summary.warnings > 0)) {
    if (flag(opts, "json")) console.log(JSON.stringify(report, null, 2)); else process.stdout.write(formatPreflight(report));
    throw new CliError("task package stopped because preflight failed");
  }
  const archive = await writeTaskZip(report, out);
  const manifest = {
    schema_version: PACKAGE_SCHEMA,
    archive: { path: path.basename(out), ...archive },
    preflight: report,
    complete_package: true,
    upload_available: true,
    message: "Use playground task upload-package to send this complete package to the verified Worker endpoint.",
  };
  await writeJsonFile(manifestPath, manifest as unknown as Record<string, Json>);
  console.log(JSON.stringify({ schema_version: PACKAGE_SCHEMA, status: "packaged", archive: out, manifest: manifestPath, ...archive, files: report.summary.files, includes_hidden: report.inventory.some((item) => item.classification === "hidden_grading"), uploaded: false, message: manifest.message }, null, 2));
}

class TaskPackageHttpError extends Error {
  statusCode: number;
  retryable: boolean;
  constructor(statusCode: number, message: string) {
    super(message);
    this.statusCode = statusCode;
    this.retryable = statusCode === 408 || statusCode === 429 || statusCode >= 500;
  }
}

function taskPackageWorkerBase(opts: Record<string, OptValue>, config: Record<string, Json>): string {
  const raw = opt(opts, "worker-api-base") || process.env.PLAYGROUND_WORKER_API_BASE ||
    apiBase({ ...opts, target: "worker" }, config);
  let url: URL;
  try { url = new URL(raw); } catch { throw new CliError("--worker-api-base must be a valid http(s) URL"); }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new CliError("--worker-api-base must use http or https");
  }
  return url.toString().replace(/\/+$/, "");
}

function taskPackageVisibility(opts: Record<string, OptValue>): "private" | "public" {
  const visibility = opt(opts, "visibility") || "private";
  if (visibility !== "private" && visibility !== "public") {
    throw new CliError("--visibility must be private or public");
  }
  return visibility;
}

function taskPackageIdempotencyKey(packageSha256: string, visibility: string, supplied?: string): string {
  if (supplied) {
    if (!/^[A-Za-z0-9._:-]{8,128}$/.test(supplied)) {
      throw new CliError("--idempotency-key must be 8-128 characters using letters, numbers, dot, underscore, colon, or hyphen");
    }
    return supplied;
  }
  const stable = createHash("sha256").update(packageSha256).update("\0").update(visibility).digest("hex");
  return `task-package:${stable}`;
}

function safeWorkerErrorText(text: string, token: string): string {
  let safe = text.replaceAll(token, "[REDACTED]").replace(/Bearer\s+\S+/gi, "Bearer [REDACTED]");
  safe = safe.replace(/[\r\n\t]+/g, " ").trim();
  return safe.slice(0, 500);
}

async function streamTaskPackageMultipart(
  endpoint: string, packagePath: string, packageBytes: number, token: string,
  idempotencyKey: string, visibility: string,
): Promise<Record<string, any>> {
  const url = new URL(endpoint);
  const boundary = `----playground-task-package-${randomBytes(18).toString("hex")}`;
  const field = (name: string, value: string) => Buffer.from(
    `--${boundary}\r\nContent-Disposition: form-data; name="${name}"\r\n\r\n${value}\r\n`, "utf8",
  );
  const safeFilename = path.basename(packagePath).replace(/["\r\n]/g, "_");
  const prefix = Buffer.concat([
    field("idempotency_key", idempotencyKey),
    field("visibility", visibility),
    Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="package"; filename="${safeFilename}"\r\nContent-Type: application/zip\r\n\r\n`, "utf8"),
  ]);
  const suffix = Buffer.from(`\r\n--${boundary}--\r\n`, "utf8");
  const contentLength = prefix.length + packageBytes + suffix.length;
  const transport = url.protocol === "https:" ? https : http;
  return new Promise((resolve, reject) => {
    const request = transport.request(url, {
      method: "POST",
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${token}`,
        "Content-Type": `multipart/form-data; boundary=${boundary}`,
        "Content-Length": String(contentLength),
      },
    }, (response) => {
      const chunks: Buffer[] = [];
      let received = 0;
      response.on("data", (chunk: Buffer) => {
        received += chunk.length;
        if (received > WORKER_MAX_RESPONSE_BYTES) {
          response.destroy(new Error("Worker response exceeded the 1 MiB client limit"));
          return;
        }
        chunks.push(chunk);
      });
      response.on("error", reject);
      response.on("end", () => {
        const body = Buffer.concat(chunks).toString("utf8");
        const status = response.statusCode || 0;
        if (status < 200 || status >= 300) {
          reject(new TaskPackageHttpError(status, `Worker HTTP ${status}${body.trim() ? `: ${safeWorkerErrorText(body, token)}` : ""}`));
          return;
        }
        if (!body.trim()) { resolve({}); return; }
        try { resolve(JSON.parse(body)); }
        catch { reject(new CliError("Worker returned a non-JSON success response")); }
      });
    });
    request.on("error", (error) => reject(new Error(safeWorkerErrorText(error.message, token))));
    request.write(prefix);
    const stream = createReadStream(packagePath);
    stream.on("error", reject);
    stream.on("data", (chunk) => {
      if (!request.write(chunk)) {
        stream.pause();
        request.once("drain", () => stream.resume());
      }
    });
    stream.on("end", () => request.end(suffix));
  });
}

async function uploadTaskPackageWithRetry(
  endpoint: string, packagePath: string, packageBytes: number, token: string,
  idempotencyKey: string, visibility: string,
): Promise<Record<string, any>> {
  let lastError: unknown;
  for (const delayMs of [0, 250, 750]) {
    if (delayMs) await sleep(delayMs);
    try {
      return await streamTaskPackageMultipart(endpoint, packagePath, packageBytes, token, idempotencyKey, visibility);
    } catch (error) {
      lastError = error;
      if (error instanceof TaskPackageHttpError && !error.retryable) throw error;
      if (error instanceof CliError && !(error instanceof TaskPackageHttpError)) throw error;
    }
  }
  throw lastError;
}

function taskPackageResponseValue(response: Record<string, any>, ...keys: string[]): unknown {
  for (const key of keys) {
    if (response[key] !== undefined) return response[key];
    if (asPlainObject(response.challenge)?.[key] !== undefined) return asPlainObject(response.challenge)![key];
    if (asPlainObject(response.task)?.[key] !== undefined) return asPlainObject(response.task)![key];
  }
  return null;
}

async function cmdTaskUploadPackage(opts: Record<string, OptValue>): Promise<void> {
  const taskDir = opt(opts, "task-dir");
  const suppliedPackage = opt(opts, "package");
  if (Boolean(taskDir) === Boolean(suppliedPackage)) {
    throw new CliError("provide exactly one of --task-dir or --package");
  }
  const strict = flag(opts, "strict");
  const visibility = taskPackageVisibility(opts);
  const config = await loadConfig(opts);
  const workerBase = taskPackageWorkerBase(opts, config);
  const endpoint = `${workerBase}/task-packages`;
  let tempDir: string | undefined;
  let packagePath: string;
  let preflight: Awaited<ReturnType<typeof preflightTask>> | undefined;
  try {
    if (taskDir) {
      preflight = await preflightTask(taskDir, strict);
      if (preflight.summary.errors > 0 || (strict && preflight.summary.warnings > 0)) {
        if (flag(opts, "json")) console.log(JSON.stringify(preflight, null, 2)); else process.stdout.write(formatPreflight(preflight));
        throw new CliError("task package upload stopped because preflight failed");
      }
      tempDir = await fs.mkdtemp(path.join(os.tmpdir(), "playground-task-package-"));
      await fs.chmod(tempDir, 0o700);
      packagePath = path.join(tempDir, "task-package.zip");
      await writeTaskZip(preflight, packagePath);
      await fs.chmod(packagePath, 0o600);
    } else {
      packagePath = path.resolve(suppliedPackage!);
      const stat = await fs.stat(packagePath).catch(() => undefined);
      if (!stat?.isFile()) throw new CliError(`package file not found: ${packagePath}`);
    }
    const packageBytes = (await fs.stat(packagePath)).size;
    if (packageBytes > WORKER_MAX_TASK_PACKAGE_BYTES) {
      throw new CliError(`task package is ${(packageBytes / 1024 / 1024).toFixed(1)} MiB; Worker limit is 128 MiB compressed`);
    }
    const packageSha256 = await sha256File(packagePath);
    const idempotencyKey = taskPackageIdempotencyKey(packageSha256, visibility, opt(opts, "idempotency-key"));
    const metadata = {
      endpoint,
      package_sha256: packageSha256,
      package_bytes: packageBytes,
      idempotency_key: idempotencyKey,
      visibility,
    };
    if (flag(opts, "dry-run")) {
      console.log(JSON.stringify({ schema_version: "playground-task-package-upload/v1", status: "dry_run", ...metadata, preflight: preflight || null }, null, 2));
      return;
    }
    const token = bearerToken({ ...opts, target: "play" }, config);
    if (!token) throw new CliError("not logged in: run playground auth login or set PLAYGROUND_TOKEN");
    const response = await uploadTaskPackageWithRetry(endpoint, packagePath, packageBytes, token, idempotencyKey, visibility);
    const challengeId = taskPackageResponseValue(response, "challenge_id", "challengeId", "id");
    const challengeUrl = taskPackageResponseValue(response, "challenge_url", "challengeUrl", "url");
    const sourceQuestionId = taskPackageResponseValue(response, "sourceQuestionId", "source_question_id");
    console.log(JSON.stringify({
      schema_version: "playground-task-package-upload/v1",
      status: "uploaded",
      ...metadata,
      challenge_id: challengeId,
      challenge_url: challengeUrl,
      sourceQuestionId,
      package: { sha256: packageSha256, bytes: packageBytes, readiness: taskPackageResponseValue(response, "readiness", "status") || "worker_accepted", wenyon: "pending" },
      worker_response: response,
    }, null, 2));
  } finally {
    if (tempDir) await fs.rm(tempDir, { recursive: true, force: true });
  }
}

async function cmdTaskUpload(opts: Record<string, OptValue>): Promise<void> {
  const config = await loadConfig(opts);
  const base = apiBase(opts, config);
  const token = bearerToken(opts, config);
  const challengeDir = path.resolve(required(opts, "challenge-dir"));
  const challengePath = path.join(challengeDir, "challenge.json");
  const challenge = await readJsonFile<Record<string, Json>>(challengePath);
  const visibility = opt(opts, "visibility");
  if (opts.visibility !== undefined && visibility === undefined) {
    throw new CliError("--visibility requires public or private");
  }
  if (visibility !== undefined) {
    if (visibility !== "public" && visibility !== "private") {
      throw new CliError("--visibility must be public or private");
    }
    challenge.visibility = visibility;
  }
  const taskMd = path.join(challengeDir, "task.md");
  const rubricMd = path.join(challengeDir, "rubric.md");
  if (await exists(taskMd)) challenge.content = await fs.readFile(taskMd, "utf8");
  if (await exists(rubricMd)) challenge.rubric = await fs.readFile(rubricMd, "utf8");
  const created = await requestJson<Record<string, Json>>(
    `${base}/challenges`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(challenge),
    },
    token,
  );
  const challengeId = String(created.id || challenge.id);
  console.log(JSON.stringify({
    schema_version: "playground-task-upload/v0",
    status: "uploaded",
    target: targetName(opts, config),
    api_base: base,
    challenge_id: challengeId,
    challenge_url: `${publicBaseFromApi(base)}/#challenge/${challengeId}`,
    challenge: created,
  }, null, 2));
}

async function loadChallengePackage(challengeDir: string): Promise<Record<string, Json>> {
  const resolved = path.resolve(challengeDir);
  const challengePath = path.join(resolved, "challenge.json");
  if (!(await exists(challengePath))) {
    throw new CliError(`challenge.json not found in ${resolved}`);
  }
  const challenge = await readJsonFile<Record<string, Json>>(challengePath);
  const taskMd = path.join(resolved, "task.md");
  const rubricMd = path.join(resolved, "rubric.md");
  if (await exists(taskMd)) challenge.content = await fs.readFile(taskMd, "utf8");
  if (await exists(rubricMd)) challenge.rubric = await fs.readFile(rubricMd, "utf8");
  // Exported/downloaded packages may contain server-managed fields. They are
  // useful locally but ordinary users are forbidden from setting them again.
  for (const key of [
    "reviewStatus", "reviewedBy", "reviewedAt", "reviewNote",
    "hackathonSeasonId", "roundId", "roundStartAt", "roundEndAt",
    "submittedBy", "attempts", "bestScore", "starCount", "createdAt", "updatedAt",
  ]) delete challenge[key];
  if (!stringValue(challenge.title)) throw new CliError(`challenge title is missing in ${challengePath}`);
  if (!stringValue(challenge.rubric)) throw new CliError(`challenge rubric is missing in ${challengePath}`);
  return challenge;
}

async function benchmarkChallengeDirs(opts: Record<string, OptValue>): Promise<string[]> {
  const dirs = optAll(opts, "challenge-dir").map((value) => path.resolve(value));
  const root = opt(opts, "challenge-root");
  if (root) {
    const resolvedRoot = path.resolve(root);
    if (await exists(path.join(resolvedRoot, "challenge.json"))) dirs.push(resolvedRoot);
    const entries = await fs.readdir(resolvedRoot, { withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      const candidate = path.join(resolvedRoot, entry.name);
      if (await exists(path.join(candidate, "challenge.json"))) dirs.push(candidate);
    }
  }
  const unique = [...new Set(dirs)].sort();
  if (unique.length === 0) {
    throw new CliError("pass --challenge-root DIR or repeat --challenge-dir DIR");
  }
  return unique;
}

async function cmdBenchmarkUpload(opts: Record<string, OptValue>): Promise<void> {
  const config = await loadConfig(opts);
  const base = apiBase(opts, config);
  const token = bearerToken(opts, config);
  if (!token) throw new CliError("benchmark upload requires authentication");
  const visibility = opt(opts, "visibility") || "private";
  if (visibility !== "public" && visibility !== "private") {
    throw new CliError("--visibility must be public or private");
  }
  const dirs = await benchmarkChallengeDirs(opts);
  const packages: Array<{ dir: string; challenge: Record<string, Json> }> = [];
  for (const dir of dirs) packages.push({ dir, challenge: await loadChallengePackage(dir) });

  const requestedSlug = opt(opts, "benchmark-slug");
  let benchmark: Record<string, Json>;
  if (requestedSlug) {
    benchmark = await requestJson<Record<string, Json>>(
      `${base}/benchmarks/${encodeURIComponent(requestedSlug)}`,
      {},
      token,
    );
  } else {
    const name = required(opts, "name");
    benchmark = await requestJson<Record<string, Json>>(`${base}/benchmarks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        slug: opt(opts, "slug"),
        description: opt(opts, "description"),
        gradingModel: opt(opts, "grading-model"),
        visibility,
      }),
    }, token);
  }
  const benchmarkId = benchmark.id;
  const benchmarkSlug = stringValue(benchmark.slug) || requestedSlug;
  if ((typeof benchmarkId !== "number" && typeof benchmarkId !== "string") || !benchmarkSlug) {
    throw new CliError("Playground returned an invalid benchmark response");
  }

  const existingKeys = new Set<string>();
  let page = 1;
  for (;;) {
    const listed = await requestJson<Record<string, any>>(
      `${base}/benchmarks/${encodeURIComponent(benchmarkSlug)}/challenges?page=${page}&per_page=200&sort=title`,
      {},
      token,
    );
    const items = Array.isArray(listed.items) ? listed.items : [];
    for (const item of items) {
      if (typeof item?.id === "string") existingKeys.add(`id:${item.id}`);
      const title = stringValue(item?.title);
      if (title) existingKeys.add(`title:${title}`);
      const sourceId = stringValue(item?.sourceQuestionId) || stringValue(item?.source_question_id);
      if (sourceId) existingKeys.add(`source:${sourceId}`);
    }
    if (!listed.has_more && !listed.hasMore) break;
    page += 1;
  }

  const uploaded: string[] = [];
  const skipped: string[] = [];
  for (const item of packages) {
    const sourceId = stringValue(item.challenge.sourceQuestionId)
      || stringValue(item.challenge.source_question_id);
    const challengeId = stringValue(item.challenge.id);
    const challengeTitle = stringValue(item.challenge.title);
    if ((sourceId && existingKeys.has(`source:${sourceId}`))
        || (challengeId && existingKeys.has(`id:${challengeId}`))
        || (challengeTitle && existingKeys.has(`title:${challengeTitle}`))) {
      skipped.push(sourceId || challengeId || challengeTitle || item.dir);
      continue;
    }
    item.challenge.benchmarkId = benchmarkId as Json;
    item.challenge.origin = "benchmark";
    item.challenge.visibility = visibility;
    const created = await requestJson<Record<string, Json>>(`${base}/challenges`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(item.challenge),
    }, token);
    const createdId = String(created.id || challengeId || sourceId || item.dir);
    uploaded.push(createdId);
    if (sourceId) existingKeys.add(`source:${sourceId}`);
    if (challengeTitle) existingKeys.add(`title:${challengeTitle}`);
    existingKeys.add(`id:${createdId}`);
  }

  console.log(JSON.stringify({
    schema_version: "playground-benchmark-upload/v0",
    status: "uploaded",
    api_base: base,
    benchmark_id: benchmarkId,
    benchmark_slug: benchmarkSlug,
    benchmark_url: `${publicBaseFromApi(base)}/#benchmark/${benchmarkSlug}`,
    requested: packages.length,
    uploaded_count: uploaded.length,
    skipped_count: skipped.length,
    uploaded,
    skipped,
  }, null, 2));
}

async function cmdTaskList(opts: Record<string, OptValue>): Promise<void> {
  const config = await loadConfig(opts);
  const base = apiBase(opts, config);
  const token = bearerToken(opts, config);
  const tagFilters = optAll(opts, "tag")
    .flatMap((value) => value.split(","))
    .map((value) => value.trim())
    .filter(Boolean);
  const rawLimit = Number(opt(opts, "limit") || "30");
  const limit = Number.isFinite(rawLimit) && rawLimit > 0 ? Math.floor(rawLimit) : 30;
  const challengeRows = await fetchChallengeRows(
    base,
    token,
    tagFilters.length > 0 ? Number.POSITIVE_INFINITY : limit,
  );
  const filteredRows = challengeRows.rows.filter((row) => matchesTagFilter(row, tagFilters));
  const visibleTotal = tagFilters.length > 0 ? filteredRows.length : challengeRows.total;
  const selected = filteredRows.slice(0, limit);
  if (flag(opts, "json")) {
    console.log(JSON.stringify({
      schema_version: "playground-task-list/v0",
      api_base: base,
      total: visibleTotal,
      total_unfiltered: challengeRows.total,
      tag_filter: tagFilters,
      tasks: selected.map((row, index) => ({
        index: index + 1,
        id: String(row.id),
        title: stringValue(row.title) || stringValue(row.title_zh) || "",
        status: stringValue(row.status) || "",
        attempts: numberValue(row.attempts),
        tags: tagsFromRow(row),
        datasets: datasetRefsFromChallenge(row).map((ref) => ({ dataset: ref.dataset, version: ref.version || null })),
        download_command: `playground task download --challenge-id ${String(row.id)} --out ${String(row.id)}`,
      })),
    }, null, 2));
    return;
  }
  if (selected.length === 0) {
    const detail = tagFilters.length > 0 ? ` for tag ${tagFilters.join(",")}` : "";
    console.error(`No tasks found${detail}.`);
    return;
  }
  for (const [index, row] of selected.entries()) {
    const title = stringValue(row.title) || stringValue(row.title_zh) || "";
    const tags = tagsFromRow(row);
    const tagText = tags.length ? `  [${tags.join(",")}]` : "";
    const suffix = title ? `  ${title}` : "";
    const datasetCount = datasetRefsFromChallenge(row).length;
    const dataText = datasetCount ? `  [data:${datasetCount}]` : "";
    console.log(`${index + 1}\t${String(row.id)}${tagText}${dataText}${suffix}`);
    if (datasetCount) console.log(`\tDownload: playground task download --challenge-id ${String(row.id)} --out ${String(row.id)}`);
  }
  if (visibleTotal > selected.length) {
    const filterText = tagFilters.length ? ` matching tag ${tagFilters.join(",")}` : "";
    console.error(`Showing ${selected.length}/${visibleTotal}${filterText}; pass --limit ${visibleTotal} to show all.`);
  }
}

async function cmdTaskDownload(opts: Record<string, OptValue>): Promise<void> {
  const config = await loadConfig(opts);
  const base = apiBase(opts, config);
  const token = bearerToken(opts, config);
  const inputChallengeId = required(opts, "challenge-id");
  const challengeId = await resolveChallengeId(base, token, inputChallengeId);
  const outDir = path.resolve(opt(opts, "out") || challengeId);
  let challenge: Record<string, Json>;
  try {
    challenge = await requestJson<Record<string, Json>>(`${base}/challenges/${encodeURIComponent(challengeId)}`, {}, token);
  } catch (error) {
    if (error instanceof CliError && error.message.includes("HTTP 404")) {
      throw new CliError(`${error.message}\nHint: run 'playground task list --limit 20' and pass one of the listed string ids, or use a numeric list index such as --challenge-id 1.`);
    }
    throw error;
  }
  await fs.mkdir(outDir, { recursive: true });
  await writeJsonFile(path.join(outDir, "challenge.json"), challenge);
  const datasetRefs = flag(opts, "skip-datasets") ? [] : datasetRefsFromChallenge(challenge);
  const suppliedConfig = configFromChallenge(challenge);
  const portableConfig: Record<string, Json> = suppliedConfig || {
    id: challengeId,
    wenyon: { datasets: datasetRefs as unknown as Json },
  };
  if (!portableConfig.id) portableConfig.id = challengeId;
  await writeJsonFile(path.join(outDir, "config.json"), portableConfig);
  if (typeof challenge.content === "string") await fs.writeFile(path.join(outDir, "task.md"), challenge.content);
  if (typeof challenge.rubric === "string") await fs.writeFile(path.join(outDir, "rubric.md"), challenge.rubric);
  const datasetRoot = path.resolve(opt(opts, "dataset-out") || path.join(outDir, "datasets"));
  const datasetDownloads: Awaited<ReturnType<typeof downloadWenyonDataset>>[] = [];
  for (const ref of datasetRefs) {
    const version = requirePinnedDatasetVersion(ref);
    const target = ref.path
      ? path.resolve(outDir, ref.path)
      : path.join(datasetRoot, slugify(ref.dataset), slugify(version));
    datasetDownloads.push(await downloadWenyonDataset(opts, ref, target));
  }
  console.log(JSON.stringify({
    status: "downloaded",
    challenge_id: challengeId,
    input_challenge_id: inputChallengeId,
    outDir,
    source: "wenyon",
    datasets: datasetDownloads,
  }, null, 2));
}

function pushStringFlag(args: string[], opts: Record<string, OptValue>, optKey: string, cliFlag = optKey): void {
  const value = opt(opts, optKey);
  if (value) args.push(`--${cliFlag}`, value);
}

async function cmdDataList(opts: Record<string, OptValue>): Promise<void> {
  const args = ["dataset", "list"];
  if (flag(opts, "include-hidden")) args.push("--include-hidden");
  if (flag(opts, "dry-run")) {
    console.log(JSON.stringify({
      schema_version: "playground-data-list/v1",
      status: "dry_run",
      source: "wenyon",
      command: [wenyonCommand(opts).file, ...wenyonCommandArgs(opts, args)],
    }, null, 2));
    return;
  }
  const { stdout } = await runWenyon(opts, args);
  console.log(JSON.stringify({
    schema_version: "playground-data-list/v1",
    source: "wenyon",
    output: stdout.trim(),
  }, null, 2));
}

async function cmdDataGet(opts: Record<string, OptValue>): Promise<void> {
  const dataset = opt(opts, "dataset") || opt(opts, "id") || required(opts, "name");
  if (flag(opts, "dry-run")) {
    console.log(JSON.stringify({
      schema_version: "playground-data-get/v1",
      status: "dry_run",
      source: "wenyon",
      dataset,
    }, null, 2));
    return;
  }
  const payload = await getWenyonDatasetPayload(opts, dataset);
  console.log(JSON.stringify(simplifyDatasetGet(payload, dataset), null, 2));
}

async function cmdDataPull(opts: Record<string, OptValue>): Promise<void> {
  const dataset = opt(opts, "dataset") || opt(opts, "id") || required(opts, "name");
  const version = required(opts, "version");
  const prefix = opt(opts, "prefix");
  const paths = stringList(optAll(opts, "paths").flatMap((value) => value.split(",")));
  const ref: DatasetRef = { dataset, version, prefix, paths };
  const rawOut = opt(opts, "out") || opt(opts, "output-dir") || opt(opts, "output");
  const outPath = rawOut
    ? path.resolve(rawOut)
    : path.resolve("data", slugify(dataset), slugify(version));
  const result = await downloadWenyonDataset(opts, ref, outPath);
  console.log(JSON.stringify({
    schema_version: "playground-data-pull/v1",
    status: flag(opts, "dry-run") ? "dry_run" : "downloaded",
    source: "wenyon",
    dataset: result.dataset,
    version: result.version,
    output: result.output,
    files: result.files as unknown as Json,
  }, null, 2));
}

async function cmdDoctor(opts: Record<string, OptValue>): Promise<void> {
  const results: Record<string, Json> = {
    schema_version: "playground-doctor/v0",
    playground_version: VERSION,
    node: process.version,
    wenyon: null,
  };
  try {
    const command = wenyonCommand(opts);
    const helpArgs = [...command.prefix, "--help"];
    const { stdout } = await runProcess(command.file, helpArgs);
    results.wenyon = {
      status: "present",
      command: wenyonCommandDisplay(opts, ["--help"]),
      summary: stdout.trim().split(/\r?\n/)[0] || "available",
    };
  } catch (error) {
    if (flag(opts, "install-wenyon") || flag(opts, "install-if-missing")) {
      await installWenyon(opts);
      const command = wenyonCommand(opts);
      await runProcess(command.file, [...command.prefix, "--help"]);
      results.wenyon = { status: "installed", command: wenyonCommandDisplay(opts, ["--help"]) };
    } else {
      results.wenyon = {
        status: "missing",
        install: "bohr update",
        auth_local: "bohr auth login",
        auth_remote: "bohr auth login --device",
        error: error instanceof Error ? error.message : String(error),
      };
    }
  }
  if (!flag(opts, "quiet")) console.log(JSON.stringify(results, null, 2));
}

interface SubmissionIdentity {
  declaredModel?: string;
  declaredHarness?: string;
  detectedModel?: string;
  detectedHarness?: string;
  model: string;
  harness: string;
}

function mostFrequent(values: Array<string | undefined>): string | undefined {
  const counts = new Map<string, number>();
  for (const value of values) {
    if (!value) continue;
    counts.set(value, (counts.get(value) || 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
}

async function submissionIdentity(
  opts: Record<string, OptValue>,
  traceSteps: Record<string, Json>[],
): Promise<SubmissionIdentity> {
  const declaredModel = opt(opts, "model") || process.env.PLAYGROUND_MODEL;
  const declaredHarness = opt(opts, "harness") || process.env.PLAYGROUND_HARNESS;
  const detectedModel = mostFrequent(traceSteps.map((step) =>
    stringValue(step.model_id) || stringValue(step.modelId) || stringValue(step.model_name) || stringValue(step.model),
  ));
  let detectedHarness: string | undefined;
  const traceFormat = (opt(opts, "trace-format") || "").toLowerCase();
  const tracePath = opt(opts, "trace");
  if (traceFormat && traceFormat !== "auto" && traceFormat !== "arm") detectedHarness = traceFormat;
  if (!detectedHarness && tracePath) {
    const text = await fs.readFile(path.resolve(tracePath), "utf8");
    const rows = objectRowsFromJsonl(text);
    const lower = text.slice(0, 2_000_000).toLowerCase();
    if (opencodeEventLike(rows) || /\bopencode\b/.test(lower)) detectedHarness = "opencode";
    else if (claudeCodeEventLike(rows) || /\bclaude[-_ ]?code\b/.test(lower)) detectedHarness = "claude-code";
    else if (/\bcodex\b/.test(lower)) detectedHarness = "codex";
    else if (/\b(openclaw|arkclaw)\b/.test(lower)) detectedHarness = "openclaw";
    else if (/\bharbor[-_ ]?lbg\b/.test(lower)) detectedHarness = "harbor-lbg";
  }
  return {
    declaredModel,
    declaredHarness,
    detectedModel,
    detectedHarness,
    model: declaredModel || detectedModel || "unknown",
    harness: declaredHarness || detectedHarness || "harbor-lbg",
  };
}

type DetectedTrace = { path: string; harness: string };

function atifArguments(value: unknown): Record<string, Json> {
  const object = asPlainObject(value);
  return object ? jsonValue(object) as Record<string, Json> : { value: jsonValue(value) };
}

function atifMetrics(step: Record<string, Json>): Record<string, Json> | undefined {
  const promptTokens = numberValue(step.tokens_in);
  const completionTokens = numberValue(step.tokens_out);
  const costUsd = numberValue(step.cost_usd);
  if (!promptTokens && !completionTokens && !costUsd) return undefined;
  return {
    prompt_tokens: promptTokens,
    completion_tokens: completionTokens,
    cost_usd: costUsd,
  };
}

function armStepsToAtif(
  steps: Record<string, Json>[],
  subagentRefs: Map<string, Record<string, Json>> = new Map(),
): Record<string, Json>[] {
  const converted: Record<string, Json>[] = [];
  const calls = new Map<string, Record<string, Json>>();
  for (const [index, step] of steps.entries()) {
    const stepType = stringValue(step.step_type) || stringValue(step.type) || "observation";
    const callId = stringValue(step.tool_call_id);
    const body = stringValue(step.body) || stringValue(step.tool_output) || "";
    if (["tool_result", "error"].includes(stepType) && callId && calls.has(callId)) {
      const callStep = calls.get(callId)!;
      const observation = asPlainObject(callStep.observation) || { results: [] };
      const results = Array.isArray(observation.results) ? observation.results : [];
      const result: Record<string, Json> = {
        content: body,
        source_call_id: callId,
        extra: {
          arm_result_step_id: stringValue(step.step_id) || "",
          ...(stringValue(step.timestamp) ? { result_timestamp: stringValue(step.timestamp) } : {}),
          ...(stepType === "error" ? { is_error: true } : {}),
        },
      };
      const subagentRef = subagentRefs.get(callId);
      if (subagentRef) result.subagent_trajectory_ref = [subagentRef];
      results.push(result);
      callStep.observation = { ...observation, results };
      continue;
    }
    const source = ["thought", "tool_call", "tool_result", "artifact", "decision"].includes(stepType)
      ? "agent"
      : stepType === "error" ? "system" : "user";
    const atifStep: Record<string, Json> = {
      step_id: converted.length + 1,
      source,
      message: ["thought", "tool_result"].includes(stepType) ? "" : body,
      extra: {
        arm_step_id: stringValue(step.step_id) || "",
        arm_step_type: stepType,
      },
    };
    const timestamp = stringValue(step.timestamp);
    const modelName = stringValue(step.model_id) || stringValue(step.model_name);
    if (timestamp) atifStep.timestamp = timestamp;
    if (source === "agent" && modelName) atifStep.model_name = modelName;
    if (stepType === "thought" && body) atifStep.reasoning_content = body;
    if (stepType === "tool_call") {
      atifStep.tool_calls = [{
        tool_call_id: callId || `tool-${index + 1}`,
        function_name: stringValue(step.tool_name) || "unknown",
        arguments: atifArguments(step.tool_args),
      }];
      calls.set(callId || `tool-${index + 1}`, atifStep);
    }
    if (["tool_result", "error"].includes(stepType)) {
      const result: Record<string, Json> = {
        content: body,
        extra: callId ? { unresolved_source_call_id: callId } : {},
      };
      const subagentRef = callId ? subagentRefs.get(callId) : undefined;
      if (subagentRef) result.subagent_trajectory_ref = [subagentRef];
      atifStep.observation = { results: [result] };
    }
    const metrics = atifMetrics(step);
    if (metrics && source === "agent") {
      atifStep.metrics = metrics;
      atifStep.llm_call_count = 1;
    }
    converted.push(atifStep);
  }
  return converted;
}

function atifFinalMetrics(steps: Record<string, Json>[], totalSteps = steps.length): Record<string, Json> {
  return {
    total_prompt_tokens: steps.reduce((sum, step) => sum + numberValue(step.tokens_in), 0),
    total_completion_tokens: steps.reduce((sum, step) => sum + numberValue(step.tokens_out), 0),
    total_cost_usd: Number(steps.reduce((sum, step) => sum + numberValue(step.cost_usd), 0).toFixed(6)),
    total_steps: totalSteps,
  };
}

function claudeSessionIdentity(rows: Record<string, any>[], tracePath: string): { sessionId: string; version: string } {
  return {
    sessionId: mostFrequent(rows.map((row) => stringValue(row.sessionId) || stringValue(row.session_id)))
      || path.basename(tracePath, path.extname(tracePath)),
    version: mostFrequent(rows.map((row) => stringValue(row.version))) || "unknown",
  };
}

function claudeSubagentCallMap(rows: Record<string, any>[]): Map<string, { callId: string; summary: string }> {
  const mapped = new Map<string, { callId: string; summary: string }>();
  for (const row of rows) {
    const message = asPlainObject(row.message);
    const blocks = Array.isArray(message?.content) ? message.content : [];
    for (const rawBlock of blocks) {
      const block = asPlainObject(rawBlock);
      if (!block || stringValue(block.type) !== "tool_result") continue;
      const callId = stringValue(block.tool_use_id);
      if (!callId) continue;
      const result = asPlainObject(row.toolUseResult) || asPlainObject(row.tool_use_result);
      const text = bodyFromContent(block.content);
      const agentId = stringValue(result?.agentId)
        || stringValue(result?.agent_id)
        || /agentId:\s*([a-z0-9-]+)/i.exec(text)?.[1];
      if (!agentId) continue;
      mapped.set(agentId, {
        callId,
        summary: stringValue(result?.description) || text.slice(0, 500),
      });
    }
  }
  return mapped;
}

async function makeClaudeAtifBundle(
  tracePath: string,
  parentSteps: Record<string, Json>[],
): Promise<ClaudeAtifBundle | undefined> {
  const parentText = await fs.readFile(tracePath, "utf8");
  const parentRows = objectRowsFromJsonl(parentText);
  if (!claudeCodeEventLike(parentRows)) return undefined;

  const parentIdentity = claudeSessionIdentity(parentRows, tracePath);
  const subagentDir = path.join(path.dirname(tracePath), path.basename(tracePath, path.extname(tracePath)), "subagents");
  const callMap = claudeSubagentCallMap(parentRows);
  const subagentTrajectories: Record<string, Json>[] = [];
  const subagentPaths: string[] = [];
  const subagentRefs = new Map<string, Record<string, Json>>();
  let entries: Dirent[] = [];
  try {
    entries = await fs.readdir(subagentDir, { withFileTypes: true });
  } catch {
    // Claude Code creates this directory only when the main session delegated work.
  }

  for (const entry of entries) {
    if (!entry.isFile() || !entry.name.toLowerCase().endsWith(".jsonl")) continue;
    const agentId = /^agent-(.+)\.jsonl$/i.exec(entry.name)?.[1];
    const call = agentId ? callMap.get(agentId) : undefined;
    if (!agentId || !call) continue;
    const childPath = path.join(subagentDir, entry.name);
    const childText = await fs.readFile(childPath, "utf8");
    const childRows = objectRowsFromJsonl(childText);
    const childSteps = parseTraceSteps(childText, entry.name);
    if (!claudeCodeEventLike(childRows) || !childSteps.length) continue;
    const childIdentity = claudeSessionIdentity(childRows, childPath);
    const trajectoryId = `claude-subagent-${agentId}`;
    const childModel = mostFrequent(childSteps.map((step) => stringValue(step.model_id))) || "unknown";
    const childAtifSteps = armStepsToAtif(childSteps);
    subagentTrajectories.push({
      schema_version: "ATIF-v1.7",
      session_id: childIdentity.sessionId || parentIdentity.sessionId,
      trajectory_id: trajectoryId,
      agent: {
        name: "claude-code-subagent",
        version: childIdentity.version,
        model_name: childModel,
        extra: { agent_id: agentId },
      },
      steps: childAtifSteps,
      final_metrics: atifFinalMetrics(childSteps, childAtifSteps.length),
      notes: "Claude Code delegated subagent trajectory linked from its parent Agent tool call.",
    });
    subagentPaths.push(childPath);
    subagentRefs.set(call.callId, {
      trajectory_id: trajectoryId,
      session_id: childIdentity.sessionId || parentIdentity.sessionId,
      extra: {
        agent_id: agentId,
        summary: call.summary,
      },
    });
  }

  const parentModel = mostFrequent(parentSteps.map((step) => stringValue(step.model_id))) || "unknown";
  const trajectoryId = `claude-main-${parentIdentity.sessionId}`;
  const parentAtifSteps = armStepsToAtif(parentSteps, subagentRefs);
  return {
    trajectory: {
      schema_version: "ATIF-v1.7",
      session_id: parentIdentity.sessionId,
      trajectory_id: trajectoryId,
      agent: {
        name: "claude-code",
        version: parentIdentity.version,
        model_name: parentModel,
      },
      steps: parentAtifSteps,
      final_metrics: atifFinalMetrics(parentSteps, parentAtifSteps.length),
      ...(subagentTrajectories.length ? { subagent_trajectories: subagentTrajectories as unknown as Json } : {}),
      notes: "Claude Code main trajectory. Delegated agents remain independent ATIF trajectories referenced from tool observations.",
      extra: {
        native_trace: path.basename(tracePath),
        subagent_count: subagentTrajectories.length,
        recursive_total_steps: parentAtifSteps.length + subagentTrajectories.reduce((sum, child) => {
          const metrics = asPlainObject(child.final_metrics);
          return sum + numberValue(metrics?.total_steps);
        }, 0),
      },
    },
    subagentPaths,
  };
}

async function detectNativeTrace(): Promise<DetectedTrace | undefined> {
  const configured = process.env.PLAYGROUND_TRACE;
  const candidates: DetectedTrace[] = [
    ...(configured ? [{ path: configured, harness: process.env.PLAYGROUND_HARNESS || "auto" }] : []),
    { path: "/logs/agent/opencode.txt", harness: "opencode" },
    { path: "/logs/agent/codex.txt", harness: "codex" },
    { path: "/logs/agent/claude-code.txt", harness: "claude-code" },
    { path: "/logs/agent/claude_code.txt", harness: "claude-code" },
    { path: "/logs/agent/claude.txt", harness: "claude-code" },
  ];
  const claudeProjects = path.join(os.homedir(), ".claude", "projects");
  if (await exists(claudeProjects)) {
    for (const file of await listFiles(claudeProjects)) {
      const relative = path.relative(claudeProjects, file).split(path.sep);
      if (path.extname(file) === ".jsonl" && !relative.includes("subagents")) {
        candidates.push({ path: file, harness: "claude-code" });
      }
    }
  }
  const present: Array<DetectedTrace & { mtimeMs: number }> = [];
  for (const candidate of candidates) {
    const resolved = path.resolve(candidate.path);
    try {
      const stat = await fs.stat(resolved);
      if (stat.isFile() && stat.size > 0) present.push({ ...candidate, path: resolved, mtimeMs: stat.mtimeMs });
    } catch {
      // Candidate is not present in this harness.
    }
  }
  present.sort((a, b) => b.mtimeMs - a.mtimeMs);
  return present[0];
}

async function ensureSubmissionTrace(opts: Record<string, OptValue>): Promise<void> {
  if (opt(opts, "trace")) return;
  const detected = await detectNativeTrace();
  if (!detected) {
    throw new CliError(
      "no agent trace was found automatically.\n" +
      "Agent: locate your own session .jsonl file, validate it, then submit it directly—no conversion is required.\n" +
      "Common locations: /logs/agent, the current workspace, ~/.codex/sessions, ~/.claude/projects, and your agent's session/log directory.\n" +
      "Useful search: find . /logs/agent ~/.codex/sessions ~/.claude/projects -type f -name '*.jsonl' 2>/dev/null\n" +
      "Then run:\n" +
      "  playground trace validate --trace PATH/TO/SESSION.jsonl\n" +
      "  playground submit --challenge-id ID --outputs outputs-dir --trace PATH/TO/SESSION.jsonl",
    );
  }
  opts.trace = detected.path;
  if (!opt(opts, "trace-format") && detected.harness !== "auto") opts["trace-format"] = detected.harness;
}

async function loadTraceSteps(opts: Record<string, OptValue>, outputFiles: string[]): Promise<Record<string, Json>[]> {
  const trace = opt(opts, "trace");
  if (!trace) throw new CliError("submission requires a native trace; pass --trace PATH");
  const tracePath = path.resolve(trace);
  const text = await fs.readFile(tracePath, "utf8");
  const parsedSteps = parseTraceSteps(text, path.basename(tracePath));
  if (parsedSteps.length) return parsedSteps;
  throw new CliError(`could not derive normalized trace steps from native trace ${tracePath}`);
}

async function writeRawMessages(stage: string, source: string): Promise<{ data: Buffer; path: string; redactions: number }> {
  const raw = await fs.readFile(source, "utf8");
  const redacted = redactTraceText(raw);
  const rows = objectRowsFromJsonl(redacted.text);
  const hasSessionStart = stringValue(rows[0]?.type) === "session_start";
  const envelope = hasSessionStart ? "" : `${JSON.stringify({ type: "session_start", source: "playground-cli-auto-detect" })}\n`;
  const data = Buffer.from(`${envelope}${redacted.text}${redacted.text.endsWith("\n") ? "" : "\n"}`, "utf8");
  const rootTarget = path.join(stage, "raw_messages.jsonl");
  const tracesTarget = path.join(stage, "traces", "raw_messages.jsonl");
  await fs.mkdir(path.dirname(tracesTarget), { recursive: true });
  await fs.writeFile(rootTarget, data);
  await fs.writeFile(tracesTarget, data);
  return { data, path: rootTarget, redactions: redacted.redactions };
}

async function traceCanServeAsRawMessages(tracePath: string): Promise<boolean> {
  const text = await fs.readFile(tracePath, "utf8");
  try {
    const parsed = JSON.parse(text);
    const obj = asPlainObject(parsed);
    if (Array.isArray(parsed) || (obj && Array.isArray(obj.steps))) return true;
  } catch {
    // JSONL traces are handled below.
  }
  const rows = objectRowsFromJsonl(text);
  return nativeTraceLike(rows)
    || opencodeEventLike(rows)
    || claudeCodeEventLike(rows)
    || rows.some((row) => row.role || row.source || row.content || row.text || row.message);
}

async function cmdTraceConvert(opts: Record<string, OptValue>): Promise<void> {
  const input = path.resolve(opt(opts, "trace") || opt(opts, "in") || required(opts, "input"));
  const out = path.resolve(opt(opts, "out") || "trace.jsonl");
  const text = await fs.readFile(input, "utf8");
  const steps = parseTraceSteps(text, path.basename(input));
  if (!steps.length) throw new CliError(`could not derive ARM trace steps from ${input}`);
  await fs.mkdir(path.dirname(out), { recursive: true });
  await fs.writeFile(out, `${steps.map((step) => JSON.stringify(step)).join("\n")}\n`);
  let rawOut: string | undefined;
  let redactions = 0;
  if (opt(opts, "raw-out")) {
    rawOut = path.resolve(required(opts, "raw-out"));
    const redacted = redactTraceText(text);
    redactions = redacted.redactions;
    await fs.mkdir(path.dirname(rawOut), { recursive: true });
    await fs.writeFile(rawOut, redacted.text);
  }
  console.log(JSON.stringify({
    status: "converted",
    input,
    out,
    raw_out: rawOut || null,
    raw_redactions: redactions,
    validation: validateTraceSteps(steps),
  }, null, 2));
}

async function cmdTraceValidate(opts: Record<string, OptValue>): Promise<void> {
  const input = path.resolve(opt(opts, "trace") || opt(opts, "in") || required(opts, "input"));
  const text = await fs.readFile(input, "utf8");
  const rows = objectRowsFromJsonl(text);
  const steps = parseTraceSteps(text, path.basename(input));
  const result = {
    path: input,
    format: "jsonl",
    jsonl_events: rows.length,
    usable_events: steps.length,
    valid: rows.length > 0 && steps.length > 0,
  };
  console.log(JSON.stringify(result, null, 2));
  if (!result.valid) {
    throw new CliError(`trace is not usable agent JSONL: ${input}`);
  }
}

async function makeArmBundle(opts: Record<string, OptValue>): Promise<BundleResult> {
  const outputs = path.resolve(required(opts, "outputs"));
  const challengeId = required(opts, "challenge-id");
  const createdAt = utcNow();
  const runId = opt(opts, "run-id") || `local-${createdAt.replace(/[-:]/g, "").toLowerCase()}-${createHash("sha1").update(`${challengeId}:${process.cwd()}:${Date.now()}`).digest("hex").slice(0, 8)}`;
  const inputsForSecretScan = [outputs, opt(opts, "report"), opt(opts, "log"), opt(opts, "trace")].filter(Boolean) as string[];
  if (!flag(opts, "allow-secrets")) {
    const secretHits = await scanForSecrets(inputsForSecretScan);
    if (secretHits.length > 0) {
      throw new CliError(`possible secrets found; refusing to package:\n${secretHits.slice(0, 20).map((hit) => `  - ${hit}`).join("\n")}`);
    }
  }

  const bundlePath = path.resolve(opt(opts, "bundle-out") || "playground-arm.zip");
  const tmp = await fs.mkdtemp(path.join(os.tmpdir(), "playground-cli-ts-"));
  const stage = path.join(tmp, "stage");
  try {
    await fs.mkdir(stage, { recursive: true });
    await copyPath(outputs, path.join(stage, "outputs"));
    await copyPath(outputs, path.join(stage, "results"));
    await copyPath(outputs, path.join(stage, "execution", "results"));
    if (opt(opts, "report")) await copyPath(path.resolve(required(opts, "report")), path.join(stage, "reproduction_report.md"));
    if (opt(opts, "log")) await copyPath(path.resolve(required(opts, "log")), path.join(stage, "logs"));
    const tracePath = opt(opts, "trace") ? path.resolve(required(opts, "trace")) : undefined;
    if (tracePath) await copyPath(tracePath, path.join(stage, "native_trace", path.basename(tracePath)));
    const rawMessagesSource = opt(opts, "raw-messages")
      ? path.resolve(required(opts, "raw-messages"))
      : tracePath && await traceCanServeAsRawMessages(tracePath)
        ? tracePath
        : undefined;
    const rawMessages = rawMessagesSource ? await writeRawMessages(stage, rawMessagesSource) : undefined;
    const skillEvidence = await collectSkillEvidence(opts, tracePath, stage);

    const outputFiles = (await listFiles(path.join(stage, "outputs"))).map((file) => path.relative(stage, file).replaceAll(path.sep, "/"));
    const traceSteps = await loadTraceSteps(opts, outputFiles);
    const identity = await submissionIdentity(opts, traceSteps);
    const claudeAtif = tracePath ? await makeClaudeAtifBundle(tracePath, traceSteps) : undefined;
    if (claudeAtif && !flag(opts, "allow-secrets")) {
      const secretHits = await scanForSecrets(claudeAtif.subagentPaths);
      if (secretHits.length > 0) {
        throw new CliError(`possible secrets found in Claude subagent traces; refusing to package:
${secretHits.slice(0, 20).map((hit) => `  - ${hit}`).join("\n")}`);
      }
    }
    if (claudeAtif) {
      for (const subagentPath of claudeAtif.subagentPaths) {
        await copyPath(subagentPath, path.join(stage, "native_trace", "subagents", path.basename(subagentPath)));
      }
    }
    const existingTimestamps = traceSteps.map((step) => timestampMillis(step.timestamp));
    const firstTimestampIndex = existingTimestamps.findIndex((millis) => millis !== undefined);
    const fallbackStart = firstTimestampIndex >= 0
      ? (existingTimestamps[firstTimestampIndex] as number) - firstTimestampIndex * 1000
      : Date.now();
    let previousTimestamp = 0;
    traceSteps.forEach((step, index) => {
      step.step_order = index + 1;
      let millis = timestampMillis(step.timestamp);
      if (millis === undefined) millis = fallbackStart + index * 1000;
      if (previousTimestamp && millis < previousTimestamp) millis = previousTimestamp + 1000;
      step.timestamp = isoNoMillis(millis);
      previousTimestamp = millis;
      if (!step.type && step.step_type) step.type = step.step_type;
      if (!step.step_type && step.type) step.step_type = step.type;
    });

    const artifacts = outputFiles.map((arc, index) => ({
      id: `artifact-${index + 1}`,
      path: arc.replace(/^outputs\//, "execution/results/"),
      kind: "output",
      type: "file",
      format: path.extname(arc).replace(/^\./, "") || "artifact",
    }));
    const manifest: Record<string, Json> = {
      arm_version: "1.1",
      paper: {
        title: challengeId,
        url: opt(opts, "task-url") || "",
      },
      entrypoint: "src/reproduce.py",
      environment: { dependencies: "requirements.txt" },
      execution: {
        ran_at: utcNow(),
        wall_time_s: 1,
        log_path: "execution/run.log",
        artifacts: artifacts as unknown as Json,
      },
      expected_outputs: outputFiles.map((arc, index) => ({
        name: path.basename(arc),
        path: arc,
        type: [".md", ".txt", ".json", ".csv"].includes(path.extname(arc).toLowerCase()) ? "text" : "artifact",
        comparison_method: "harbor_checker",
        produced_by: [`artifact-${index + 1}`],
      })) as unknown as Json,
      characterization: "characterization.json",
      trace: "traces/trace.jsonl",
      ...(claudeAtif ? { atif_trajectory: "traces/trajectory.json" } : {}),
      ...(rawMessages ? { raw_messages: "raw_messages.jsonl" } : {}),
      ...(skillEvidence.skills.length ? { skills: "skills/manifest.json" } : {}),
      provenance: {
        created_by: "@paper2arm/playground-cli",
        created_at: createdAt,
        challenge_id: challengeId,
        task_id: opt(opts, "task-id") || challengeId,
        run_id: runId,
        model: identity.model,
        harness: identity.harness,
        declared_model: identity.declaredModel || "",
        declared_harness: identity.declaredHarness || "",
        detected_model: identity.detectedModel || "",
        detected_harness: identity.detectedHarness || "",
        model_source: identity.declaredModel ? "declared" : identity.detectedModel ? "detected" : "fallback",
        harness_source: identity.declaredHarness ? "declared" : identity.detectedHarness ? "detected" : "fallback",
      },
    };
    const submission: Record<string, Json> = {
      schema_version: "playground-submission/v0",
      task_id: opt(opts, "task-id") || challengeId,
      challenge_id: challengeId,
      run_id: runId,
      created_at: createdAt,
      task_url: opt(opts, "task-url") || "",
      agent: {
        name: opt(opts, "agent-name") || "playground-cli",
        version: opt(opts, "agent-version") || VERSION,
        model: identity.model,
      },
      harness: {
        name: identity.harness,
        native_trace_format: opt(opts, "trace-format") || (tracePath ? "auto" : "arm"),
      },
      ...(skillEvidence.skills.length ? {
        skills: {
          manifest: "skills/manifest.json",
          count: skillEvidence.skills.length,
          names: skillEvidence.skills.map((skill) => skill.name),
        },
      } : {}),
      artifacts: [] as unknown as Json,
      privacy: {
        redaction: "playground-cli-secret-scan-v0",
        contains_raw_credentials: false,
      },
    };
    const characterization: Record<string, Json> = {
      envelope: {
        challenge_id: challengeId,
        task_id: opt(opts, "task-id") || challengeId,
        run_id: runId,
        status: "submitted",
        note: "Generated by @paper2arm/playground-cli. Final scoring is delegated to Playground/Harbor.",
      },
      failure_modes: [
        {
          name: "independent_characterization_pending",
          status: "pending",
          mitigation: "Evaluate with the Playground rubric or Harbor checker.",
        },
      ],
    };
    const runLog = [
      `Packaged Playground submission for ${challengeId}.`,
      `Outputs: ${outputFiles.join(", ") || "(none)"}`,
      "Generated by @paper2arm/playground-cli.",
      "",
    ].join("\n");
    const submissionArtifacts: Record<string, Json>[] = [];
    for (const arc of outputFiles) {
      submissionArtifacts.push({
        path: arc,
        sha256: await sha256File(path.join(stage, arc)),
      });
    }
    if (await exists(path.join(stage, "reproduction_report.md"))) {
      submissionArtifacts.push({
        path: "reproduction_report.md",
        sha256: await sha256File(path.join(stage, "reproduction_report.md")),
      });
    }
    if (skillEvidence.skills.length) {
      submissionArtifacts.push({
        path: "skills/manifest.json",
        sha256: await sha256File(path.join(stage, "skills", "manifest.json")),
      });
      for (const skill of skillEvidence.skills) {
        for (const file of skill.files) submissionArtifacts.push({ path: file.path, sha256: file.sha256 });
      }
    }
    submission.artifacts = submissionArtifacts as unknown as Json;
    await writeJsonFile(path.join(stage, "submission.json"), submission);
    await writeJsonFile(path.join(stage, "arm_manifest.json"), manifest);
    await writeJsonFile(path.join(stage, "characterization.json"), characterization);
    await fs.mkdir(path.join(stage, "execution"), { recursive: true });
    await fs.writeFile(path.join(stage, "execution", "run.log"), runLog);
    await fs.mkdir(path.join(stage, "logs"), { recursive: true });
    await fs.writeFile(path.join(stage, "logs", "run.log"), runLog);
    await fs.mkdir(path.join(stage, "traces"), { recursive: true });
    await fs.writeFile(path.join(stage, "traces", "trace.jsonl"), `${traceSteps.map((step) => JSON.stringify(step)).join("\n")}\n`);
    if (claudeAtif) await writeJsonFile(path.join(stage, "traces", "trajectory.json"), claudeAtif.trajectory);
    await fs.writeFile(path.join(stage, "README.md"), `# Playground submission\n\nChallenge: \`${challengeId}\`\n`);
    await fs.writeFile(path.join(stage, "Dockerfile"), "FROM python:3.11-slim\nWORKDIR /workspace\n");
    await fs.writeFile(path.join(stage, "requirements.txt"), "");
    await fs.mkdir(path.join(stage, "src"), { recursive: true });
    await fs.writeFile(
      path.join(stage, "src", "reproduce.py"),
      "from pathlib import Path\nPath('outputs').mkdir(exist_ok=True)\nprint('Playground bundle contains submitted outputs.')\n",
    );
    await zipDirectory(stage, bundlePath);
    return {
      bundlePath,
      manifest,
      traceSteps,
      rawMessagesData: rawMessages?.data,
      rawMessagesFilename: rawMessages ? "raw_messages.jsonl" : undefined,
    };
  } finally {
    await fs.rm(tmp, { recursive: true, force: true });
  }
}

// The create endpoint requires trajectory before a submitted attempt can exist.
// A multipart FILE bypasses Werkzeug's 500 KB ordinary-field limit; it still
// obeys the creation endpoint's overall request-body limit. Never truncate it.
async function submissionRawMessages(
  opts: Record<string, OptValue>,
  traceSteps: Record<string, Json>[],
  builtRaw?: Buffer,
): Promise<Buffer> {
  if (builtRaw) return builtRaw;
  const source = opt(opts, "raw-messages") || opt(opts, "trace");
  let text: string;
  if (source) {
    text = redactTraceText(await fs.readFile(path.resolve(source), "utf8")).text;
    if (!parseTraceSteps(text, path.basename(source)).length) {
      throw new CliError("创建提交记录需要非空、可解析的轨迹；请提供有效的 --trace 或 --raw-messages。");
    }
  } else if (traceSteps.length) {
    text = traceSteps.map((step) => JSON.stringify(step)).join("\n");
  } else {
    throw new CliError("使用 --bundle 创建新提交时，请同时提供 --trace 或 --raw-messages；重试已有提交可使用 --attempt-id。");
  }
  const hasSessionStart = stringValue(objectRowsFromJsonl(text)[0]?.type) === "session_start";
  const envelope = hasSessionStart ? "" : `${JSON.stringify({ type: "session_start", source: "playground-cli" })}\n`;
  return Buffer.from(`${envelope}${text}${text.endsWith("\n") ? "" : "\n"}`, "utf8");
}

async function cmdSubmit(opts: Record<string, OptValue>): Promise<void> {
  const config = await loadConfig(opts);
  const playOpts = { ...opts, target: "play" };
  const workerOpts = { ...opts, target: "worker" };
  const base = apiBase(playOpts, config);
  const token = bearerToken(playOpts, config);
  const workerBase = apiBase(workerOpts, config);
  // Normal users authenticate to Worker with their Playground token. A separate
  // Worker token remains supported only for operator recovery workflows.
  const workerAuthToken = bearerToken(workerOpts, config) || token;
  const challengeId = required(opts, "challenge-id");
  let bundlePath = opt(opts, "bundle") ? path.resolve(required(opts, "bundle")) : "";
  let manifest: Record<string, Json> = {};
  let traceSteps: Record<string, Json>[] = [];
  let rawMessagesData: Buffer | undefined;
  if (!bundlePath) {
    await ensureSubmissionTrace(opts);
    const built = await makeArmBundle(opts);
    bundlePath = built.bundlePath;
    manifest = built.manifest;
    traceSteps = built.traceSteps;
    rawMessagesData = built.rawMessagesData;
  } else {
    manifest = opt(opts, "manifest") ? await readJsonFile<Record<string, Json>>(path.resolve(required(opts, "manifest"))) : {};
    const suppliedTrace = opt(opts, "trace") || opt(opts, "raw-messages");
    traceSteps = suppliedTrace ? await loadTraceSteps({ ...opts, trace: suppliedTrace }, []) : [];
  }
  const bundleSha256 = await sha256File(bundlePath);
  const bundleBytes = (await fs.stat(bundlePath)).size;
  if (bundleBytes > WORKER_MAX_UPLOAD_BYTES) {
    throw new CliError(
      `提交包为 ${(bundleBytes / 1024 / 1024).toFixed(1)} MiB，超过 worker 当前支持的 512 MiB。请精简后重试，或在群里联系维护者。`,
    );
  }
  const identity = await submissionIdentity(opts, traceSteps);
  let attemptId = opt(opts, "attempt-id") || "";
  if (!attemptId) rawMessagesData = await submissionRawMessages(opts, traceSteps, rawMessagesData);
  if (flag(opts, "dry-run")) {
    console.log(JSON.stringify({ status: "dry_run", bundle: bundlePath, bundle_sha256: bundleSha256, manifest, trace_steps: traceSteps }, null, 2));
    return;
  }
  // Keep ordinary fields small. Send complete trajectory as a file below.
  const attemptFields: Record<string, string> = {
    method: opt(opts, "method") || "Playground CLI submission",
    model: identity.model,
    harness: identity.harness,
    type: "agent",
    status: "submitted",
    detail: opt(opts, "detail") || `Submitted by @paper2arm/playground-cli ${VERSION}.`,
    manifest_json: JSON.stringify(manifest),
    trace: "[]",
    author_name: opt(opts, "author-name") || "Playground CLI",
  };
  const declaredOutcome = opt(opts, "outcome");
  if (declaredOutcome) attemptFields.outcome = declaredOutcome;
  let attempt: Record<string, Json> = {};
  if (!attemptId) {
    try {
      attempt = await postMultipartJson<Record<string, Json>>(
        `${base}/challenges/${encodeURIComponent(challengeId)}/attempts`,
        attemptFields,
        [{ name: "raw_messages", filename: "raw_messages.jsonl",
          contentType: "application/x-ndjson", data: rawMessagesData! }],
        token,
      );
    } catch (error) {
      throw cleanSubmissionError(error, "attempt-create");
    }
    attemptId = String(attempt.id);
    if (!attemptId || attemptId === "undefined") {
      throw new CliError("未能创建提交记录，请稍后再试；若持续失败，请在群里联系维护者。");
    }
  }

  let bundleResponse: Record<string, Json>;
  const bundleData = await fs.readFile(bundlePath);
  try {
    bundleResponse = await retryWorkerUpload(() => postMultipartJson<Record<string, Json>>(
      `${workerBase}/uploads`,
      { attempt_id: attemptId, challenge_id: challengeId, playground_token: token || "" },
      [{
        name: "bundle",
        filename: path.basename(bundlePath),
        contentType: "application/zip",
        data: bundleData,
      }],
      workerAuthToken,
    ));
  } catch (error) {
    throw cleanSubmissionError(error, "worker-upload", attemptId, bundlePath);
  }
  console.log(JSON.stringify({
    schema_version: "playground-cli-submission/v0",
    status: "submitted",
    target: targetName(opts, config),
    api_base: base,
    worker_api_base: workerBase,
    challenge_id: challengeId,
    attempt_id: attemptId,
    attempt_url: `${publicBaseFromApi(base)}/#challenge/${challengeId}`,
    bundle: bundlePath,
    bundle_sha256: bundleSha256,
    attempt,
    bundle_response: bundleResponse,
  }, null, 2));
}

async function retryWorkerUpload<T>(upload: () => Promise<T>): Promise<T> {
  let lastError: unknown;
  for (const delayMs of [0, 1000, 3000]) {
    if (delayMs) await new Promise((resolve) => setTimeout(resolve, delayMs));
    try {
      return await upload();
    } catch (error) {
      lastError = error;
      const detail = error instanceof Error ? error.message : String(error);
      if (/HTTP 4\d\d/i.test(detail) && !/HTTP 408|HTTP 429/i.test(detail)) throw error;
    }
  }
  throw lastError;
}

function cleanSubmissionError(error: unknown, stage: "attempt-create" | "worker-upload", attemptId?: string, bundlePath?: string): CliError {
  const detail = error instanceof Error ? error.message : String(error);
  let reason = "未能发送成功，请稍后再试";
  if (/HTTP 401|HTTP 403/i.test(detail)) {
    reason = "认证失败，请先运行 playground auth login 后重试";
  } else if (/HTTP 413|too large|payload.*large/i.test(detail)) {
    reason = stage === "attempt-create"
      ? "创建提交记录失败（HTTP 413）：轨迹文件或创建请求超过创建接口的请求体限制，请联系维护者确认该接口限制"
      : "Worker 上传失败（HTTP 413）：提交包超过 worker 当前支持的 512 MiB，请精简后重试";
  } else if (/HTTP 429/i.test(detail) && /Submission limit reached|at most\s+\d+\s+submissions/i.test(detail)) {
    reason = "该题已达到 10 次提交上限；如需赛后回归或研究，请联系维护者开启赛后练习/测试通道";
  } else if (/HTTP 429/i.test(detail)) {
    reason = "服务端当前限流或提交过于频繁，请稍后再试";
  } else if (/HTTP 400|invalid|bad request/i.test(detail)) {
    reason = stage === "attempt-create"
      ? (/trajectory data/i.test(detail)
        ? "创建提交记录失败：服务端未收到有效轨迹，请检查 --trace 或 --raw-messages"
        : "创建提交记录未通过校验，请检查提交元数据和轨迹文件")
      : "Worker 上传的提交包未通过校验，请检查 bundle 内容后重试";
  } else if (/ENOTFOUND|ECONNREFUSED|ECONNRESET|ETIMEDOUT|fetch failed|network/i.test(detail)) {
    reason = stage === "attempt-create" ? "未能连接创建接口，请稍后再试" : "未能连接 worker，请稍后再试";
  }
  const retry = attemptId && bundlePath
    ? ` 可重试：playground submit --challenge-id <原任务ID> --attempt-id ${attemptId} --bundle ${JSON.stringify(bundlePath)}`
    : "";
  return new CliError(`${reason}。${retry} 若持续失败，请在群里联系维护者。`);
}

async function cmdStatus(opts: Record<string, OptValue>): Promise<void> {
  const config = await loadConfig(opts);
  const base = apiBase(opts, config);
  const token = bearerToken(opts, config);
  const attemptId = required(opts, "attempt-id");
  const suffix = flag(opts, "bundle") ? "bundle/status" : "";
  const url = `${base}/attempts/${encodeURIComponent(attemptId)}${suffix ? `/${suffix}` : ""}`;
  const attempt = await requestJson<Record<string, any>>(url, {}, token);
  let generatedSkill: Record<string, any> = { status: "unavailable" };
  try {
    generatedSkill = await fetchGeneratedSkillStatus(opts, config, attemptId);
  } catch (error) {
    generatedSkill = {
      status: "unavailable",
      warning: error instanceof Error ? error.message : String(error),
    };
  }
  const nextActions = generatedSkill.status === "ready" ? {
    download: `playground skill download --attempt-id ${attemptId} --out ./skills`,
    share: `playground skill share --attempt-id ${attemptId} --out ./skills`,
  } : {};
  console.log(JSON.stringify({
    ...attempt,
    generated_skill: { ...generatedSkill, next_actions: nextActions },
  }, null, 2));
}

function workerSkillHeaders(playgroundToken: string | undefined, workerAccessToken: string | undefined): Headers {
  const headers = new Headers({ Accept: "application/json" });
  if (workerAccessToken) headers.set("Authorization", `Bearer ${workerAccessToken}`);
  if (playgroundToken) headers.set("X-Playground-Token", playgroundToken);
  return headers;
}

async function fetchGeneratedSkillStatus(
  opts: Record<string, OptValue>, config: Record<string, Json>, attemptId: string,
): Promise<Record<string, any>> {
  const playToken = bearerToken({ ...opts, target: "play" }, config);
  if (!playToken) return { status: "authentication_required" };
  const workerBase = apiBase({ ...opts, target: "worker" }, config);
  return requestJson<Record<string, any>>(
    `${workerBase}/attempts/${encodeURIComponent(attemptId)}/generated-skill/status`,
    { headers: workerSkillHeaders(playToken, workerToken(opts, config)) },
  );
}

async function downloadGeneratedSkill(
  opts: Record<string, OptValue>, config: Record<string, Json>, attemptId: string,
  state: Record<string, any>, requestedOut?: string,
): Promise<{ path: string; content: string; name: string; sha256: string }> {
  const playToken = bearerToken({ ...opts, target: "play" }, config);
  if (!playToken) throw new CliError("a Playground login is required to download generated skills");
  const workerBase = apiBase({ ...opts, target: "worker" }, config);
  const response = await fetch(
    `${workerBase}/attempts/${encodeURIComponent(attemptId)}/generated-skill/download`,
    { headers: workerSkillHeaders(playToken, workerToken(opts, config)) },
  );
  const data = Buffer.from(await response.arrayBuffer());
  if (!response.ok) throw new CliError(`HTTP ${response.status} ${response.statusText}: ${data.toString("utf8")}`);
  const name = String(state.name || `attempt-${attemptId}-expert`).replace(/[^a-z0-9-]/g, "-");
  const root = path.resolve(requestedOut || path.join(process.cwd(), "skills"));
  const destination = path.basename(root) === "SKILL.md" ? root : path.join(root, name, "SKILL.md");
  await fs.mkdir(path.dirname(destination), { recursive: true });
  await fs.writeFile(destination, data, { mode: 0o644 });
  const sha256 = createHash("sha256").update(data).digest("hex");
  if (state.sha256 && sha256 !== state.sha256) {
    await fs.unlink(destination).catch(() => undefined);
    throw new CliError("downloaded skill failed SHA-256 verification");
  }
  return { path: destination, content: data.toString("utf8"), name, sha256 };
}

async function publishGeneratedSkill(
  opts: Record<string, OptValue>, config: Record<string, Json>,
  skill: { content: string; name: string; sha256: string }, state: Record<string, any>,
): Promise<Record<string, any>> {
  const base = apiBase({ ...opts, target: "play" }, config);
  const playToken = bearerToken({ ...opts, target: "play" }, config);
  if (!playToken) throw new CliError("a Playground login is required to share skills");
  const frontmatter = skill.content.match(/^---\s*\n([\s\S]*?)\n---/);
  const description = String(state.description || frontmatter?.[1]?.match(/^description:\s*(.+)$/m)?.[1] || "").replace(/^['"]|['"]$/g, "");
  if (!description) throw new CliError("generated skill has no publishable description");
  const publish = (name: string) => requestJson<Record<string, any>>(`${base}/skills`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: `/${name}`, type: "atomic", icon: "🧠", desc: description, domain: [], spec: skill.content }),
  }, playToken);
  try {
    return await publish(skill.name);
  } catch (error) {
    if (!(error instanceof CliError) || !error.message.startsWith("HTTP 409 ")) throw error;
    return publish(`${skill.name}-${skill.sha256.slice(0, 8)}`);
  }
}

async function cmdSkillStatus(opts: Record<string, OptValue>): Promise<void> {
  const config = await loadConfig(opts);
  console.log(JSON.stringify(await fetchGeneratedSkillStatus(opts, config, required(opts, "attempt-id")), null, 2));
}

async function cmdSkillDownload(opts: Record<string, OptValue>): Promise<void> {
  const config = await loadConfig(opts);
  const attemptId = required(opts, "attempt-id");
  const state = await fetchGeneratedSkillStatus(opts, config, attemptId);
  if (state.status !== "ready") throw new CliError(`generated skill is not ready (status=${state.status || "unknown"})`);
  const result = await downloadGeneratedSkill(opts, config, attemptId, state, opt(opts, "out"));
  console.log(JSON.stringify({ status: "downloaded", attempt_id: attemptId, path: result.path, sha256: result.sha256 }, null, 2));
}

async function cmdSkillShare(opts: Record<string, OptValue>): Promise<void> {
  const config = await loadConfig(opts);
  const attemptId = required(opts, "attempt-id");
  const state = await fetchGeneratedSkillStatus(opts, config, attemptId);
  if (state.status !== "ready") throw new CliError(`generated skill is not ready (status=${state.status || "unknown"})`);
  const downloaded = await downloadGeneratedSkill(opts, config, attemptId, state, opt(opts, "out"));
  const published = await publishGeneratedSkill(opts, config, downloaded, state);
  console.log(JSON.stringify({ status: "shared", attempt_id: attemptId, local_path: downloaded.path, skill: published }, null, 2));
}

async function cmdResultUpdate(opts: Record<string, OptValue>): Promise<void> {
  const config = await loadConfig(opts);
  const base = apiBase(opts, config);
  const token = bearerToken(opts, config);
  const attemptId = required(opts, "attempt-id");
  const payload: Record<string, Json> = {
    score: Number(required(opts, "score")),
    status: opt(opts, "status") || "scored",
    outcome: opt(opts, "outcome") || "scored",
    summary: opt(opts, "summary") || "Harbor evaluation completed.",
    evaluatedAt: utcNow(),
  };
  if (opt(opts, "results-json")) {
    payload.resultsJson = await readJsonFile(path.resolve(required(opts, "results-json"))) as unknown as Json;
  }
  console.log(JSON.stringify(await requestJson(
    `${base}/attempts/${encodeURIComponent(attemptId)}/result`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    token,
  ), null, 2));
}

function asRecord(value: unknown): Record<string, any> | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, any> : undefined;
}

function finiteNumber(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const n = Number(value);
    if (Number.isFinite(n)) return n;
  }
  return undefined;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function findHarborResultFiles(root: string): Promise<string[]> {
  if (!(await exists(root))) return [];
  return (await listFiles(root)).filter((file) => path.basename(file) === "result.json");
}

function rewardFromJobResult(result: Record<string, any>): { reward?: number; errors?: number; evalName?: string } {
  const stats = asRecord(result.stats);
  if (!stats) return {};
  const errors = finiteNumber(stats.n_errors);
  const evals = asRecord(stats.evals);
  if (!evals) return { errors };
  for (const [evalName, rawEval] of Object.entries(evals)) {
    const evalRow = asRecord(rawEval);
    if (!evalRow) continue;
    const metrics = Array.isArray(evalRow.metrics) ? evalRow.metrics : [];
    for (const metric of metrics) {
      const mean = finiteNumber(asRecord(metric)?.mean);
      if (mean !== undefined) return { reward: mean, errors, evalName };
    }
    const rewardStats = asRecord(asRecord(evalRow.reward_stats)?.reward);
    if (rewardStats) {
      const values = Object.keys(rewardStats).map((key) => finiteNumber(key)).filter((n): n is number => n !== undefined);
      if (values.length) return { reward: Math.max(...values), errors, evalName };
    }
  }
  return { errors };
}

function rewardFromTrialResult(result: Record<string, any>): { reward?: number; errors?: number } {
  const reward = finiteNumber(asRecord(asRecord(result.verifier_result)?.rewards)?.reward);
  const errors = result.exception_info ? 1 : 0;
  return { reward, errors };
}

async function collectHarborScore(opts: Record<string, OptValue>): Promise<{
  reward: number;
  errors: number;
  jobResult?: string;
  trialResult?: string;
  evalName?: string;
}> {
  let jobResult = opt(opts, "harbor-result");
  let trialResult = opt(opts, "trial-result");
  const evalRoot = opt(opts, "eval-root");
  if (evalRoot && (!jobResult || !trialResult)) {
    const files = await findHarborResultFiles(path.resolve(evalRoot));
    for (const file of files) {
      const data = await readJsonFile<Record<string, any>>(file);
      if (!jobResult && asRecord(data.stats)?.evals) jobResult = file;
      if (!trialResult && asRecord(data.verifier_result)) trialResult = file;
    }
  }

  let reward: number | undefined;
  let errors = 0;
  let evalName: string | undefined;
  if (jobResult) {
    const data = await readJsonFile<Record<string, any>>(path.resolve(jobResult));
    const extracted = rewardFromJobResult(data);
    reward = extracted.reward ?? reward;
    errors = extracted.errors ?? errors;
    evalName = extracted.evalName;
  }
  if (reward === undefined && trialResult) {
    const data = await readJsonFile<Record<string, any>>(path.resolve(trialResult));
    const extracted = rewardFromTrialResult(data);
    reward = extracted.reward;
    errors = extracted.errors ?? errors;
  }
  if (reward === undefined) {
    throw new CliError("Harbor result is not ready or did not contain a numeric reward");
  }
  return {
    reward,
    errors,
    jobResult: jobResult ? path.resolve(jobResult) : undefined,
    trialResult: trialResult ? path.resolve(trialResult) : undefined,
    evalName,
  };
}

async function cmdResultPoll(opts: Record<string, OptValue>): Promise<void> {
  const config = await loadConfig(opts);
  const base = apiBase(opts, config);
  const token = bearerToken(opts, config);
  const attemptId = required(opts, "attempt-id");
  const scoreMultiplier = Number(opt(opts, "score-multiplier") || "100");
  if (!Number.isFinite(scoreMultiplier)) throw new CliError("--score-multiplier must be numeric");
  const watch = flag(opts, "watch");
  const intervalMs = Number(opt(opts, "interval-ms") || "5000");
  const timeoutMs = Number(opt(opts, "timeout-ms") || (watch ? "1800000" : "0"));
  const deadline = timeoutMs > 0 ? Date.now() + timeoutMs : 0;

  let collected: Awaited<ReturnType<typeof collectHarborScore>> | undefined;
  for (;;) {
    try {
      collected = await collectHarborScore(opts);
      break;
    } catch (error) {
      if (!watch || (deadline && Date.now() >= deadline)) throw error;
      await sleep(intervalMs);
    }
  }
  const score = Number((collected.reward * scoreMultiplier).toFixed(6));
  const summary = opt(opts, "summary") ||
    `Harbor evaluation completed. Reward ${collected.reward}; Playground score ${score}.`;
  const payload: Record<string, Json> = {
    score,
    status: opt(opts, "status") || "scored",
    outcome: opt(opts, "outcome") || "scored",
    summary,
    evaluatedAt: utcNow(),
    resultsJson: {
      harbor_reward: collected.reward,
      score_percent: score,
      harbor_errors: collected.errors,
      eval_name: collected.evalName || null,
      harbor_job_result: collected.jobResult || null,
      harbor_trial_result: collected.trialResult || null,
    },
    scorecard: {
      harbor_replay_executed: 1,
      verifier_errors: collected.errors,
      reward: collected.reward,
    },
    execStatus: collected.errors > 0 ? "completed_with_errors" : "completed",
  };
  if (flag(opts, "dry-run")) {
    console.log(JSON.stringify({
      status: "dry_run",
      attempt_id: attemptId,
      target: targetName(opts, config),
      api_base: base,
      payload,
    }, null, 2));
    return;
  }
  console.log(JSON.stringify(await requestJson(
    `${base}/attempts/${encodeURIComponent(attemptId)}/result`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    token,
  ), null, 2));
}

function makeCrcTable(): number[] {
  const table: number[] = [];
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c >>> 0;
  }
  return table;
}

const CRC_TABLE = makeCrcTable();

function crc32(data: Buffer): number {
  let c = 0xffffffff;
  for (const byte of data) c = CRC_TABLE[(c ^ byte) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function u16(value: number): Buffer {
  const buf = Buffer.alloc(2);
  buf.writeUInt16LE(value & 0xffff, 0);
  return buf;
}

function u32(value: number): Buffer {
  const buf = Buffer.alloc(4);
  buf.writeUInt32LE(value >>> 0, 0);
  return buf;
}

async function zipDirectory(root: string, output: string): Promise<void> {
  const files = await listFiles(root);
  const localParts: Buffer[] = [];
  const centralParts: Buffer[] = [];
  let offset = 0;
  for (const file of files) {
    const rel = path.relative(root, file).replaceAll(path.sep, "/");
    const name = Buffer.from(rel, "utf8");
    const data = await fs.readFile(file);
    const crc = crc32(data);
    const local = Buffer.concat([
      u32(0x04034b50),
      u16(20),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(crc),
      u32(data.length),
      u32(data.length),
      u16(name.length),
      u16(0),
      name,
      data,
    ]);
    localParts.push(local);
    const central = Buffer.concat([
      u32(0x02014b50),
      u16(20),
      u16(20),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(crc),
      u32(data.length),
      u32(data.length),
      u16(name.length),
      u16(0),
      u16(0),
      u16(0),
      u16(0),
      u32(0o100644 << 16),
      u32(offset),
      name,
    ]);
    centralParts.push(central);
    offset += local.length;
  }
  const central = Buffer.concat(centralParts);
  const end = Buffer.concat([
    u32(0x06054b50),
    u16(0),
    u16(0),
    u16(files.length),
    u16(files.length),
    u32(central.length),
    u32(offset),
    u16(0),
  ]);
  await fs.mkdir(path.dirname(output), { recursive: true });
  await fs.writeFile(output, Buffer.concat([...localParts, central, end]));
}

function printHelp(): void {
  console.log(`Playground CLI ${VERSION}

Usage:
  playground <command> [options]
  playground -h | --help
  playground <command> -h | --help

Recommended contest flow:
  # New user (a strong password is generated and saved automatically):
  playground auth register --name "YOUR NAME" --email EMAIL --affiliation ORGANIZATION
  # Returning user:
  playground auth login --email EMAIL
  # Confirm that saved credentials work:
  playground auth status
  playground task list --limit 20
  playground task download --challenge-id ID --out challenge-dir
  playground submit --challenge-id ID --outputs outputs-dir --trace native-trace --model MODEL --harness HARNESS
  playground status --attempt-id ID --bundle

Command groups:
  config      Write local endpoint and token configuration
  auth        Login, register, and check saved credentials
  agent       Register an agent identity and request an operator claim
  task        Guide, preflight, package, list, download, or upload Playground tasks
  benchmark   Upload ready challenge packages as one Playground benchmark
  data        List, inspect, or pull Wenyon datasets
  trace       Validate agent JSONL traces before submission
  harbor      Convert a Harbor task directory into a Playground task package
  submit      Package outputs plus trace evidence and create an attempt
  status      Check attempt or bundle status
  skill       Check, download, or share a generated high-score skill
  doctor      Check local helper dependencies
  result      Operator-only score update/poll helpers

Examples:
  playground config init --api-base ${DEFAULT_PLAY_API}
  playground agent claim --name "My Agent" --email agent@example.com --operator @alice --framework Codex
  playground task list --limit 20 --json
  playground data pull --dataset DATASET --version VERSION --out data-dir/
  playground submit --challenge-id ID --outputs outputs-dir --trace PATH/TO/SESSION.jsonl
  playground skill download --attempt-id ID --out ./skills
  playground skill share --attempt-id ID --out ./skills

Run 'playground <command> -h' for command-specific options.

Important environment variables:
  PLAYGROUND_TOKEN          Optional override; auth commands save this automatically
  PLAYGROUND_PASSWORD       Optional password override for register; required by login unless saved
  PLAYGROUND_AGENT_PASSWORD Optional password for agent claim; generated securely when unset
  PLAYGROUND_CREDENTIALS_PATH  Read credentials from a non-default file
  PLAYGROUND_API_BASE       Optional override for the built-in Playground API
  PLAYGROUND_WORKER_API_BASE  Worker base override for task upload-package
  PLAYGROUND_MODEL          Optional self-reported model (same as --model)
  PLAYGROUND_HARNESS        Optional self-reported harness (same as --harness)
  PLAYGROUND_TRACE          Optional agent JSONL path; submit checks /logs/agent first
  PLAYGROUND_BOHR_BIN       Bohrium CLI path. Default: bohr
  PLAYGROUND_WENYON_BIN     Legacy standalone Wenyon override (compatibility only)
`);
}

const COMMAND_HELP: Record<string, string> = {
  config: `Playground CLI ${VERSION}

Usage:
  playground config init [options]

Commands:
  init   Write ~/.playground/config.json with Playground defaults.

Run 'playground config init -h' for init options.`,

  "config init": `Playground CLI ${VERSION}

Usage:
  playground config init [--api-base ${DEFAULT_PLAY_API}] [--config FILE]

Writes a local config file. Most contestants can skip this because the CLI
already defaults to ${DEFAULT_PLAY_API}.

Options:
  --api-base URL              Playground API/root URL. Default: ${DEFAULT_PLAY_API}
  --config FILE               Config path. Default: ${DEFAULT_CONFIG_PATH}
  --bohr-bin PATH              Bohrium CLI path. Default: bohr
  --wenyon-bin PATH            Legacy standalone Wenyon override`,

  auth: `Playground CLI ${VERSION}

Usage:
  playground auth login --email EMAIL [--password-env PLAYGROUND_PASSWORD]
  playground auth register --name NAME --email EMAIL [--affiliation TEXT] [--password-env NAME]
  playground auth status

Registration generates a strong password when no password environment variable is set.
Credentials and the generated password are saved to ${DEFAULT_CREDENTIALS_PATH} with 0600 permissions.`,

  "auth login": `Playground CLI ${VERSION}

Usage:
  playground auth login --email EMAIL [--password-env PLAYGROUND_PASSWORD] [--api-base URL]

Logs in and saves PLAYGROUND_TOKEN for later commands.

Options:
  --email EMAIL               Account email.
  --password-env NAME         Env var that contains the password. Default: PLAYGROUND_PASSWORD
  --api-base URL              Override the Playground endpoint for this command.`,

  "auth register": `Playground CLI ${VERSION}

Usage:
  playground auth register --name NAME --email EMAIL [--affiliation TEXT] [--password-env NAME]

Registers an account and saves the returned token. If the password environment
variable is unset, generates a strong random password and saves it for future login.

Options:
  --name NAME                 Display name.
  --email EMAIL               Account email.
  --affiliation TEXT          Organization or team label.
  --password-env NAME         Optional env var containing a chosen password.
                              Default: PLAYGROUND_PASSWORD; random when unset.`,

  "auth status": `Playground CLI ${VERSION}

Usage:
  playground auth status [--api-base URL]

Checks whether the saved or environment token can reach Playground.`,

  agent: `Playground CLI ${VERSION}

Usage:
  playground agent claim --name NAME --email EMAIL --operator @USER [--framework NAME]
  playground agent register --name NAME --email EMAIL --operator @USER [--framework NAME]

Self-registers an agent and requests a pending operator binding. The human
operator must confirm the claim in Playground before attribution is active.`,

  "agent claim": `Playground CLI ${VERSION}

Usage:
  playground agent claim --name NAME --email EMAIL --operator @USER [options]

Registers an agent account and declares an exact human Playground user as its
operator. A leading @ is accepted and removed before the request. Agent
credentials are saved separately and never overwrite the active human account.
If the agent email already exists, the CLI can log in with the existing password
or inspect --credentials-out to report whether that account is already pending
or confirmed for the requested operator. Current Playground APIs cannot create a
new pending claim for an existing agent account through CLI-only calls.

Options:
  --name NAME                 Agent display name.
  --email EMAIL               Agent account email.
  --operator @USER            Exact Playground human user id.
  --framework NAME            Agent framework. Default: Custom
  --persona-id ID             Optional existing Playground persona.
  --password-env NAME         Env var containing a chosen password.
                              Default: PLAYGROUND_AGENT_PASSWORD; random when unset.
  --credentials-out FILE      Separate credential file destination.
  --force                     Replace an existing destination credential file.
  --dry-run                   Validate the operator and show the safe request without registering.

Use the returned credential file with:
  PLAYGROUND_CREDENTIALS_PATH=/path/to/agent.env playground auth status`,

  "agent register": `Playground CLI ${VERSION}

Alias for 'playground agent claim'. Run 'playground agent claim -h' for options.`,

  harbor: `Playground CLI ${VERSION}

Usage:
  playground harbor convert --harbor-task DIR --out challenge-dir [options]

Converts a Harbor task directory into a Playground challenge package.`,

  "harbor convert": `Playground CLI ${VERSION}

Usage:
  playground harbor convert --harbor-task DIR --out challenge-dir [--title TEXT] [--challenge-id ID] [--dataset DATASET:VERSION] [--expected-output PATH:DESC]

Creates challenge.json, task.md, rubric.md, config.json, and
playground_manifest.json from a Harbor task directory.`,

  trace: `Playground CLI ${VERSION}

Usage:
  playground trace validate --trace trace.jsonl

Validate an agent session JSONL and submit that same file directly with
--trace. No trace conversion is required.`,

  "trace validate": `Playground CLI ${VERSION}

Usage:
  playground trace validate --trace trace.jsonl

Checks whether the agent JSONL contains usable trace events before submission.
Submit the same file directly with --trace; no conversion is required.`,

  task: `Playground CLI ${VERSION}

Usage:
  playground task guide [--path]
  playground task preflight --task-dir DIR [--strict] [--json]
  playground task package --task-dir DIR --out task.zip [--strict]
  playground task upload-package --task-dir DIR [--strict] [--visibility private|public]
  playground task list [--limit 30] [--tag harbor] [--json]
  playground task download --challenge-id ID --out challenge-dir [--skip-datasets]
  playground task upload --challenge-dir challenge-dir

Authoring preflight and packaging are local. upload-package sends the complete package
to the verified Worker endpoint; task upload remains the legacy challenge upload flow.
Use 'playground task <subcommand> -h' for details.`,

  "task guide": `Playground CLI ${VERSION}

Usage:
  playground task guide [--path]

Prints the shipped Paper2ARM/Harbor authoring guide. --path prints its installed path.`,

  "task preflight": `Playground CLI ${VERSION}

Usage:
  playground task preflight --task-dir DIR [--strict] [--json]

Read-only mechanical validation before submission. Reports deterministic inventory,
trust classification, bounded format/contract checks, and obvious leak patterns without
printing hidden file contents or values. Errors fail; --strict also fails on warnings.`,

  "task package": `Playground CLI ${VERSION}

Usage:
  playground task package --task-dir DIR --out TASK.zip [--strict]

Runs preflight and creates a deterministic complete-task ZIP plus .manifest.json.
Hidden files are included for Worker grading and classified in the manifest. No network
request is made because Worker complete-package ingestion is not yet verified.`,

  "task list": `Playground CLI ${VERSION}

Usage:
  playground task list [--limit 30] [--tag TAG] [--json] [--api-base URL]

Lists visible Playground tasks.

Options:
  --limit N                   Number of rows to print. Default: 30
  --tag TAG                   Filter by tag. Can be repeated or comma-separated.
  --json                      Print machine-readable JSON.`,

  "task download": `Playground CLI ${VERSION}

Usage:
  playground task download --challenge-id ID --out challenge-dir [--skip-datasets]

Downloads task metadata, instructions, config, and pinned Wenyon datasets. Model metadata is retained but models are not downloaded.
Numeric --challenge-id values are resolved as 1-based indexes from task list.`,

  "task upload": `Playground CLI ${VERSION}

Usage:
  playground task upload --challenge-dir challenge-dir [--visibility public|private]

Uploads a local challenge package to Playground.

Options:
  --visibility VALUE          Override challenge.json visibility (public or private).
                              If omitted, challenge.json or the server default is used.`,

  "task upload-package": `Playground CLI ${VERSION}

Usage:
  playground task upload-package --task-dir DIR [--strict] [--visibility private|public]
  playground task upload-package --package ZIP [--visibility private|public]

Preflights and deterministically packages a complete Harbor task, then streams it
to the verified Worker task-package endpoint. Existing ZIPs are streamed unchanged.

Options:
  --task-dir DIR              Complete task directory to preflight and package.
  --package ZIP               Previously generated complete package; mutually exclusive with --task-dir.
  --strict                    Treat preflight warnings as failures.
  --visibility VALUE          private (default) or public.
  --idempotency-key KEY       Explicit 8-128 character retry key.
  --worker-api-base URL       Command-specific Worker base override (http or https).
  --dry-run                   Print endpoint, SHA-256, bytes, key, and visibility; do not connect.

Authentication uses the normal Playground login token, never PLAYGROUND_WORKER_TOKEN.
The compressed package limit is 128 MiB.`,

  benchmark: `Playground CLI ${VERSION}

Usage:
  playground benchmark upload --name NAME --challenge-root DIR [options]
  playground benchmark upload --benchmark-slug SLUG --challenge-dir DIR [--challenge-dir DIR ...]

Creates or resumes a benchmark upload. Existing tasks are skipped by
sourceQuestionId (falling back to challenge id), so reruns are safe.`,

  "benchmark upload": `Playground CLI ${VERSION}

Usage:
  playground benchmark upload --name NAME [--slug SLUG] --challenge-root DIR [options]
  playground benchmark upload --benchmark-slug SLUG --challenge-dir DIR [--challenge-dir DIR ...]

Options:
  --name NAME                 Create a benchmark with this display name.
  --slug SLUG                 Preferred slug when creating a benchmark.
  --benchmark-slug SLUG       Resume an existing benchmark instead of creating one.
  --challenge-root DIR        Add every immediate child containing challenge.json.
  --challenge-dir DIR         Add one ready package; may be repeated.
  --description TEXT          Benchmark description when creating.
  --grading-model MODEL       Optional default grading model.
  --visibility VALUE          public or private. Default: private.

Each package must contain challenge.json and a rubric (in challenge.json or
rubric.md). task.md and rubric.md override their corresponding JSON fields.`,

  data: `Playground CLI ${VERSION}

Usage:
  playground data list [--include-hidden]
  playground data get --dataset DATASET
  playground data pull --dataset DATASET --version VERSION [--prefix PREFIX] [--paths P1,P2] [--out data-dir/]

Dataset commands use Bohrium's managed Wenyon companion through bohr wenyon.
Authenticate with bohr auth login (local) or bohr auth login --device (remote).`,

  "data list": `Playground CLI ${VERSION}

Usage:
  playground data list [--include-hidden] [--bohr-bin PATH]

Runs bohr wenyon dataset list. Wenyon currently provides table output for this command.`,

  "data get": `Playground CLI ${VERSION}

Usage:
  playground data get --dataset DATASET
  playground data get --name DATASET

Shows metadata for one prepared dataset.`,

  "data pull": `Playground CLI ${VERSION}

Usage:
  playground data pull --dataset DATASET --version VERSION [--prefix PREFIX] [--paths P1,P2] [--out data-dir/]

Downloads an explicitly pinned immutable dataset version. --prefix filters by path prefix; --paths selects exact comma-separated paths.`,

  submit: `Playground CLI ${VERSION}

Usage:
  playground submit --challenge-id ID --outputs outputs-dir [--trace native-trace] [--raw-messages raw.jsonl] [--model MODEL] [--harness HARNESS] [--bundle-out playground-arm.zip] [--dry-run]
  playground submit --challenge-id ID --attempt-id ID --bundle playground-arm.zip --trace native-trace

For a new attempt, sends the full trace as a raw_messages FILE during creation;
ordinary trace fields stay small. Creation has its own request-body limit.
With --bundle, pass --trace or --raw-messages when creating a new attempt.
Packages outputs, logs, trace evidence, metadata, and raw messages,
creates a Playground attempt, and uploads the submission bundle.

Common options:
  --challenge-id ID           Playground task id.
  --attempt-id ID             Retry a failed worker upload without creating a duplicate attempt.
  --bundle PATH               Upload an existing ARM bundle, including for a retry.
  --outputs DIR               Directory containing final answer files.
  --trace PATH                Agent session JSONL. If omitted, /logs/agent is scanned.
  --skill PATH                Include a skill directory or SKILL.md. Can be repeated.
  --skill-root DIR            Extra root for resolving skill names found in the trace.
  --no-auto-skills            Disable skill inference from the selected trace.
  --model MODEL               Self-reported model, also available as PLAYGROUND_MODEL.
  --harness HARNESS           Self-reported harness, also available as PLAYGROUND_HARNESS.
  --dry-run                   Build and validate the bundle without submitting.`,

  status: `Playground CLI ${VERSION}

Usage:
  playground status --attempt-id ID [--bundle]

Read-only, non-interactive status query. A ready generated skill includes explicit
next_actions commands; download and sharing only occur through playground skill.`,
  skill: `Playground CLI ${VERSION}

Usage:
  playground skill status --attempt-id ID
  playground skill download --attempt-id ID [--out ./skills]
  playground skill share --attempt-id ID [--out ./skills]

High-score skills are generated asynchronously after a total score above 90.
Download verifies SHA-256. Share publishes SKILL.md to https://play.bohrium.com/#tools.`,

  doctor: `Playground CLI ${VERSION}

Usage:
  playground doctor [--install-wenyon] [--bohr-bin PATH] [--quiet]

Checks Node and Wenyon using bohr wenyon --help. With --install-wenyon, the CLI runs
bohr update to converge the Bohrium-managed companion; it never starts login automatically.`,

  "update-check": `Playground CLI ${VERSION}

Usage:
  playground update-check

Checks the controlled install site for a newer CLI version.`,

  result: `Playground CLI ${VERSION}

Usage:
  playground result update --attempt-id ID --score SCORE [--status scored]
  playground result poll --attempt-id ID --eval-root DIR [--watch]

Operator-only helpers for evaluator workers.`,

  "result update": `Playground CLI ${VERSION}

Usage:
  playground result update --attempt-id ID --score SCORE [--status scored] [--outcome scored] [--summary TEXT] [--results-json FILE]

Posts an explicit score payload to an attempt.`,

  "result poll": `Playground CLI ${VERSION}

Usage:
  playground result poll --attempt-id ID --eval-root DIR [--watch] [--interval-ms 5000] [--timeout-ms 1800000]

Polls local Harbor result.json files and posts the derived score when ready.`,
};

function normalizeHelpKey(key: string): string {
  const normalized = key.trim().replace(/\s+/g, " ");
  if (normalized.startsWith("dataset ")) return `data ${normalized.slice("dataset ".length)}`;
  if (normalized === "dataset") return "data";
  if (normalized === "data download") return "data pull";
  if (normalized === "dataset download") return "data pull";
  return normalized;
}

function printCommandHelp(key: string): boolean {
  const help = COMMAND_HELP[normalizeHelpKey(key)];
  if (!help) return false;
  console.log(`${help.trimEnd()}\n`);
  return true;
}

async function main(): Promise<void> {
  await loadSavedCredentials();
  await migrateDefaultConfig();
  const { commands, opts } = parseArgs(process.argv.slice(2));
  const localConfig = await loadConfig(opts);
  if (!opt(opts, "bohr-bin") && !opt(opts, "wenyon-bin")
      && !process.env.PLAYGROUND_BOHR_BIN && !process.env.PLAYGROUND_WENYON_BIN) {
    const configuredBohr = stringValue(localConfig.bohrBin);
    const configuredLegacyWenyon = stringValue(localConfig.wenyonBin);
    if (configuredBohr) opts["bohr-bin"] = configuredBohr;
    else if (configuredLegacyWenyon) opts["wenyon-bin"] = configuredLegacyWenyon;
  }
  if (flag(opts, "version") || commands[0] === "version") {
    console.log(VERSION);
    return;
  }
  if (commands.length === 0) {
    printHelp();
    return;
  }
  const key = commands.join(" ");
  if (commands[0] === "help") {
    const helpKey = commands.slice(1).join(" ");
    if (!helpKey) {
      printHelp();
      return;
    }
    if (printCommandHelp(helpKey)) return;
    throw new CliError(`unknown help topic: ${helpKey}`);
  }
  if (flag(opts, "help")) {
    if (printCommandHelp(key)) return;
    throw new CliError(`unknown help topic: ${key}`);
  }
  if (key === "update-check") return printUpdateStatus(true);
  await maybePrintUpdateNotice();
  if (key === "config init") return cmdConfigInit(opts);
  if (key === "auth login") return cmdAuthLogin(opts);
  if (key === "auth register") return cmdAuthRegister(opts);
  if (key === "auth status") return cmdAuthStatus(opts);
  if (key === "agent claim" || key === "agent register") return cmdAgentClaim(opts);
  if (key === "harbor convert") return cmdHarborConvert(opts);
  if (key === "trace convert") return cmdTraceConvert(opts);
  if (key === "trace validate") return cmdTraceValidate(opts);
  if (key === "task guide") return cmdTaskGuide(opts);
  if (key === "task preflight") return cmdTaskPreflight(opts);
  if (key === "task package") return cmdTaskPackage(opts);
  if (key === "task upload-package") return cmdTaskUploadPackage(opts);
  if (key === "task upload") return cmdTaskUpload(opts);
  if (key === "benchmark upload") return cmdBenchmarkUpload(opts);
  if (key === "task list") return cmdTaskList(opts);
  if (key === "task download") return cmdTaskDownload(opts);
  if (key === "data list" || key === "dataset list") return cmdDataList(opts);
  if (key === "data get" || key === "dataset get") return cmdDataGet(opts);
  if (key === "data pull" || key === "data download" || key === "dataset pull" || key === "dataset download") return cmdDataPull(opts);
  if (key === "submit") return cmdSubmit(opts);
  if (key === "status") return cmdStatus(opts);
  if (key === "skill status") return cmdSkillStatus(opts);
  if (key === "skill download") return cmdSkillDownload(opts);
  if (key === "skill share") return cmdSkillShare(opts);
  if (key === "doctor") return cmdDoctor(opts);
  if (key === "result update") return cmdResultUpdate(opts);
  if (key === "result poll") return cmdResultPoll(opts);
  throw new CliError(`unknown command: ${commands.join(" ")}`);
}

main().catch((error: unknown) => {
  const err = error instanceof CliError ? error : new CliError(error instanceof Error ? error.message : String(error));
  console.error(`error: ${err.message}`);
  process.exit(err.exitCode);
});
