# Windows installation / upgrade

This package changes transport to ordinary Git. Keep game saves and mods private. Do not use the public source repository as your data remote.

1. Close the game and wait for any previous sync to finish. Back up the existing tool directory, config, saves and mods. Stop if a previous sync is still active.
2. Install Git for Windows and Python 3.10+ if absent. Configure access to the **private data repository** using Git Credential Manager / the OS credential store or SSH. Never place a token in the remote URL or config.json. Verify `git ls-remote <private-remote> refs/heads/sync-v1` works without an interactive prompt.
3. Clone `https://github.com/Anormallylee/dsp-git-sync.git` into a fixed local directory outside OneDrive, then download the matching release's standalone `SteamSync.exe` into that directory. No ZIP is required. A delivered raw tool folder can also be copied to the fixed directory. Preserve the old tool directory for rollback. Copy the old machine's data/game/backup paths to the new config.json, and set git_remote, git_branch, and optionally an absolute git executable path. Remove obsolete rclone/remote/cloud keys from the new config. Use config.example.json for the schema.
4. The Git backend uses a separate `backup/git-launcher-state` baseline. Do not copy the Mac baseline or initialize Windows as the source. After reviewing and backing up any Windows-only changes, run `py -3 launcher.py init-download`. This initial import uses the private Git branch as authoritative and backs up changed existing files. Later sessions use three-way reconciliation.
5. Run `py -3 configure_windows_steam.py`. Apply the printed launch option in Steam; preserve unrelated original game arguments.
6. Launch from Steam, verify pre-sync completes before the game opens, save and quit normally, and wait until the sync window says completed. Inspect logs/status in ipc/sessions. Failed upload or an unresolved transaction is not success.

The older OneDrive backend must not continue publishing from either device after the Git migration. The OneDrive desktop client may still be used to deliver the tool files, but it does not synchronize game data in this version.

## Recovery
A failed upload keeps local game files and pending state. A later Steam start can recover a push whose server confirmation was lost. If both devices changed the same save/mod group, automatic replacement stops. Do not force-push, delete state files, or discard pending markers to bypass a conflict. For a verified local unpublished session with unchanged remote, `py -3 launcher.py recover-upload` retries publication.

Do not blindly remove active.lock: inspect whether a worker/game process is active. An apply-journal.json requires transaction/backup inspection. Independent blueprints merge; same-name text blueprints retain a `.conflict-local-*` copy. Save files and their mod companions are treated as one conflict group.

Local backups and Git history grow over time. Cache repacking runs after verified sync when needed; this compacts objects but does not delete committed history. Do not purge history without a separate retention/migration procedure.
