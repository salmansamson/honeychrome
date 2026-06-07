import numpy as np
import pandas as pd
from functools import lru_cache
from pathlib import Path

_CYTOMETER_TO_CSV = {
    'Aurora':         'Aurora_spectral_reference_library.csv',
    'NorthernLights': 'Aurora_spectral_reference_library.csv',
    'Discover':       'Discover_spectral_reference_library.csv',
    'ID7000':         'ID7000_spectral_reference_library.csv',
    'Opteon':         'Opteon_spectral_reference_library.csv',
    'Mosaic':         'Mosaic_spectral_reference_library.csv',
    'Xenith':         'Xenith_spectral_reference_library.csv',
    'A5SE':           'Symphony_spectral_reference_library.csv',
}

@lru_cache(maxsize=8)
def load_reference_library(cytometer_key: str) -> pd.DataFrame | None:
    """Load and cache spectral reference CSV; rows normalised to [0, 1]."""
    csv_name = _CYTOMETER_TO_CSV.get(cytometer_key)
    if csv_name is None:
        return None
    data_dir = Path(__file__).parent.parent / 'data'
    path = data_dir / csv_name
    if not path.exists():
        return None
    df = pd.read_csv(path, index_col=0)
    row_max = df.max(axis=1).replace(0, np.nan)
    return df.div(row_max, axis=0).fillna(0)


def cosine_similarity_to_reference(
    spectrum: np.ndarray,
    channel_names: list[str],
    fluorophore: str,
    cytometer_key: str,
) -> float | None:
    ref = load_reference_library(cytometer_key)
    if ref is None:
        return None
    if fluorophore not in ref.index:
        return None
    common = [c for c in channel_names if c in ref.columns]
    if not common:
        return None
    v_exp = np.array([spectrum[channel_names.index(c)] for c in common], dtype=float)
    v_ref = ref.loc[fluorophore, common].values.astype(float)  # type: ignore[index]
    denom = (np.linalg.norm(v_exp) * np.linalg.norm(v_ref)) + 1e-9
    cs = float(np.dot(v_exp, v_ref) / denom)
    return cs