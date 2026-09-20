#!/bin/sh
set -eu

usage() {
    printf '%s\n' \
        'Usage: ./install.sh [--dry-run | --check] [--no-link-bin]' \
        '' \
        'Installs the tracked files into ${CLAUDE_CONFIG_DIR:-$HOME/.claude}.' \
        'Changed destination files are backed up before replacement.'
}

mode=install
link_bin=yes

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run) mode=dry-run ;;
        --check) mode=check ;;
        --no-link-bin) link_bin=no ;;
        -h|--help) usage; exit 0 ;;
        *) printf 'Unknown option: %s\n' "$1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
target_dir=${CLAUDE_CONFIG_DIR:-"$HOME/.claude"}
local_bin_dir=${LOCAL_BIN_DIR:-"$HOME/.local/bin"}
manifest="$repo_dir/config-manifest.txt"
timestamp=$(date -u '+%Y%m%dT%H%M%SZ')
backup_dir="$target_dir/backups/claude-global-config-$timestamp"
changed=0

while IFS= read -r relative_path || [ -n "$relative_path" ]; do
    case "$relative_path" in
        ''|'#'*) continue ;;
        /*|../*|*/../*|*/..) printf 'Unsafe manifest path: %s\n' "$relative_path" >&2; exit 2 ;;
    esac

    source_path="$repo_dir/$relative_path"
    destination_path="$target_dir/$relative_path"

    if [ ! -f "$source_path" ]; then
        printf 'Missing source file: %s\n' "$source_path" >&2
        exit 2
    fi

    if [ -f "$destination_path" ] && cmp -s "$source_path" "$destination_path"; then
        continue
    fi

    changed=1
    if [ "$mode" = check ]; then
        printf 'DIFF %s\n' "$relative_path"
        continue
    fi
    if [ "$mode" = dry-run ]; then
        printf 'INSTALL %s\n' "$relative_path"
        continue
    fi

    destination_parent=$(dirname -- "$destination_path")
    mkdir -p "$destination_parent"
    if [ -e "$destination_path" ] || [ -L "$destination_path" ]; then
        backup_path="$backup_dir/$relative_path"
        mkdir -p "$(dirname -- "$backup_path")"
        cp -p "$destination_path" "$backup_path"
    fi
    cp -p "$source_path" "$destination_path"
    printf 'Installed %s\n' "$relative_path"
done < "$manifest"

if [ "$mode" = check ]; then
    if [ "$changed" -eq 0 ]; then
        printf '%s\n' 'Configuration matches the tracked repository.'
        exit 0
    fi
    exit 1
fi

if [ "$link_bin" = yes ]; then
    for helper in claude-workflow remote-runner; do
        link_path="$local_bin_dir/$helper"
        helper_path="$target_dir/bin/$helper"
        if [ -e "$link_path" ] && [ ! -L "$link_path" ]; then
            printf 'Skipped %s: an existing non-symlink file is in the way.\n' "$link_path" >&2
            continue
        fi
        if [ "$mode" = dry-run ]; then
            printf 'LINK %s -> %s\n' "$link_path" "$helper_path"
            continue
        fi
        mkdir -p "$local_bin_dir"
        ln -sfn "$helper_path" "$link_path"
    done
fi

if [ "$mode" = install ] && [ "$changed" -eq 0 ]; then
    printf '%s\n' 'Configuration already matches the tracked repository.'
fi
if [ "$mode" = install ] && [ -d "$backup_dir" ]; then
    printf 'Previous files were backed up to %s\n' "$backup_dir"
fi

