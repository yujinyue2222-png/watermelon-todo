#!/bin/bash
# =============================================================================
#  西瓜todo · macOS 打包脚本
#  在一台 Mac 上运行本脚本，即可把程序打包成「西瓜todo.app」，
#  你的同事下载后拖进「应用程序」双击即用，无需安装 Python。
#
#  使用方法（在 Mac 的「终端」里执行）：
#     cd 到本文件所在目录
#     chmod +x build_mac.sh
#     ./build_mac.sh
#
#  产物：dist/西瓜todo.app （可再压缩成 zip 发给别人）
# =============================================================================

set -e
cd "$(dirname "$0")"

APP_NAME="西瓜todo"

echo "==> 1/4 检查 Python3"
if ! command -v python3 >/dev/null 2>&1; then
    echo "未找到 python3，请先安装：https://www.python.org/downloads/macos/"
    exit 1
fi

echo "==> 2/4 创建虚拟环境并安装依赖 (PySide6 + PyInstaller)"
python3 -m venv .venv_mac
source .venv_mac/bin/activate
python -m pip install --upgrade pip
pip install PySide6 pyinstaller

echo "==> 3/4 用 PyInstaller 打包为 .app（窗口模式，无终端黑框）"
rm -rf build dist
pyinstaller \
    --noconfirm \
    --windowed \
    --name "$APP_NAME" \
    --osx-bundle-identifier "com.watermelon.desktoptodo" \
    todo_qt.py

echo "==> 4/4 压缩成 zip，便于分发"
cd dist
# 用 ditto 保留 .app 结构与权限，压出来的 zip 别人解压即用
ditto -c -k --keepParent "$APP_NAME.app" "$APP_NAME-mac.zip"
cd ..

echo ""
echo "✅ 打包完成！"
echo "   应用： dist/$APP_NAME.app"
echo "   分发： dist/$APP_NAME-mac.zip  （把这个发给同事）"
echo ""
echo "📌 首次打开提示：macOS 可能提示「无法验证开发者」，"
echo "   让对方在 应用上「右键 → 打开」一次，或到"
echo "   系统设置 → 隐私与安全性 → 仍要打开，即可正常使用。"