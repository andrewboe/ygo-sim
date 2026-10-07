#!/usr/bin/env bash
# PyTorch with CUDA for the RTX 5080 (Blackwell, sm_120 needs CUDA 12.8+ builds) in the WSL venv,
# plus a quick GPU check: device name, compute capability, and a timed matmul.
set -e
source ~/ygo/.venv/bin/activate
pip install -q --upgrade torch --index-url https://download.pytorch.org/whl/cu128
python3 - <<'EOF'
import time, torch
print("torch", torch.__version__, "cuda", torch.version.cuda, "available", torch.cuda.is_available())
d = torch.device("cuda")
print("device", torch.cuda.get_device_name(0), "capability", torch.cuda.get_device_capability(0))
print("supported archs", torch.cuda.get_arch_list())
x = torch.randn(8192, 8192, device=d, dtype=torch.bfloat16)
torch.cuda.synchronize(); t = time.time()
for _ in range(20):
    y = x @ x
torch.cuda.synchronize(); dt = time.time() - t
print(f"bf16 matmul: {20 * 2 * 8192**3 / dt / 1e12:.1f} TFLOPS")
EOF
