#!/usr/bin/env bash
# =====================================================================
#  VardiaShift - Linux installer
#
#  Copies the built app into ~/.local/share, installs the icon sizes a
#  Linux desktop expects, and registers a .desktop entry so VardiaShift
#  appears in the applications menu and can be launched from a search.
#
#  Run from anywhere:
#      ./install.sh
#
#  Remove it again:
#      ./install.sh --uninstall
#
#  Options:
#      --prefix DIR   install under DIR instead of ~/.local/share
#      --uninstall    remove an existing installation
# =====================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}"
UNINSTALL=0
SOURCE_DIR=""

while [ $# -gt 0 ]; do
    case "$1" in
        --prefix)
            PREFIX="$2"
            shift 2
            ;;
        --prefix=*)
            PREFIX="${1#*=}"
            shift
            ;;
        --uninstall)
            UNINSTALL=1
            shift
            ;;
        --source)
            SOURCE_DIR="$2"
            shift 2
            ;;
        --source=*)
            SOURCE_DIR="${1#*=}"
            shift
            ;;
        -h|--help)
            sed -n '2,20p' "$0"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

APP_DIR="$PREFIX/vardiashift"
BINARY="$APP_DIR/VardiaShift"
DESKTOP_DIR="$PREFIX/applications"
ICON_ROOT="$PREFIX/icons"
DESKTOP_FILE="$DESKTOP_DIR/vardiashift.desktop"

if [ "$UNINSTALL" -eq 1 ]; then
    rm -f "$DESKTOP_FILE"
    rm -rf "$APP_DIR"
    # Only VardiaShift's own icons: the theme folder is shared with anything
    # else the user installed.
    find "$ICON_ROOT" -type f -name "vardiashift.png" -delete 2>/dev/null || true
    find "$ICON_ROOT" -depth -type d -empty -delete 2>/dev/null || true
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
    echo "VardiaShift removed."
    exit 0
fi

# Inside a release archive the executable sits two folders up from this script.
# In the repository it is under dist/.
if [ -z "$SOURCE_DIR" ]; then
    if [ -x "$APP_ROOT/VardiaShift" ]; then
        SOURCE_DIR="$APP_ROOT"
    else
        SOURCE_DIR="$APP_ROOT/dist/VardiaShift"
    fi
fi

if [ ! -x "$SOURCE_DIR/VardiaShift" ]; then
    echo "[ERROR] No built application at $SOURCE_DIR/VardiaShift"
    echo "        Run ./build_linux.sh first, or pass --source DIR."
    exit 1
fi

echo "[1/4] Installing to $APP_DIR"
mkdir -p "$APP_DIR"
# cp -a keeps the executable bit and symlinks inside the bundle.
cp -a "$SOURCE_DIR/." "$APP_DIR/"

echo "[2/4] Installing icons"
# The icon lives in the repository when run from a checkout, and inside the
# bundle when run from a release archive.
ICON_SOURCE="$APP_ROOT/assets/icon.png"
if [ ! -f "$ICON_SOURCE" ]; then
    ICON_SOURCE="$SOURCE_DIR/_internal/assets/icon.png"
fi
if [ -f "$ICON_SOURCE" ]; then
    # Pillow ships with the bundle, but the icon sizes only need the interpreter
    # that generated the app, so fall back to copying the single large PNG.
    if command -v python3 >/dev/null 2>&1 && python3 -c "import PIL" >/dev/null 2>&1; then
        python3 "$SCRIPT_DIR/make-icons.py" "$ICON_SOURCE" "$ICON_ROOT"
    else
        mkdir -p "$ICON_ROOT/hicolor/512x512/apps"
        cp "$ICON_SOURCE" "$ICON_ROOT/hicolor/512x512/apps/vardiashift.png"
        echo "      Pillow not available: installed one icon size only."
    fi
else
    echo "      [WARNING] No icon found; skipping."
fi

echo "[3/4] Registering the application menu entry"
mkdir -p "$DESKTOP_DIR"
# The stock file uses a bare "Exec=vardiashift"; the absolute path is what makes
# it work without adding the folder to PATH. Path= tells the desktop where the
# bundle lives, which matters for the shared libraries in _internal.
sed -e "s|^Exec=.*|Exec=$BINARY|" \
    -e "s|^Path=.*|Path=$APP_DIR|" \
    "$SCRIPT_DIR/vardiashift.desktop" > "$DESKTOP_FILE"
chmod +x "$DESKTOP_FILE"

echo "[4/4] Refreshing caches"
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -f -t "$ICON_ROOT" >/dev/null 2>&1 || true
fi

echo
echo "====================================================================="
echo "  INSTALLED"
echo
echo "  Launch from the applications menu, or:"
echo "      $BINARY"
echo
echo "  Remove with:"
echo "      $0 --uninstall"
echo "====================================================================="
