"""Settings from environment variables."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_XLS = DATA_DIR / "raw" / "superstore.xls"
TABLEAU_DIR = DATA_DIR / "tableau"
SQL_DIR = ROOT / "sql"
RESULTS_DIR = ROOT / "results"
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/retailpulse")
SOURCE_URL = "https://public.tableau.com/app/sample-data/sample_-_superstore.xls"
