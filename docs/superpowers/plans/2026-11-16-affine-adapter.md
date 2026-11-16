# AFFiNE Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver and push a locally verified AFFiNE adapter using lazycat-action@v1.

**Architecture:** The adapter owns runtime bootstrap, metadata and acceptance tests.
The executor handles tag selection, three-image delivery, state and publication.
Acceptance runs against delivered immutable images in the packaging buildscript.

**Tech Stack:** YAML, Python 3, Node.js, Docker, existing Go executor.

**Spec:** docs/superpowers/specs/2026-11-16-affine-adapter.md

## Global Constraints

- Package cloud.lazycat.app.affine; first upstream candidate 0.27.4; amd64.
- Do not migrate 0.25.7 data; isolate /lzcapp/var/affine.
- No changes to lazycat-action; no credentials or generated state fabricated.
- No real submission or production installation during local verification.
- Use the existing requested checkout; user authorized commit and push.

## Review Focus

- Rejected-review retries must use source_version for the upstream image.
- Docker failures/timeouts must clean up only adapter-owned resources.
- Test evidence must bind all image content, metadata and bootstrap files.
- Existing user config must survive domain/OIDC credential refresh.
- Dependency/tag changes or incomplete proof must block packaging.

### Task 1: Reproducible deployment and contract

**Files:** package.yml, lzc-manifest.yml, lzc-build.yml, lazycat-action.yml,
icon.png, content/bootstrap.cjs, scripts/contract.py, scripts/registry.py,
tests/test_contract.py, tests/bootstrap.test.cjs.

**Interfaces:** contract validates package/service bindings and recipe hash;
registry reads immutable platform/config identity; bootstrap merges only managed
domain/OIDC fields and runs upstream predeploy before exec of the server.

- [x] Write failing behavior tests for versions, three-image bindings, config
  preservation, malformed OIDC input and incomplete/changed runtime proof.
- [x] Run RED, implement minimal deployment and utilities, verify GREEN.
- [x] Validate metadata and compile/parse all scripts.

### Task 2: Real verification, workflow and delivery

**Files:** scripts/verify_runtime.py, scripts/verify_package.py,
scripts/verify_latest.py, scripts/upstream.py, tests/, .github/workflows/update.yml,
README.md, requirements-test.txt.

**Interfaces:** verify_runtime accepts immutable three-image identities and
produces proof only after real setup/login/workspace/document/blob/OIDC/restart
checks; verify_package binds that proof to final delivered images and recipe.

- [x] Add failure-first tests for proof integrity and cleanup boundaries.
- [x] Run bounded local three-service acceptance and a real local LPK build.
- [x] Verify a read-only upstream check, workflow syntax and Release behavior.
- [x] Obtain fresh-context review; resolve important findings and rerun tests.
- [ ] Commit, push, verify remote commit and read-only push workflow.
