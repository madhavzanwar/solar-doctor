# Installation Guide

## Prerequisites

- Python `3.10+`
- `pip`
- Model weights at `ml/checkpoints/best.pt`
- Optional GPU: CUDA-capable environment for `device=0`

## Clone and install

```bash
git clone <repo-url> AxalonSystems
cd AxalonSystems

# ML dependencies
pip install -r ml/requirements.txt

# Platform dependencies
pip install -r requirements_platform.txt

# Register local packages as axalon + ml
pip install -e .
```

## System libraries for PDF reports

PDF generation uses WeasyPrint.

```bash
# Ubuntu / Debian
sudo apt install -y libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0

# macOS
brew install pango
```

## Verify installation

```bash
python -c "import axalon; print('axalon package OK')"
python -c "from axalon.api.app import app; print(app.title)"
python -c "from ml.src.utils import CANONICAL_CLASSES; print(len(CANONICAL_CLASSES))"
```

Optional service check:

```bash
./run.sh status
```

## Model weights

Expected path:

```bash
ml/checkpoints/best.pt
```

This repo treats that file as the primary YOLOv8s thermal model.

## Common startup commands

```bash
./run.sh setup
./run.sh doctor
./run.sh api
./run.sh dashboard
./run.sh both
```

Alternative direct entrypoints:

```bash
python main.py api
python main.py dashboard
```

## Test the install

```bash
PYTHONSAFEPATH=1 python -m pytest
```

`PYTHONSAFEPATH=1` is recommended because the repository contains a local `platform/` directory and the test configuration is set up to avoid shadowing Python's standard-library `platform` module.
