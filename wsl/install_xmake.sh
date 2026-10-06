#!/usr/bin/env bash
# Install xmake from its official GitHub release as a single self-contained binary in ~/.local/bin.
set -e
mkdir -p ~/.local/bin
tag=$(curl -fsSL https://api.github.com/repos/xmake-io/xmake/releases/latest | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])')
url="https://github.com/xmake-io/xmake/releases/download/${tag}/xmake-bundle-${tag}.linux.x86_64"
echo "downloading $url"
curl -fsSL "$url" -o ~/.local/bin/xmake
chmod +x ~/.local/bin/xmake
~/.local/bin/xmake --version | head -1
