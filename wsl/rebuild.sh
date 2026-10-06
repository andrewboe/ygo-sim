#!/usr/bin/env bash
# Re-apply ygoenv patches and rebuild edopro_ygoenv; print only compiler errors.
export PATH=~/.local/bin:$PATH
source ~/ygo/.venv/bin/activate
python3 /mnt/c/Users/andre/Desktop/ygo-sim/wsl/patch_ygoenv.py
cd ~/ygo/ygo-agent
xmake b -y edopro_ygoenv > /tmp/build.log 2>&1
status=$?
grep -E 'error:' /tmp/build.log | sed 's/\x1b\[[0-9;]*m//g' | sort -u | head -${1:-40}
echo "build exit: $status"; tail -3 /tmp/build.log | sed 's/\x1b\[[0-9;]*m//g'
