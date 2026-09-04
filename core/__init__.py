"""AgriNexus AI core package.

Rule: nothing under ``core/`` imports Streamlit. Engines return plain data
objects that the UI layer (``ui/``) renders and the Copilot reasons over.
"""
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PACKAGE_ROOT / "data"
KB_DIR = DATA_DIR / "knowledge_base"
CONFIG_DIR = DATA_DIR / "config"
DEMO_FARMS_DIR = DATA_DIR / "demo_farms"

__all__ = ["PACKAGE_ROOT", "DATA_DIR", "KB_DIR", "CONFIG_DIR", "DEMO_FARMS_DIR"]
