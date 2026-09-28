#!/bin/sh
set -eu
cd "$(dirname "$0")"
${CC:-x86_64-w64-mingw32-gcc} -Os -municode -static -o SteamSync.exe native/wrapper.c -lole32
