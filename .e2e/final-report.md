# Autonomous Web E2E Test Report

## 1. Scope

- Base URL: `http://127.0.0.1:8002`
- Run ID: `20260917-002920-fix` (resumed from `20260916-220405`)
- Revision observed: `f9067dd` plus the deployed current worktree image
- Image: `nexora:latest`, `sha256:ff2a77189e432348e1fa9da8499bac63aa4f841f9510d684e7f69222df3b14fd`
- Window: `2026-09-16T14:04:05Z` – `2026-09-17T00:29:20Z`
- Browser/tool: authenticated `agent-browser` session, runtime UI and internal Session API observations
- Safety boundary: existing kvm2 VMs were not used for destructive create/delete/clone/migrate completion. Preview, validation, and one accidentally direct device/lifecycle path were restored and verified.

## 2. System Model

- Primary reachable routes explored: overview, hosts, host onboarding, host detail, VMs, VM detail/config/XML/snapshots, VM create, storage, media, media copy, networks, tasks, audit, account, UI preview, and the compatibility `/manage/.../config` route.
- Managed host: `kvm2`, status `ready`, `kvm2.soocoo.xyz:22`, `qemu:///system`.
- Authoritative inventory after refresh: 33 VMs, 4 storage pools, 70 storage volumes, 94 topology nodes, 87 topology edges.
- VM states observed: 13 running, 20 shut off, 0 paused.
- Important VM configuration states: CPU/memory, disk/CD-ROM, network, PCI/USB/shared directory, Watchdog/vsock/cache/maxphysaddr, NUMA, CPU Pinning, XML history/rollback.
- Authentication: login, logout, protected-route redirect, session-expiry reload redirect, and re-login were exercised. Only one administrator role is available.

## 3. Coverage Summary

```text
Features discovered: 40
Features tested: 38
Features passed: 13
Features partially covered: 23
Features failed: 0
Features blocked: 2

States discovered: 18
Transitions discovered: 15
Transitions tested: 14

Workflows generated: 15
Workflows executed: 13

CRUD lifecycles expected: 1
CRUD lifecycles tested: 0

Negative paths expected: 4
Negative paths tested: 3
```

The machine-readable source for these numbers is `.e2e/coverage.json`; its counts were checked against the Inventory, State Graph, and Workflow arrays.

## 4. Critical Workflows Tested

- `kvm2` discovery → host refresh task `22/22` → VM list/filter/node filter/pagination → VM detail → browser back/forward; final inventory remained 33 VMs.
- VM advanced configuration read path → CPU/memory/disk/network/peripheral/advanced sections → XML → empty snapshot/history state → history rollback confirmation gate.
- Advanced preview matrix: valid CPU, memory, NUMA, CPU Pinning, and advanced-device previews returned `200`; invalid vsock/NUMA/CPU Pinning/maxphysaddr combinations returned `422` without tasks.
- VM create blank-disk preview and platform-image preview returned complete Domain XML diffs; no create confirmation was executed.
- VM clone preview returned a target disk/MAC/XML diff; no clone confirmation was executed.
- Snapshot preview returned an internal-disk snapshot plan; no snapshot task was executed.
- Storage volume preview returned a 1 GiB qcow2 plan; no create confirmation was executed.
- Media scan completed `3/3`; a test-issued media credential was revoked and the UI returned to “创建访问凭据”. Invalid media-copy filename was blocked before a request.
- VNC and serial console connected on a running VM and were closed without sending input.
- Logout → protected `/hosts` → `/login` redirect → re-login → kvm2 reload succeeded.
- Existing `balloon-test-kvm2` was restored to shut off, autostart disabled, original name, original `vda` path, and no active task.
- Retest after the fix: the advanced form hydrated `itco/reset`; unchanged preview returned no-change `422`, and an unrelated vsock preview returned `200` without a watchdog deletion. Empty account submit stayed on the form with no POST.

## 5. Failures

### FAIL-001 — High — Resolved

Feature: `vm.config.advanced`; workflow: `workflow.vm.advanced-settings.preview.001`.

Historical reproduction: the current XML contains `watchdog model="itco" action="reset"`, but the advanced form rendered Watchdog unchecked and defaulted the model to `i6300esb`. A preview made with the untouched UI defaults returned `200` and its diff removed the existing watchdog. No apply request was sent. Evidence:

- `.e2e/evidence/screenshots/vm-config-advanced-existing-watchdog.png`
- `.e2e/evidence/network/FAIL-001-advanced-watchdog-preview.txt`

Fix and retest evidence:

- `.e2e/evidence/screenshots/vm-config-advanced-fixed.png`
- `.e2e/evidence/network/FAIL-001-advanced-watchdog-retest.txt`

The form now shows enabled `itco/reset`; an unchanged preview returns `422 proposed VM configuration has no changes`, and changing only vsock returns `200` without watchdog deletion or addition. This was preview-only; no apply request was sent.

### FAIL-002 — Medium — Resolved

Feature: `account.update`; workflow: `workflow.account.validation.001`.

Historical reproduction: submitting the account form with 当前密码 empty sent no request, but the Ant Design validation rejection was caught as a page error. The form was replaced by “页面数据加载失败 / 账户保存失败”; reopening the route was required to recover. Evidence:

- `.e2e/evidence/screenshots/account-empty-submit-error.png`
- `.e2e/evidence/network/FAIL-002-account-validation.txt`

Fix and retest evidence:

- `.e2e/evidence/screenshots/account-validation-fixed.png`
- `.e2e/evidence/network/FAIL-002-account-validation-retest.txt`

The field is now marked invalid, the account page remains mounted, and no POST request is sent. Successful password rotation remains outside this retest because the current password is not exposed to the test agent.

## 6. Coverage Gaps and Blocks

- No safe dedicated VM fixture was authorized, so real VM create → configure → snapshot → clone/delete → deleted-URL lifecycle remains unexecuted.
- VM configuration apply/refresh/revisit/rollback persistence was not run against existing VMs.
- Cross-host migration cannot be tested with only one managed host.
- Successful account update/password rotation was not repeated because the saved browser auth profile does not expose the current password to the test agent.
- Task cancellation and interrupted-task recovery need a safe in-flight/interrupted task fixture.
- Repeat destructive mutations and deleted-VM browser-back/URL behavior remain untested.
- Remote previews are slow: storage about 16 seconds, blank-disk VM about 60 seconds, platform-image VM about 60 seconds, clone about 80 seconds.

## 7. Source vs Runtime Differences

- Source-only page: `/initialize` (already-initialized runtime did not use it).
- Runtime-only features: none found.
- Compatibility route `/manage/hosts/{host_id}/vms/{vm_id}/config` loaded the same configuration page.
- `/vms/new` returned a 404 JSON response and is not in the source route map; the actual source/runtime create route is `/vms/create`.
- Expected error state `/hosts/{host_id}/confirm` rendered “节点不再等待 Host Key 确认” through the generic page-error surface.

## 8. Final State

`completed_with_gaps`

The main reachable UI and kvm2 auto-discovery path are working, including 33 automatically discovered VMs and the advanced-settings read/validation/preview paths. FAIL-001 and FAIL-002 are resolved and retested. The run remains `completed_with_gaps` because destructive persistence/lifecycle coverage is intentionally incomplete and task-control fixtures/credentials are unavailable.

Final-state evidence: `.e2e/evidence/network/final-state-20260917.txt`.

## 9. Fix Deployment and Retest

- Backend XML regression: `uv run pytest -q tests/xml/test_advanced_devices.py` → 7 passed; Ruff passed.
- Related backend Web regression: `uv run pytest -q tests/web/test_vms.py tests/web/test_auth_flow.py` → 12 passed, 2 existing datetime warnings.
- Frontend: typecheck passed; App test 17 passed; full frontend suite 26 passed; production build passed.
- Deployment: backup `/data/backups/nexora-20260917T002508Z.tar.gz`; current rollback tags include `nexora:rollback-fix-20260917T002133Z` and `nexora:rollback-watchdog-20260917T002501Z`; container healthy, `/live`/`/ready` 200, SQLite `quick_check` ok.
- Browser retest: account validation and advanced Watchdog hydration/preview passed with no console errors; no real VM configuration save/apply was sent.
