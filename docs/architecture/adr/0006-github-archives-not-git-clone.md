# ADR-0006: Import GitHub repositories as one commit's archive, never a clone

- **Status:** Accepted
- **Date:** 2026-11-13

## Context

Importing a repository with `git clone` runs git on content an attacker controls: hooks
are not run on clone, but git has had a steady stream of clone-time vulnerabilities
(malicious submodules, symlinked `.git` paths, case-folding tricks), clones bring the
whole history, and a clone needs a git binary and a writable checkout on the worker.

## Decision

- Resolve the ref to a commit SHA through the REST API, then download GitHub's tarball
  for exactly that commit (`/repos/{repo}/tarball/{sha}`), streamed and capped at four
  times `MAX_UPLOAD_BYTES`.
- Follow the archive redirect only to GitHub's own archive host or the configured API
  host; the HTTP client follows nothing else.
- Unpack in memory with `sources/archive.py`, the same defensive reader as ZIP uploads,
  and store a normalized snapshot. Pull requests use the same path for the head commit,
  with changed files and patches from the pull request files endpoint.
- Private repositories need a token with read access to contents and pull requests,
  sealed per project. Requests go only to `GITHUB_API_URL`, checked against metadata and
  (unless allowed) private addresses.

## Consequences

**Good**
- No git binary, no hooks, no submodules, no history on the worker; one commit, pinned by
  SHA, so an import is reproducible.
- One unpacking path for uploads and repositories.
- Works with GitHub Enterprise and with the mock GitHub used by tests and the demo.

**Bad / caveats**
- Submodules and Git LFS content are not imported.
- GitHub only in 0.1.0; GitLab and other hosts are roadmap.
