# DSP Git Sync

An open-source Steam launch/exit bridge for Dyson Sphere Program saves, blueprints, and BepInEx mods, using a **private Git repository** for binary delta transport.

Implementation in progress. Source code belongs in this public repository; game data, binaries from the game or third-party mods, credentials, machine configuration and backup files do not.

Target platforms: Windows Steam and macOS Steam through CrossOver. Python 3.10+ and Git required. One device at a time. No Git LFS: the data server must accept large ordinary Git blobs and support delta packing at their size.

License: MIT.
