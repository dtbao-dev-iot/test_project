#!/usr/bin/env bash
# setup_hooks.sh: Install dtbao-IoT git hooks from .githooks/ directory
# Run this script once after cloning the repository
# Usage: bash docs/scripts/setup_hooks.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
HOOKS_DIR="$PROJECT_ROOT/.githooks"

if [ ! -d "$HOOKS_DIR" ]; then
    echo "ERROR: .githooks/ directory not found at $HOOKS_DIR"
    exit 1
fi

# Set git hooks path to .githooks/
git -C "$PROJECT_ROOT" config core.hooksPath .githooks

# Make hooks executable (Linux/macOS)
chmod +x "$HOOKS_DIR/pre-commit" 2>/dev/null || true
chmod +x "$HOOKS_DIR/pre-push" 2>/dev/null || true
chmod +x "$HOOKS_DIR/commit-msg" 2>/dev/null || true

echo "Git hooks installed successfully!"
echo ""
echo "  Hooks path : .githooks/"
echo "  pre-commit : clang-format style check"
echo "  pre-push   : branch naming + cppcheck static analysis"
echo "  commit-msg  : Conventional Commits validation"
echo ""
echo "To skip hooks temporarily:"
echo "  git commit --no-verify    (skip pre-commit + commit-msg)"
echo "  git push --no-verify     (skip pre-push)"