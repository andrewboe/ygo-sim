#!/usr/bin/env bash
# Python venv in WSL for ygoenv and the goldfish driver.
set -e
cd ~/ygo
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -U pip
.venv/bin/pip install -q numpy dm-env "gym>=0.26" gymnasium optree packaging pybind11 pybind11-stubgen tqdm tyro
.venv/bin/python -c 'import numpy, gymnasium, optree; print("venv ok, numpy", numpy.__version__)'
