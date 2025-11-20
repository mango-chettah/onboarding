#!/usr/bin/env bash
set -e

echo "Installing Specstory wrapper..."

# --- 1. Locate real specstory binary ---
REAL_BIN="$(command -v specstory || true)"
if [[ -z "$REAL_BIN" ]]; then
  echo "Specstory not found in PATH. Install it first (brew install specstoryai/tap/specstory)."
  exit 1
fi

REAL_DIR="$(dirname "$REAL_BIN")"
REAL_WRAPPED="$REAL_DIR/specstory-real"

# --- 2. Rename real binary (if not already renamed) ---
if [[ ! -f "$REAL_WRAPPED" ]]; then
  echo "➡ Renaming $REAL_BIN → $REAL_WRAPPED"
  mv "$REAL_BIN" "$REAL_WRAPPED"
else
  echo "✔ Real binary already renamed."
fi

# --- 3. Install wrapper to ~/bin/specstory ---
mkdir -p "$HOME/bin"
WRAPPER_BIN="$HOME/bin/specstory"

echo "➡ Installing wrapper launcher → $WRAPPER_BIN"
cat > "$WRAPPER_BIN" <<'EOF'
#!/usr/bin/env bash
python3 "$HOME/.specstory_wrapper/specstory_wrapper.py" "$@"
EOF

chmod +x "$WRAPPER_BIN"

# --- 4. Install Python wrapper script ---
if [[ ! -f "specstory_wrapper.py" ]]; then
  echo "specstory_wrapper.py not found in the current directory."
  echo "Please place it next to this installer."
  exit 1
fi

echo "➡ Copying specstory_wrapper.py → ~/.specstory_wrapper/"
mkdir -p "$HOME/.specstory_wrapper"
cp specstory_wrapper.py "$HOME/.specstory_wrapper/specstory_wrapper.py"

if ! echo "$PATH" | grep -q "$HOME/bin"; then
  echo "➡ Adding ~/bin to PATH in your shell config (bash/zsh)"

  PROFILE_FILES=()

  # Always consider both common rc files so it works even if you switch shells
  PROFILE_FILES+=("$HOME/.zshrc" "$HOME/.bashrc")

  # De-duplicate list
  UNIQUE_PROFILES=()
  for P in "${PROFILE_FILES[@]}"; do
    SKIP=false
    for U in "${UNIQUE_PROFILES[@]}"; do
      if [[ "$P" == "$U" ]]; then
        SKIP=true
        break
      fi
    done
    $SKIP && continue
    UNIQUE_PROFILES+=("$P")
  done

  for PROFILE in "${UNIQUE_PROFILES[@]}"; do
    [[ -z "$PROFILE" ]] && continue

    # Create the profile file if it doesn't exist yet
    if [[ ! -f "$PROFILE" ]]; then
      touch "$PROFILE"
    fi

    if ! grep -q 'export PATH="$HOME/bin:$PATH"' "$PROFILE" 2>/dev/null; then
      echo "➡ Updating $PROFILE"
      echo 'export PATH="$HOME/bin:$PATH"' >> "$PROFILE"
    else
      echo "✔ ~/bin already configured in $PROFILE"
    fi
  done
fi

# --- 6. Conda per-environment activation hook (FIXED) ---
if command -v conda >/dev/null 2>&1; then

  echo
  echo "IMPORTANT:"
  echo "Enter the name of the conda environment where Specstory capture should be active."
  echo "(Example: base or your dev environment name)"
  printf "Environment name: "
  read ENV_NAME

  # Validate environment name is not empty or contains special characters
  if [[ -z "$ENV_NAME" ]] || [[ "$ENV_NAME" =~ [^a-zA-Z0-9_-] ]]; then
    echo "Error: Invalid environment name. Use only alphanumeric characters, underscores, and hyphens."
    exit 1
  fi

  # Validate environment exists and get its path
  ENV_PATH="$(conda env list | grep -E "^${ENV_NAME}[[:space:]]" | awk '{print $NF}')"

  if [[ -z "$ENV_PATH" ]]; then
    echo "Conda environment '$ENV_NAME' not found."
    echo "Available environments:"
    conda env list
    exit 1
  fi

  # Validate the path exists and is a directory
  if [[ ! -d "$ENV_PATH" ]]; then
    echo "Error: Environment path '$ENV_PATH' is not a valid directory."
    exit 1
  fi

  HOOK_DIR="$ENV_PATH/etc/conda/activate.d"
  mkdir -p "$HOOK_DIR"

  echo "➡ Adding activation hook ONLY for env '$ENV_NAME' → $HOOK_DIR/specstory.sh"

  cat > "$HOOK_DIR/specstory.sh" <<'EOF'
export PATH="$HOME/bin:$PATH"
alias claude="specstory run claude --no-cloud-sync"
EOF

  # Create deactivation hook to unset alias when leaving environment
  DEACTIVATE_HOOK_DIR="$ENV_PATH/etc/conda/deactivate.d"
  mkdir -p "$DEACTIVATE_HOOK_DIR"

  echo "➡ Adding deactivation hook ONLY for env '$ENV_NAME' → $DEACTIVATE_HOOK_DIR/specstory.sh"

  cat > "$DEACTIVATE_HOOK_DIR/specstory.sh" <<'EOF'
unalias claude 2>/dev/null || true
EOF

  echo "✔ Activation and deactivation hooks installed for environment: $ENV_NAME"
  echo "➡ When you run:  conda activate $ENV_NAME"
  echo "   The alias 'claude' will route through specstory. Please note that "claude" cannot accept arguments."
  echo "➡ When you run:  conda deactivate"
  echo "   The alias 'claude' will be removed."
fi

echo
echo "Installation complete!"
echo "Your Specstory wrapper is ready."
echo "Restart your terminal or 'source ~/.zshrc' / 'source ~/.bashrc' if needed."
echo