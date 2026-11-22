#!/usr/bin/env sh
# onboarding-atlas web installer. Downloads a tagged release from GitHub and runs install.sh. No sudo.
#
#   curl -fsSL https://raw.githubusercontent.com/Vikas070/onboarding-atlas/v1.0.0/get.sh | sh -s -- /path/to/project --claude
#
# Environment:
#   OA_REPO     GitHub "owner/name"                         (default below)
#   OA_REF      tag or branch to install                    (default: v1.0.0, pin a tag!)
#   OA_SHA256   expected sha256 of the downloaded tarball   (recommended: fails if it does not match)
#   OA_TARBALL_URL  override the download URL (testing / mirrors)
# Prefer to read before you run: download get.sh, open it, then `sh get.sh`.
set -eu

OA_REPO="${OA_REPO:-Vikas070/onboarding-atlas}"
OA_REF="${OA_REF:-v1.0.0}"
URL="${OA_TARBALL_URL:-https://github.com/$OA_REPO/archive/refs/tags/$OA_REF.tar.gz}"

command -v tar >/dev/null 2>&1 || { echo "tar is required" >&2; exit 1; }
TMP="$(mktemp -d 2>/dev/null || mktemp -d -t oa)"
trap 'rm -rf "$TMP"' EXIT INT TERM

echo "downloading $URL"
if command -v curl >/dev/null 2>&1; then curl -fsSL "$URL" -o "$TMP/oa.tgz"
elif command -v wget >/dev/null 2>&1; then wget -q "$URL" -O "$TMP/oa.tgz"
else echo "curl or wget is required" >&2; exit 1; fi

if [ -n "${OA_SHA256:-}" ]; then
  if command -v sha256sum >/dev/null 2>&1; then GOT="$(sha256sum "$TMP/oa.tgz" | cut -d' ' -f1)"
  else GOT="$(shasum -a 256 "$TMP/oa.tgz" | cut -d' ' -f1)"; fi
  [ "$GOT" = "$OA_SHA256" ] || { echo "checksum mismatch (got $GOT); aborting" >&2; exit 1; }
  echo "checksum OK"
else
  echo "note: OA_SHA256 not set, download not verified" >&2
fi

tar -xzf "$TMP/oa.tgz" -C "$TMP"
SRC="$(find "$TMP" -maxdepth 2 -name install.sh -print | head -n 1)"
[ -n "$SRC" ] || { echo "install.sh not found in archive" >&2; exit 1; }
sh "$SRC" "$@"
