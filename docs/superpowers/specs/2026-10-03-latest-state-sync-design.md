# Latest-state synchronization

The user approved skipping intermediate binary save versions, not increasing timeout limits. Windows currently fetches all intervening blobs when catching up, despite requiring only the latest save state.

Use Git partial fetch (`blob:none`) to retain complete commit/tree ancestry while omitting intermediate file contents. Read and validate the latest manifest and tree without asking for sizes of missing data blobs. Before materializing, fetch only missing blobs reachable from the requested latest tree in batches; use cached baseline blobs whenever already present. Validate downloaded actual sizes, paths, attributes, and SHA-256 before applying. Preserve the existing three-way conflict detection, transaction backups, recovery markers, normal push, and remote-history rewrite checks. No destructive rewriting/pruning of the private remote. No changes to the user's local configuration or save files for deployment. Never silently fall back to a full-history download if filtering is unsupported.

Acceptance: real Git test with three changed binary snapshots proves the receiver obtains baseline/latest data as needed but never the intermediate unique blob; commit ancestry remains checkable; subsequent normal publish works; existing recovery/conflict/tamper tests pass. Failed retrieval must retain baseline/live files.

Deployment: review and test isolated source, back up installed tool, install changed runtime files/tests/docs, verify installed source hashes. No automatic game launch or server configuration change. Source remains available as a local branch and portable patch for the Mac; no remote publish without user authorization.
