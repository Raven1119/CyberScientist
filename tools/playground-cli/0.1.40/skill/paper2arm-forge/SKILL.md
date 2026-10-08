---
name: paper2arm-forge
description: Author, preflight, and package a canonical Paper2Task Harbor single-step task while preserving Agent-visible, trusted-runtime, and hidden-grading boundaries.
---

# Paper2Task / Harbor authoring guide

## Paper2Task / LBG standard

The canonical standard profile requires:

```text
TASK/
├── instruction.md
├── task.toml
├── environment/                 # may be empty
│   └── resources.yaml           # recommended when resources are supplied
└── tests/
    └── test.sh
```

`solution/` is optional in Harbor, but Paper2Task publication should include `solution/solve.sh` so an Oracle can establish the intended ceiling.

`task.toml` must contain non-empty `[task]`, `[environment]`, `[agent]`, and `[verifier]` sections. `[environment].docker_image` must name a fixed prebuilt image using an explicit non-`latest` tag or digest. The CLI applies bounded textual TOML table/key checks; it does not execute TOML or infer arbitrary semantics.

Do not include `environment/Dockerfile` or `environment/docker-compose.yaml`/`.yml` in this profile. There is no automatic top-level `environment/setup.sh` behavior: invoke any setup explicitly in the workflow rather than assuming Harbor runs it.

## Visibility boundary

- **public_agent_visible:** `instruction.md` and every file under `environment/**`.
- **trusted_runtime:** `task.toml`, `README.md`, and the full `task_spec.json` when present. These are runtime/authoring metadata, not ordinary public-download content.
- **hidden_grading:** `tests/**`, `solution/**`, `calibration/**`, and nonstandard root `paper/**`.

Runtime isolation must enforce this boundary. Reports inventory paths, classifications, sizes, and hashes, but never print hidden file contents or sensitive values. Packaging includes every full file for trusted ingestion; it does not create a public projection.

## Public instruction and resources

Write `instruction.md` as a standalone task brief. Clearly state goals, inputs, outputs, constraints, completion criteria, and the resource entry point. Exact Forge H2 headings are not required in the standard profile.

All `environment/**` content is visible to the Agent. When resources are provided, enumerate them in `environment/resources.yaml`. The supported mechanical checks intentionally cover only a conservative YAML subset: a top-level non-empty `resources` list and plain fields such as `name`, `path`, `url`, `description`, `credential_source`, or `credential_env`. Bundled `path` references must resolve beneath `environment/`. Credential source names and environment-variable declarations are allowed; credential literals, bearer tokens, and expiring signed URLs are errors. No YAML runtime dependency is added.

If the paper itself is intended as an Agent input, use the canonical path `environment/reference/paper.pdf` and enumerate it in `environment/resources.yaml`. A root `paper/` is nonstandard hidden material and fails preflight with migration guidance.

## Verifier and Oracle

`tests/**` and `solution/**` are hidden from the solving Agent. `tests/test.sh` must visibly write `/logs/verifier/reward.json` or `/logs/verifier/reward.txt`; preflight checks the script text but does not execute it. Use absolute paths. Run the Oracle and calibrate full, empty, malformed, hard-coded, and claim-ablated outputs before publication.

## Optional enhanced Forge profile

`task_spec.json` and `tests/verification_plan.json` are optional as a pair. If either appears without the other, preflight fails. When both appear, the reported profile is `standard+forge` and the existing enhanced checks are added: output-contract shape, provenance-value leak checks, non-empty claims/checks, and exact ordered Forge instruction sections. The standard profile reports `standard`.

The historical Forge archive described one authoring profile that required `environment/Dockerfile`. That requirement is superseded for current Paper2Task/LBG tasks: a Dockerfile is now an error, and the fixed prebuilt `task.toml` image is authoritative wherever the profiles conflict.

## Commands

```bash
playground task guide
playground task guide --path
playground task preflight --task-dir TASK
playground task preflight --task-dir TASK --strict --json
harbor run -p TASK -a oracle
playground task package --task-dir TASK --out TASK.zip --strict
playground task upload-package --task-dir TASK --strict --visibility private
playground task upload-package --package TASK.zip --visibility private
```

`preflight` is read-only, deterministic, bounded, and mechanical. Normal mode exits nonzero on errors; `--strict` also fails on warnings. It cannot certify scientific correctness or deep semantic non-leakage.

`task package` reruns preflight and writes a deterministic complete ZIP plus `TASK.zip.manifest.json`, including Agent-visible, trusted-runtime, and hidden-grading files. It remains local and makes no network request.

`task upload-package` is the verified complete-package ingestion path. With `--task-dir`, it reruns preflight and creates the deterministic archive in a secure temporary directory; with `--package`, it streams the supplied ZIP unchanged and never deletes it. It sends the normal Playground user bearer token and multipart fields `package`, `idempotency_key`, and `visibility` to exactly `${workerBase}/task-packages`, never `/uploads`, with no owner/user field. The compressed limit is 128 MiB. Default idempotency is stable for identical package bytes and visibility; retries are limited to network errors and HTTP 408/429/5xx. Use `--dry-run` to inspect endpoint, SHA-256, bytes, key, and visibility without a token or network request. Server-side revalidation remains authoritative.
