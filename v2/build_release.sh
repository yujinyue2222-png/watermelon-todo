#!/usr/bin/env bash
#
# 西瓜todo 跨平台打包脚本
#
# macOS：生成 dist/西瓜todo.app 和 dist/西瓜todo-<版本>-mac.dmg
# Windows（Git Bash）：生成 dist/西瓜todo.exe；若检测到 Inno Setup，
#                      额外生成可安装的 Setup.exe。
#
# 注意：PyInstaller 不支持交叉编译。请在 macOS 上构建 DMG，在 Windows 上构建 EXE。

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

APP_NAME="西瓜todo"
APP_ID="com.watermelon.desktoptodo"
PY_SOURCE="$ROOT_DIR/todo_qt_v2.py"
SVG_PATH="$ROOT_DIR/watermelon_logo.svg"
VENV_DIR="$ROOT_DIR/.venv_build"
BUILD_DIR="$ROOT_DIR/build"
DIST_DIR="$ROOT_DIR/dist"
ASSET_DIR="$BUILD_DIR/icons"

log() {
    printf '\n==> %s\n' "$1"
}

fail() {
    printf '\n错误：%s\n' "$1" >&2
    exit 1
}

[[ -f "$PY_SOURCE" ]] || fail "找不到 $PY_SOURCE"
[[ -f "$SVG_PATH" ]] || fail "找不到 $SVG_PATH"

case "$(uname -s)" in
    Darwin)
        PLATFORM="mac"
        ;;
    MINGW*|MSYS*|CYGWIN*)
        PLATFORM="windows"
        ;;
    *)
        fail "当前系统不支持。请在 macOS 或 Windows 的 Git Bash 中运行。"
        ;;
esac

PYTHON_ARGS=()
if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
elif command -v py >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v py)"
    PYTHON_ARGS=(-3)
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python)"
else
    fail "未找到 Python 3，请先安装 Python 3.9 或更高版本。"
fi

log "创建独立构建环境"
"$PYTHON_BIN" "${PYTHON_ARGS[@]}" -m venv "$VENV_DIR"
if [[ "$PLATFORM" == "windows" ]]; then
    VENV_PY="$VENV_DIR/Scripts/python.exe"
else
    VENV_PY="$VENV_DIR/bin/python"
fi

"$VENV_PY" -m pip install --upgrade pip
"$VENV_PY" -m pip install "PySide6>=6.5" "PyInstaller>=6.0" "Pillow>=10.0"

VERSION="$(awk -F'"' '/^APP_VERSION = / {print $2; exit}' "$PY_SOURCE")"
[[ -n "$VERSION" ]] || fail "无法从 todo_qt_v2.py 读取 APP_VERSION"

log "生成平台图标"
rm -rf "$BUILD_DIR"
mkdir -p "$ASSET_DIR" "$DIST_DIR"
PNG_PATH="$ASSET_DIR/watermelon-1024.png"

SVG_PATH="$SVG_PATH" PNG_PATH="$PNG_PATH" "$VENV_PY" - <<'PY'
import os
from pathlib import Path

from PySide6.QtCore import QRectF, QSize
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

svg_path = Path(os.environ["SVG_PATH"])
png_path = Path(os.environ["PNG_PATH"])
renderer = QSvgRenderer(str(svg_path))
if not renderer.isValid():
    raise RuntimeError(f"无效的 SVG：{svg_path}")

size = QSize(1024, 1024)
image = QImage(size, QImage.Format_ARGB32)
image.fill(QColor(0, 0, 0, 0))
painter = QPainter(image)
renderer.render(painter, QRectF(0, 0, size.width(), size.height()))
painter.end()
if not image.save(str(png_path), "PNG"):
    raise RuntimeError(f"无法生成 PNG：{png_path}")
PY

if [[ "$PLATFORM" == "windows" ]]; then
    ICO_PATH="$ASSET_DIR/watermelon.ico"
    PNG_PATH="$PNG_PATH" ICO_PATH="$ICO_PATH" "$VENV_PY" - <<'PY'
import os
from pathlib import Path

from PIL import Image

png_path = Path(os.environ["PNG_PATH"])
ico_path = Path(os.environ["ICO_PATH"])
with Image.open(png_path) as image:
    image.convert("RGBA").save(
        ico_path,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
PY

    log "构建 Windows 单文件 EXE"
    "$VENV_PY" -m PyInstaller \
        --noconfirm \
        --clean \
        --onefile \
        --windowed \
        --name "$APP_NAME" \
        --icon "$ICO_PATH" \
        --add-data "$SVG_PATH;." \
        --distpath "$DIST_DIR" \
        --workpath "$BUILD_DIR/pyinstaller" \
        --specpath "$BUILD_DIR" \
        "$PY_SOURCE"

    # Inno Setup 不是 Python 包；若系统已安装，则顺便生成真正的安装程序。
    ISCC_BIN=""
    if command -v ISCC.exe >/dev/null 2>&1; then
        ISCC_BIN="$(command -v ISCC.exe)"
    elif [[ -x "/c/Program Files (x86)/Inno Setup 6/ISCC.exe" ]]; then
        ISCC_BIN="/c/Program Files (x86)/Inno Setup 6/ISCC.exe"
    elif [[ -x "/c/Program Files/Inno Setup 6/ISCC.exe" ]]; then
        ISCC_BIN="/c/Program Files/Inno Setup 6/ISCC.exe"
    fi

    if [[ -n "$ISCC_BIN" ]]; then
        log "使用 Inno Setup 生成 Windows 安装程序"
        ISS_PATH="$BUILD_DIR/watermelon_todo.iss"
        DIST_WIN="$(cygpath -w "$DIST_DIR")"
        ICO_WIN="$(cygpath -w "$ICO_PATH")"
        cat > "$ISS_PATH" <<EOF
[Setup]
AppId={{6D51B216-93DF-4E9B-98CA-88A418D115A4}
AppName=$APP_NAME
AppVersion=$VERSION
DefaultDirName={autopf}\\WatermelonTodo
DefaultGroupName=$APP_NAME
OutputDir=$DIST_WIN
OutputBaseFilename=$APP_NAME-$VERSION-Setup
SetupIconFile=$ICO_WIN
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "$DIST_WIN\\$APP_NAME.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\\$APP_NAME"; Filename: "{app}\\$APP_NAME.exe"
Name: "{autodesktop}\\$APP_NAME"; Filename: "{app}\\$APP_NAME.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加选项："

[Run]
Filename: "{app}\\$APP_NAME.exe"; Description: "启动 $APP_NAME"; Flags: nowait postinstall skipifsilent
EOF
        "$ISCC_BIN" "$(cygpath -w "$ISS_PATH")"
    else
        printf '\n提示：未检测到 Inno Setup，仅生成便携版 EXE。\n'
        printf '安装 Inno Setup 6 后再次运行，可额外生成 Setup.exe。\n'
    fi

    printf '\n打包完成：\n  %s/%s.exe\n' "$DIST_DIR" "$APP_NAME"
else
    command -v iconutil >/dev/null 2>&1 || fail "系统缺少 iconutil"
    command -v hdiutil >/dev/null 2>&1 || fail "系统缺少 hdiutil"
    command -v sips >/dev/null 2>&1 || fail "系统缺少 sips"

    ICONSET_DIR="$ASSET_DIR/watermelon.iconset"
    ICNS_PATH="$ASSET_DIR/watermelon.icns"
    mkdir -p "$ICONSET_DIR"

    sips -z 16 16 "$PNG_PATH" --out "$ICONSET_DIR/icon_16x16.png" >/dev/null
    sips -z 32 32 "$PNG_PATH" --out "$ICONSET_DIR/icon_16x16@2x.png" >/dev/null
    sips -z 32 32 "$PNG_PATH" --out "$ICONSET_DIR/icon_32x32.png" >/dev/null
    sips -z 64 64 "$PNG_PATH" --out "$ICONSET_DIR/icon_32x32@2x.png" >/dev/null
    sips -z 128 128 "$PNG_PATH" --out "$ICONSET_DIR/icon_128x128.png" >/dev/null
    sips -z 256 256 "$PNG_PATH" --out "$ICONSET_DIR/icon_128x128@2x.png" >/dev/null
    sips -z 256 256 "$PNG_PATH" --out "$ICONSET_DIR/icon_256x256.png" >/dev/null
    sips -z 512 512 "$PNG_PATH" --out "$ICONSET_DIR/icon_256x256@2x.png" >/dev/null
    sips -z 512 512 "$PNG_PATH" --out "$ICONSET_DIR/icon_512x512.png" >/dev/null
    cp "$PNG_PATH" "$ICONSET_DIR/icon_512x512@2x.png"
    iconutil -c icns "$ICONSET_DIR" -o "$ICNS_PATH"

    log "构建 macOS APP"
    "$VENV_PY" -m PyInstaller \
        --noconfirm \
        --clean \
        --windowed \
        --name "$APP_NAME" \
        --icon "$ICNS_PATH" \
        --osx-bundle-identifier "$APP_ID" \
        --add-data "$SVG_PATH:." \
        --distpath "$DIST_DIR" \
        --workpath "$BUILD_DIR/pyinstaller" \
        --specpath "$BUILD_DIR" \
        "$PY_SOURCE"

    APP_BUNDLE="$DIST_DIR/$APP_NAME.app"
    [[ -d "$APP_BUNDLE" ]] || fail "未生成 $APP_BUNDLE"
    codesign --force --deep --sign - "$APP_BUNDLE"

    log "生成 macOS DMG"
    DMG_STAGE="$BUILD_DIR/dmg"
    DMG_PATH="$DIST_DIR/$APP_NAME-$VERSION-mac.dmg"
    rm -rf "$DMG_STAGE"
    mkdir -p "$DMG_STAGE"
    cp -R "$APP_BUNDLE" "$DMG_STAGE/"
    ln -s /Applications "$DMG_STAGE/Applications"
    rm -f "$DMG_PATH"
    hdiutil create \
        -volname "$APP_NAME" \
        -srcfolder "$DMG_STAGE" \
        -ov \
        -format UDZO \
        "$DMG_PATH"

    printf '\n打包完成：\n  %s\n  %s\n' "$APP_BUNDLE" "$DMG_PATH"
    printf '\n未配置 Apple Developer 签名和公证时，其他 Mac 首次打开可能需要右键“打开”。\n'
fi
