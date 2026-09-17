## 1. Password Policy

- [x] 1.1 Change the shared backend administrator password minimum to 8 characters while preserving the 1,024-character maximum and existing hash/authentication behavior.
- [x] 1.2 Update the React administrator account form's minimum-length rule and validation message to 8 characters.

## 2. Tests

- [x] 2.1 Add backend boundary coverage for rejecting 7 characters and accepting exactly 8 characters, including confirmation mismatch behavior.
- [x] 2.2 Add or update account-flow coverage so a valid password change still requires the current password and rotates Sessions as before.
- [x] 2.3 Run frontend typecheck/tests/build, backend targeted auth tests, Ruff, diff checks, and production dependency audit.

## 3. Documentation

- [x] 3.1 Record the password policy change and security trade-off in `SECURITY.md`.
- [x] 3.2 Update `PROJECT_STATUS.md`, `ROADMAP.md`, `TEST_STATUS.md`, and `CHANGELOG.md` with implementation and verification evidence.

## 4. Production Release

- [x] 4.1 Build the current worktree image, create a `/data` backup, and preserve a rollback image tag before replacing the running container.
- [x] 4.2 Start the new container and verify health, live/ready endpoints, SQLite integrity, non-root/non-privileged runtime, and that the current admin password remains unchanged until manually updated through the page.
