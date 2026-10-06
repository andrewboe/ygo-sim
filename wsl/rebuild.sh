#!/usr/bin/env bash
# Re-apply ygoenv patches and rebuild edopro_ygoenv; print only compiler errors.
export PATH=~/.local/bin:$PATH
source ~/ygo/.venv/bin/activate
python3 /mnt/c/Users/andre/Desktop/ygo-sim/wsl/patch_ygoenv.py || exit 1
cd ~/ygo/ygo-agent
# Move the installed module aside instead of letting the build overwrite it in place: running
# simulations keep their mapped copy (same inode) and new runs load the fresh file.
for so in ygoenv/ygoenv/edopro/edopro_ygoenv*.so; do
  [ -e "$so" ] && mv "$so" "$so.old"
done
xmake b -y edopro_ygoenv > /tmp/build.log 2>&1
status=$?
grep -E 'error:' /tmp/build.log | sed 's/\x1b\[[0-9;]*m//g' | sort -u | head -${1:-40}
if [ $status -ne 0 ]; then  # keep the previous module usable if the build failed
  for old in ygoenv/ygoenv/edopro/edopro_ygoenv*.so.old; do [ -e "$old" ] && mv "$old" "${old%.old}"; done
fi
echo "build exit: $status"; tail -3 /tmp/build.log | sed 's/\x1b\[[0-9;]*m//g'
