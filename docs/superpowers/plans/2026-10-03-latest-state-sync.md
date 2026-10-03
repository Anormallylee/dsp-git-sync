# Latest-state synchronization implementation plan

> For agentic workers: use superpowers:subagent-driven-development with TDD and independent review.

**Goal:** Catch up to the latest save state without transferring intermediate save blobs.

**Architecture:** Metadata-only filtered fetch preserves ancestry. Validated latest-tree object IDs select the content to retrieve; cached objects are reused. Existing apply/publish protection remains intact.

**Tech stack:** Python standard library, Git 2.50+, unittest; real filtered file transport with uploadpack.allowFilter for tests.

## Chunk 1: Transport and validation

### Task 1: Implement latest-state download

Files: modify `git_sync.py`, `README.md`; create `tests/test_partial_fetch.py`.

- [ ] Add a real Git regression test creating baseline A, intermediate B, latest C unique binary blobs in a temporary bare origin with filtering enabled. An existing receiver at A fetches C. Assert B remains absent using a no-lazy-fetch object check after fetch, materialization, subsequent normal push, confirmation fetch and maintenance; ancestry A..C is valid and C materializes. Cover fresh cache and conversion of an existing full baseline cache. Run and observe failure before code changes.
- [ ] Add tests for fresh initialization and receive/publish round trip, latest checksum tamper rejection, and mandatory unsupported filtering behavior using a real Git origin with uploadpack.allowFilter=false. No mock-only proof of transfer efficiency.
- [ ] Configure dedicated cache as promisor; use `fetch --filter=blob:none` for network metadata without pruning ancestry. Preflight protocol-v2 fetch filter capability BEFORE the fetch (private packet trace captured in memory with no credential logging; reject missing filter capability). Checking a warning after fetch is too late because Git can silently ignore the filter and transfer full history.
- [ ] Separate tree enumeration from file-size lookups (`ls-tree` without `-l`) so the manifest operation cannot lazily retrieve all historical or latest data. Bound/control manifest and attributes retrieval; validate declared path/mode/set and actual size/hash when content is fetched.
- [ ] Identify missing latest-tree blobs with lazy fetching explicitly disabled. Batch explicit missing object retrieval using supported Git fetch or checkout bulk-prefetch; prove no intermediate blob retrieval. Keep lazy fetching disabled for ordinary archive/validation after prefetch so unplanned object requests fail visibly. Avoid one network request per data file and no request of unrelated history. Retain latest object length validation.
- [ ] Explicit blob fetching uses selected blob OIDs only, no revision ranges. Reject a server refusal safely. Verify a harmless latest metadata blob fetch works against the actual GitLab in an isolated cache before installing. Validate complete tree path/mode set before large-file retrieval; enforce manifest/attributes byte limits before parsing.
- [ ] Confirm normal push and recovery can operate with a promisor cache without requiring intermediate blobs. Keep remote history rewriting refused.
- [ ] Document latest-only file retrieval and residual network/timeout limitations without claiming exact byte predictions. Keep time limits unchanged.
- [ ] Run new tests and full `python -X utf8 -m unittest discover -s tests -v`.
- [ ] Commit changes to the isolated feature branch using local-only identity if necessary; no push.

## Chunk 2: Review and install

- [ ] Independent spec review followed by independent code quality review; address material findings.
- [ ] Root verifies full suite and hash correspondence; inspect no active session.
- [ ] Back up `C:/DSP-Git-Sync`; install changed runtime sources and tests while preserving config, bridge.ini, SteamSync.exe, cache, state and saves.
- [ ] Verify installed tests or matching hashes and package portable source/patch plus concise Mac installation instructions under outputs. Do not claim Mac installed.
