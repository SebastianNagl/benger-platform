#!/bin/sh
# Bring ./node_modules in step with ./package-lock.json for the dev container.
#
# The dev compose file keeps node_modules in an anonymous volume, and Docker
# carries that volume over when the container is recreated from a rebuilt
# image, so a stale install (for example a Next.js release with known
# advisories) would otherwise keep running after the lockfile moved on.
# Dockerfile.dev stamps the lockfile hash into node_modules/.lockfile-sha256;
# when it no longer matches, the dependencies are installed afresh with npm ci
# in a staging directory and swapped in. Neither npm ci nor npm install can
# run in place, because overlays bind-mount packages inside node_modules and
# npm would try to delete those mounts.
#
# The staging directory has one fixed path that is cleared before every
# attempt and removed on exit, so a failed install (registry unreachable,
# container killed) leaves nothing behind across the restart loop that
# `restart: unless-stopped` produces. On failure node_modules is untouched.
#
# Run from the frontend directory. MOUNTINFO overrides /proc/self/mountinfo
# and TMPDIR the staging parent; both exist for the tests.

set -e

mountinfo=${MOUNTINFO:-/proc/self/mountinfo}
staging="${TMPDIR:-/tmp}/benger-node-modules-staging"
stamp=node_modules/.lockfile-sha256

[ -f package-lock.json ] || exit 0
wanted_lock=$(sha256sum package-lock.json | cut -d' ' -f1)
installed_lock=$(cat "$stamp" 2>/dev/null || true)
[ "$wanted_lock" = "$installed_lock" ] && exit 0

# True when $1 is listed as a mount point.
is_mount() {
    printf '%s\n' "$node_modules_mounts" |
        awk -v p="$1" '$0 == p { found = 1 } END { exit !found }'
}

# True when $1 is a mount point or contains one.
holds_mount() {
    printf '%s\n' "$node_modules_mounts" |
        awk -v p="$1" '$0 == p || index($0, p "/") == 1 { found = 1 } END { exit !found }'
}

# Delete everything under directory $1 except mount points and their parents.
clear_except_mounts() {
    for entry in "$1"/* "$1"/.[!.]* "$1"/..?*; do
        [ -e "$entry" ] || [ -L "$entry" ] || continue
        if ! holds_mount "$entry"; then
            rm -rf "$entry"
        elif [ -d "$entry" ] && ! is_mount "$entry"; then
            clear_except_mounts "$entry"
        fi
    done
}

echo "node_modules does not match package-lock.json, reinstalling dependencies..."
trap 'rm -rf "$staging"' EXIT
rm -rf "$staging"
mkdir -p "$staging"
cp package.json package-lock.json "$staging"/
if [ -f .npmrc ]; then cp .npmrc "$staging"/; fi
(cd "$staging" && npm ci --no-audit --no-fund)

mkdir -p node_modules
node_modules_mounts=$(awk -v dir="$PWD/node_modules" \
    'index($5, dir "/") == 1 { print "node_modules" substr($5, length(dir) + 1) }' \
    "$mountinfo")
clear_except_mounts node_modules
cp -a "$staging"/node_modules/. node_modules/
echo "$wanted_lock" > "$stamp"
echo "Dependencies reinstalled from package-lock.json"
