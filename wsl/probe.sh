#!/usr/bin/env bash
# Report what the WSL environment has for building ygoenv and training on the GPU.
whoami; lsb_release -ds; python3 --version
for t in gcc g++ make cmake git curl unzip; do printf "%s: " "$t"; command -v "$t" || echo MISSING; done
nvidia-smi --query-gpu=name,driver_version,compute_cap --format=csv,noheader 2>&1 | head -2
echo "cpus: $(nproc)"; free -g | sed -n 2p; df -h ~ | tail -1
sudo -n true 2>/dev/null && echo SUDO_NOPASS || echo SUDO_NEEDS_PASSWORD
