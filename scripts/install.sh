#!/usr/bin/env bash
set -euo pipefail
cd /workspace/famillejerichotache-
python3 -m venv /workspace/family-venv
/workspace/family-venv/bin/python -m pip install -r requirements.txt
/workspace/family-venv/bin/python -m unittest discover -s tests -q
