# label_matching.py
import re
import csv
from pathlib import Path
from importlib.resources import files   # Python 3.9+; use importlib_resources backport if needed

import logging
logger = logging.getLogger(__name__)


def _load_csv(path: Path) -> list[dict]:
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def _best_match(name: str, database: list[dict], canonical_col: str, synonym_cols: list[str]) -> str | None:
    """
    Return the canonical value from `canonical_col` for the longest synonym
    that appears as a word-boundary match inside `name`.
    Returns None if nothing matches.
    """
    delim = r'(?<![A-Za-z0-9\-]){}(?![A-Za-z0-9\-])'
    best_text = ''
    best_canonical = None

    for row in database:
        for col in [canonical_col] + synonym_cols:
            val = row.get(col, '') or ''
            if not val:
                continue
            escaped = re.escape(val)
            escaped = escaped.replace(r'\ ', r'\s*')   # mirror R's gsub(" ", "\\s*", ...)
            pattern = delim.format(escaped)
            if re.search(pattern, name, flags=re.IGNORECASE):
                if len(val) > len(best_text):
                    best_text = val
                    best_canonical = row[canonical_col]

    return best_canonical


def match_fluorophore(name: str, fluorophore_db: list[dict]) -> str | None:
    """Return the canonical fluorophore name, or None."""
    synonym_cols = [f'synonym{i}' for i in range(1, 5)]
    result = _best_match(name, fluorophore_db, 'fluorophore', synonym_cols)
    if result:
        logger.debug(f'Fluorophore match: "{name}" -> "{result}"')
    else:
        logger.debug(f'No fluorophore match for: "{name}"')
    return result


def match_marker(name: str, marker_db: list[dict]) -> str | None:
    """Return the canonical marker/antigen name, or None."""
    synonym_cols = [f'synonym{i}' for i in range(1, 10)]
    result = _best_match(name, marker_db, 'marker', synonym_cols)
    if result:
        logger.debug(f'Marker match: "{name}" -> "{result}"')
    else:
        logger.debug(f'No marker match for: "{name}"')
    return result

_DATA_DIR = Path(__file__).parent.parent / 'data'

_fluorophore_db: list[dict] | None = None
_marker_db: list[dict] | None = None


def get_fluorophore_db() -> list[dict]:
    global _fluorophore_db
    if _fluorophore_db is None:
        _fluorophore_db = _load_csv(_DATA_DIR / 'fluorophore_database.csv')
    return _fluorophore_db


def get_marker_db() -> list[dict]:
    global _marker_db
    if _marker_db is None:
        _marker_db = _load_csv(_DATA_DIR / 'marker_database.csv')
    return _marker_db