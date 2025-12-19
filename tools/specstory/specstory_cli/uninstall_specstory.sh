#!/usr/bin/env bash
set -e

echo "Uninstalling SpecStory wrapper..."

# Constants (matching install script)
WRAPPER_DIR="$HOME/.specstory_wrapper"
WRAPPER_BIN="$HOME/bin/specstory"
CLAUDE_WRAPPER_BIN="$HOME/bin/claude"
PATH_EXPORT='export PATH="$HOME/bin:$PATH"'

# Helper to remove lines from profiles
remove_from_profile() {
    local profile="$1"
    local pattern="$2"
    if [[ -f "$profile" ]]; then
        if grep -q "$pattern" "$profile"; then
            echo "➡ Cleaning up $profile..."
            # Use temp file for compatibility across Linux/macOS
            grep -v "$pattern" "$profile" > "${profile}.tmp" || true
            mv "${profile}.tmp" "$profile"
        fi
    fi
}

# Helper to check if a file is a wrapper
is_wrapper() {
    local file="$1"
    [[ ! -f "$file" ]] && return 1
    # Check for signature
    grep -q "specstory_wrapper.py" "$file" 2>/dev/null && return 0
    return 1
}

# 1. Remove wrapper binaries
for bin in "$WRAPPER_BIN" "$CLAUDE_WRAPPER_BIN" "$HOME/bin/specstory-real"; do
    if is_wrapper "$bin"; then
        echo "➡ Removing wrapper: $bin"
        rm "$bin"
    elif [[ -f "$bin" ]] && [[ "$bin" == "$CLAUDE_WRAPPER_BIN" ]]; then
        # Always remove the claude wrapper we created
        echo "➡ Removing $bin"
        rm "$bin"
    fi
done

# 2. Remove wrapper folder
if [[ -d "$WRAPPER_DIR" ]]; then
    echo "➡ Removing $WRAPPER_DIR"
    rm -rf "$WRAPPER_DIR"
fi

# 3. Clean up shell profiles
for profile in "$HOME/.zshrc" "$HOME/.bashrc" "$HOME/.profile"; do
    # Remove PATH export
    remove_from_profile "$profile" "^export PATH=\"\$HOME/bin:\$PATH\""
    remove_from_profile "$profile" "^PATH=\"\$HOME/bin:\$PATH\""
    
    # Remove aliases
    remove_from_profile "$profile" "^alias claude="
    
    # Remove functions (simple check for the common one added)
    if [[ -f "$profile" ]] && grep -q "claude() {" "$profile"; then
        echo "➡ Removing claude() function from $profile"
        # Remove function block (heuristic)
        sed -i.bak '/claude() {/,/}/d' "$profile" 2>/dev/null || true
        rm -f "${profile}.bak"
    fi

    # Remove SPECSTORY HOOK sections (from venv patching)
    if [[ -f "$profile" ]]; then
        sed -i.bak '/# SPECSTORY HOOK START/,/# SPECSTORY HOOK END/d' "$profile" 2>/dev/null || true
        sed -i.bak '/# SPECSTORY DEACTIVATE HOOK/,/unalias claude/d' "$profile" 2>/dev/null || true
        sed -i.bak '/# SPECSTORY DEACTIVATE HOOK/,/unset -f claude/d' "$profile" 2>/dev/null || true
        rm -f "${profile}.bak"
    fi
done

# 4. Remove conda activation hooks
if command -v conda >/dev/null 2>&1; then
    while IFS= read -r ENV_PATH; do
        [[ -z "$ENV_PATH" ]] && continue
        for hook in "$ENV_PATH/etc/conda/activate.d/specstory.sh" "$ENV_PATH/etc/conda/deactivate.d/specstory.sh"; do
            if [[ -f "$hook" ]]; then
                echo "➡ Removing conda hook: $hook"
                rm -f "$hook"
            fi
        done
    done < <(conda env list 2>/dev/null | awk 'NR>2 && NF {print $NF}')
fi

# 5. Restore original specstory binary
RESTORED=false
CANDIDATES=(
    "/usr/local/bin/specstory-real"
    "/opt/homebrew/bin/specstory-real"
    "/usr/bin/specstory-real"
    "$HOME/bin/specstory-real"
)

for real in "${CANDIDATES[@]}"; do
    if [[ -f "$real" ]] && ! is_wrapper "$real"; then
        base_dir="$(dirname "$real")"
        target="$base_dir/specstory"
        
        # If target is a wrapper or symlink, replace it
        if [[ ! -f "$target" ]] || [[ -L "$target" ]] || is_wrapper "$target"; then
            echo "➡ Restoring $real → $target"
            [[ -f "$target" || -L "$target" ]] && rm -f "$target"
            mv "$real" "$target" 2>/dev/null || {
                echo "⚠ Could not restore to $target (try running with sudo)"
                echo "  Original binary is at $real"
            }
            RESTORED=true
        else
            # If target already exists and is a real binary, just remove the -real leftover
            echo "✔ Original binary already at $target. Removing leftover $real"
            rm -f "$real"
            RESTORED=true
        fi
    fi
done

if ! $RESTORED; then
    # Check if the binary at the expected location is already the real one
    if [[ -f "/usr/local/bin/specstory" ]] && ! is_wrapper "/usr/local/bin/specstory"; then
        echo "✔ Original specstory binary is already in place at /usr/local/bin/specstory"
    else
        echo "⚠ Could not verify original specstory binary location."
    fi
fi

echo
echo "Uninstall complete!"
echo "═══════════════════════════════════════════════════════════════"
echo "IMPORTANT: To fix your CURRENT terminal session, run:"
echo
echo "  unalias claude 2>/dev/null; unset -f claude 2>/dev/null; hash -r"
echo
echo "═══════════════════════════════════════════════════════════════"
echo "New terminal sessions will work automatically."
echo
