#!/usr/bin/env bash
# install.sh — set up the solar_thermal_detection environment
# Tested: Python 3.13 + CUDA 13.0 (uses cu124 wheels — CUDA is backwards-compatible)
# Usage:  bash install.sh

set -e

echo "=== Solar Thermal Detection — Dependency Installer ==="
echo "Python: $(python3 --version)"
echo ""

# ── Upgrade pip ───────────────────────────────────────────────────────────────
pip install --upgrade pip

# ── PyTorch + torchvision (cu124 wheels support Python 3.13; run on CUDA 13.x fine) ──
pip install \
    "torch>=2.5.0" \
    "torchvision>=0.20.0" \
    --index-url https://download.pytorch.org/whl/cu124

# ── Ultralytics YOLOv8 ───────────────────────────────────────────────────────
pip install "ultralytics>=8.2.0"

# ── Augmentation ─────────────────────────────────────────────────────────────
pip install "albumentations>=1.4.0"

# ── Vision / Data ────────────────────────────────────────────────────────────
pip install \
    "opencv-python>=4.9.0" \
    "numpy>=1.26.0" \
    "Pillow>=10.2.0" \
    "scikit-learn>=1.4.0" \
    "pandas>=2.2.0" \
    "pyyaml>=6.0.1" \
    "tqdm>=4.66.0"

# ── Visualisation ────────────────────────────────────────────────────────────
pip install \
    "matplotlib>=3.8.0" \
    "seaborn>=0.13.0"

# ── Notebook ─────────────────────────────────────────────────────────────────
pip install \
    "ipykernel>=6.29.0" \
    "ipywidgets>=8.1.0" \
    "jupyter>=1.0.0"

# ── Quick smoke test ─────────────────────────────────────────────────────────
echo ""
echo "=== Verifying installs ==="
python3 -c "
import torch, torchvision, cv2, ultralytics, albumentations, sklearn
print(f'  torch        {torch.__version__}   CUDA available: {torch.cuda.is_available()}')
print(f'  torchvision  {torchvision.__version__}')
print(f'  opencv       {cv2.__version__}')
print(f'  ultralytics  {ultralytics.__version__}')
print(f'  albumentations {albumentations.__version__}')
print(f'  scikit-learn {sklearn.__version__}')
"
echo ""
echo "=== All done! ==="
echo "Launch notebook:  jupyter lab notebooks/solar_thermal_detection.ipynb"
