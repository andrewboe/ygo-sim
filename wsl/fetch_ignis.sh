#!/usr/bin/env bash
# Fetch Project Ignis card scripts and card database (the data EDOPro runs on).
set -e
cd ~/ygo
[ -d CardScripts ] || git clone -q --depth 1 https://github.com/ProjectIgnis/CardScripts.git
[ -d BabelCDB ] || git clone -q --depth 1 https://github.com/ProjectIgnis/BabelCDB.git
git -C CardScripts pull -q --ff-only; git -C BabelCDB pull -q --ff-only
git -C CardScripts log -1 --format='CardScripts: %h %cd' --date=short
git -C BabelCDB log -1 --format='BabelCDB: %h %cd' --date=short
ls BabelCDB/*.cdb | head -20
echo "official scripts: $(ls CardScripts/official | wc -l)"
# Spot-check that current-meta cards are scripted (passcodes from YGOProDeck).
for id in 30271097 85523502; do ls CardScripts/official/c$id.lua 2>/dev/null || echo "missing c$id"; done
