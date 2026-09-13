#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"

die() {
    echo "error: $*" >&2
    exit 1
}

[[ -d "$SCRIPT_DIR/claude" ]] || die "claude/ not found next to setup.sh; run it from the claude-fable-orchestrator checkout."
[[ -f "$SCRIPT_DIR/CLAUDE.snippet.md" ]] || die "CLAUDE.snippet.md not found next to setup.sh."

# ask <prompt> <default y|n>: returns 0 for yes; EOF or invalid input aborts the prompt
ask() {
    local prompt="$1" default="$2" answer=""
    while true; do
        if ! read -r -p "$prompt" answer; then
            echo "setup: input ended; skipping this prompt." >&2
            return 1
        fi
        answer="$(printf '%s' "$answer" | tr '[:upper:]' '[:lower:]')"
        case "$answer" in
            y|yes) return 0 ;;
            n|no)  return 1 ;;
            "")    if [[ "$default" == "y" ]]; then return 0; else return 1; fi ;;
            *)     echo "Please answer yes or no." ;;
        esac
    done
}

TARGET=""
while true; do
    raw=""
    read -r -p "Target repository path: " raw || exit 1
    case "$raw" in
        "~")   raw="$HOME" ;;
        "~/"*) raw="$HOME/${raw:2}" ;;
    esac
    if [[ -z "$raw" ]]; then
        echo "Please enter a path." >&2
        continue
    fi
    if [[ ! -e "$raw" ]]; then
        echo "Does not exist: $raw" >&2
        continue
    fi
    if [[ ! -d "$raw" ]]; then
        echo "Not a directory: $raw" >&2
        continue
    fi
    abs="$(cd "$raw" && pwd -P)"
    if [[ "$abs" == "$SCRIPT_DIR" || "$abs" == "$SCRIPT_DIR/"* ]]; then
        echo "Target must not be the scaffold repo itself." >&2
        continue
    fi
    TARGET="$abs"
    break
done

echo "Installing into: $TARGET"
echo

# install_dir <source dir> <dest dir> <label>
install_dir() {
    local src="$1" dest="$2" label="$3"
    local f d rel linked
    local overwrites=() conflicts=()
    local added=0 replaced=0

    if [[ -L "$dest" ]]; then
        echo "$label: skipped, $dest is a symbolic link; refusing to write through it." >&2
        return 0
    fi
    if [[ -e "$dest" && ! -d "$dest" ]]; then
        echo "$label: skipped, $dest exists and is not a directory." >&2
        return 0
    fi
    if [[ -d "$dest" ]]; then
        linked="$(find "$dest" -type l -print | head -n 1)"
        if [[ -n "$linked" ]]; then
            echo "$label: skipped, existing target contains a symbolic link ($linked)." >&2
            return 0
        fi
    fi

    while IFS= read -r -d '' f; do
        rel="${f#"$src"/}"
        if [[ ( -e "$dest/$rel" || -L "$dest/$rel" ) && ! -f "$dest/$rel" ]]; then
            conflicts+=("$rel")
        elif [[ -f "$dest/$rel" ]]; then
            overwrites+=("$rel")
            replaced=$((replaced + 1))
        else
            added=$((added + 1))
        fi
    done < <(find "$src" -type f -print0)

    while IFS= read -r -d '' d; do
        [[ "$d" == "$src" ]] && continue
        rel="${d#"$src"/}"
        if [[ ( -e "$dest/$rel" || -L "$dest/$rel" ) && ! -d "$dest/$rel" ]]; then
            conflicts+=("$rel/")
        fi
    done < <(find "$src" -type d -print0)

    if [[ ${#conflicts[@]} -gt 0 ]]; then
        echo "$label: skipped, source and target types conflict at:" >&2
        printf '%s\n' "${conflicts[@]}" | sort | sed 's/^/  /' >&2
        return 0
    fi

    if [[ ${#overwrites[@]} -gt 0 ]]; then
        echo "$label: these files already exist under $dest and would be overwritten:"
        printf '%s\n' "${overwrites[@]}" | sort | sed 's/^/  /'
        if ! ask "Update? [y/N] " "n"; then
            echo "$label: skipped."
            return 0
        fi
    fi

    mkdir -p "$dest"
    cp -R "$src/." "$dest/"
    echo "$label: installed to $dest ($added added, $replaced replaced)"
}

if ask "Install .claude/agents? [Y/n] " "y"; then
    install_dir "$SCRIPT_DIR/claude/agents" "$TARGET/.claude/agents" "agents"
fi
echo

if ask "Install .claude/skills/orchestrator? [Y/n] " "y"; then
    install_dir "$SCRIPT_DIR/claude/skills/orchestrator" "$TARGET/.claude/skills/orchestrator" "orchestrator skill"
fi
echo

START_MARK='<!-- claude-fable-orchestrator:start -->'
END_MARK='<!-- claude-fable-orchestrator:end -->'

if ask "Install CLAUDE.md orchestration block? [Y/n] " "y"; then
    claude_md="$TARGET/CLAUDE.md"
    if [[ -L "$claude_md" ]] || { [[ -e "$claude_md" ]] && [[ ! -f "$claude_md" ]]; }; then
        echo "CLAUDE.md block: skipped, $claude_md must be a regular file, not a symbolic link."
    elif [[ -f "$claude_md" ]] && grep -qF "$START_MARK" "$claude_md"; then
        echo "CLAUDE.md block: already present in $claude_md, skipped."
    else
        if [[ -s "$claude_md" ]]; then
            printf '\n' >> "$claude_md"
        fi
        {
            printf '%s\n' "$START_MARK"
            cat "$SCRIPT_DIR/CLAUDE.snippet.md"
            printf '%s\n' "$END_MARK"
        } >> "$claude_md"
        echo "CLAUDE.md block: appended to $claude_md"
    fi
fi
echo

SETTINGS_WRITTEN=0
settings_json="$TARGET/.claude/settings.json"
if [[ -L "$settings_json" ]] || { [[ -e "$settings_json" ]] && [[ ! -f "$settings_json" ]]; }; then
    echo "session model: skipped, $settings_json must be a regular file, not a symbolic link."
elif [[ -f "$settings_json" ]]; then
    echo "session model: $settings_json already exists; add \"model\": \"fable\" to it manually."
elif ask "Install .claude/settings.json (session model: fable)? [Y/n] " "y"; then
    mkdir -p "$TARGET/.claude"
    printf '{\n  "model": "fable"\n}\n' > "$settings_json"
    SETTINGS_WRITTEN=1
    echo "session model: wrote $settings_json"
fi

echo
echo "Install complete. Next steps:"
echo "  1. cd $TARGET && claude"
if [[ "$SETTINGS_WRITTEN" -eq 0 ]]; then
    echo "  2. Run /model fable to set the root session model."
    echo "  3. Ask for orchestration: \"use the orchestrator skill\", or name a flow e.g. \"use the debug flow\"."
else
    echo "  2. Ask for orchestration: \"use the orchestrator skill\", or name a flow e.g. \"use the debug flow\"."
fi
