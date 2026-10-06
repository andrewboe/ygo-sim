#!/usr/bin/env bash
# Build the current edo9300 ygopro-core (EDOPro/Project Ignis engine) as static libs with its own
# meson setup. Lua must be compiled as C++, which ygo-agent's 2024 xmake recipe can't do.
set -e
source ~/ygo/.venv/bin/activate
pip install -q meson ninja
cd ~/ygo/edopro-core
git pull -q --ff-only && git submodule update --init -q
rm -rf build
meson setup build --buildtype=debugoptimized -Ddefault_library=static -Db_staticpic=true > /dev/null
ninja -C build | tail -3
# meson emits thin archives (pointers to .o files); repack as regular archives so they can be copied.
cd build
for a in libocgcore.a lua/liblua.a; do
  objs=$(ar t "$a")
  rm "$a" && ar rcs "$a" $objs
done
ls -la libocgcore.a lua/liblua.a
head -c 8 libocgcore.a | grep -q '!<arch>' && echo "regular archives ok"
