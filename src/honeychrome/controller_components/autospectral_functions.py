"""
autospectral_functions.py
--------------------------
AutoSpectral AF extraction for Honeychrome.

Public API
----------
get_af_spectra(unstained_raw, fluor_spectra, n_clusters, similarity_threshold)
    Identifies AF spectral profiles from an unstained sample using KMeans
    clustering.  Returns an (n_af, n_channels) ndarray of L-inf-normalised
    AF spectra, with the population mean prepended as row 0.

apply_af_unmixing(raw_data, precomputed, af_spectra)
    Per-cell AF extraction and OLS unmixing for fluorescence channels only.

precompute_af_matrices(fluor_spectra, af_spectra)
    Precomputes projection matrices; call once after spectral process refresh
    and cache the result on the controller.

apply_af_transfer(raw_event_data, transfer_matrix, af_precomputed, af_spectra, settings)
    Assembles a full unmixed event array, overwriting fluorescence columns
    with AF-corrected OLS values.

save_af_profile_csv(af_spectra, channel_names, source_fcs_path, experiment_dir)
    Saves an AF profile as a CSV file in the experiment's AutoSpectral folder.
    Returns the profile name (str) used as the key in experiment.process['af_profiles'].

load_af_profile_csv(csv_path)
    Loads an AF profile from a CSV file previously saved by save_af_profile_csv.
    Returns (profile_name, spectra_ndarray, channel_names).
"""

import numpy as np
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Sub-folder inside the experiment directory where CSV files are stored
AF_SUBDIR = 'AutoSpectral'


# ---------------------------------------------------------------------------
# CSV save / load
# ---------------------------------------------------------------------------

def save_af_profile_csv(
    af_spectra: np.ndarray,
    channel_names: list,
    source_fcs_path: str,
    experiment_dir: Path,
) -> str:
    """
    Save an AF profile to CSV and return the profile name.

    The CSV file has:
      - Column headers: 'AF_index', then one column per detector
      - Rows: 0 = population mean, 1..n = cluster AF spectra

    File name: "<stem of source_fcs_path> AutoSpectral AF.csv"
    Location:  <experiment_dir>/AutoSpectral/

    Parameters
    ----------
    af_spectra : ndarray, shape (n_af, n_channels)
    channel_names : list[str]
        Detector names for the fluorescence channels, in column order.
    source_fcs_path : str
        Relative (or absolute) path of the FCS file used to extract the profile.
        Only the stem is used for naming.
    experiment_dir : Path
        Root experiment directory (contains the .kit file's sibling folder).

    Returns
    -------
    str
        Profile name, e.g. "Spleen_unstained AutoSpectral AF".
        This is the key used in experiment.process['af_profiles'].
    """
    import pandas as pd

    stem = Path(source_fcs_path).stem
    profile_name = f'{stem} AutoSpectral AF'

    out_dir = Path(experiment_dir) / AF_SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f'{profile_name}.csv'

    n_af = af_spectra.shape[0]
    row_labels = ['mean'] + [str(i) for i in range(1, n_af)]

    df = pd.DataFrame(af_spectra, columns=channel_names)
    df.insert(0, 'AF_index', row_labels)
    df.to_csv(csv_path, index=False)

    logger.info(f'AutoSpectral: saved AF profile "{profile_name}" to {csv_path}')
    return profile_name


def load_af_profile_csv(csv_path: str | Path):
    """
    Load an AF profile from a CSV file.

    Parameters
    ----------
    csv_path : str or Path

    Returns
    -------
    tuple (profile_name, af_spectra, channel_names)
        profile_name : str — derived from the file stem
        af_spectra   : ndarray, shape (n_af, n_channels)
        channel_names: list[str]
    """
    import pandas as pd

    csv_path = Path(csv_path)
    profile_name = csv_path.stem  # e.g. "Spleen_unstained AutoSpectral AF"

    df = pd.read_csv(csv_path)
    channel_names = [c for c in df.columns if c != 'AF_index']
    af_spectra = df[channel_names].to_numpy(dtype=float)

    logger.info(
        f'AutoSpectral: loaded AF profile "{profile_name}" '
        f'({af_spectra.shape[0]} spectra, {af_spectra.shape[1]} channels) '
        f'from {csv_path}'
    )
    return profile_name, af_spectra, channel_names


# ---------------------------------------------------------------------------
# Precomputation (run once per spectral process / per-sample AF assignment)
# ---------------------------------------------------------------------------

def precompute_af_matrices(fluor_spectra: np.ndarray, af_spectra: np.ndarray) -> dict:
    """
    Precompute the matrices needed for per-cell AF unmixing.

    Parameters
    ----------
    fluor_spectra : ndarray, shape (n_fluors, n_channels)
        L-infinity-normalised fluorophore spectral profiles.
    af_spectra : ndarray, shape (n_af, n_channels)
        AF spectral profiles from get_af_spectra().

    Returns
    -------
    dict with keys:
        P           : (n_fluors, n_channels)
        S_t         : (n_channels, n_fluors)
        v_library   : (n_fluors, n_af)
        r_library   : (n_channels, n_af)
        r_dots      : (n_af,)
    """
    P = np.linalg.solve(fluor_spectra @ fluor_spectra.T, fluor_spectra)
    S_t = fluor_spectra.T
    AF_t = af_spectra.T

    v_library = P @ AF_t
    r_library = AF_t - S_t @ v_library
    r_dots = np.einsum('ij,ij->j', r_library, r_library)
    r_dots = np.where(r_dots < 1e-20, 1e-20, r_dots)

    return {
        'P': P,
        'S_t': S_t,
        'v_library': v_library,
        'r_library': r_library,
        'r_dots': r_dots,
    }


def combine_af_precomputed(precomputed_list: list) -> dict:
    """
    Combine a list of per-profile precomputed dicts into one combined dict.

    Because all the column-wise arrays (v_library, r_library, r_dots) are
    independent across profiles, combination is simply np.hstack — no further
    matrix algebra is needed.  P and S_t are identical for all profiles (they
    depend only on fluor_spectra) so we take them from the first entry.

    Parameters
    ----------
    precomputed_list : list of dict
        Each element is the output of precompute_af_matrices() for one profile.
        Must be non-empty.

    Returns
    -------
    dict — same structure as precompute_af_matrices() output, but with
    v_library, r_library, and r_dots spanning all profiles combined.
    """
    if len(precomputed_list) == 1:
        return precomputed_list[0]

    return {
        'P':         precomputed_list[0]['P'],        # (n_fluors, n_channels) — shared
        'S_t':       precomputed_list[0]['S_t'],      # (n_channels, n_fluors) — shared
        'v_library': np.hstack([d['v_library'] for d in precomputed_list]),
        'r_library': np.hstack([d['r_library'] for d in precomputed_list]),
        'r_dots':    np.concatenate([d['r_dots'] for d in precomputed_list]),
    }


# ---------------------------------------------------------------------------
# Helper: assemble full unmixed event array
# ---------------------------------------------------------------------------

def apply_af_transfer(raw_event_data, transfer_matrix, af_precomputed, af_spectra, settings,
                      filtered_fl_ids_raw=None):
    """
    Assemble a full unmixed event array with AF-corrected fluorescence columns.
    Scatter, time, and event_id columns come from the standard transfer_matrix path.
    """
    from honeychrome.controller_components.functions import apply_transfer_matrix

    raw_settings = settings['raw']
    unmixed_settings = settings['unmixed']

    if filtered_fl_ids_raw is not None:
        fl_ids_raw = np.array(filtered_fl_ids_raw)
    else:
        fl_ids_raw = np.array(raw_settings['fluorescence_channel_ids'])
        
    fl_ids_unmixed = np.array(unmixed_settings['fluorescence_channel_ids'])

    unmixed = raw_event_data @ transfer_matrix

    raw_fl = raw_event_data[:, fl_ids_raw]
    result = apply_af_unmixing(raw_fl, af_precomputed, af_spectra)
    unmixed[:, fl_ids_unmixed] = result['unmixed']

    return unmixed


# ---------------------------------------------------------------------------
# Per-sample unmixing
# ---------------------------------------------------------------------------

def apply_af_unmixing(
    raw_data: np.ndarray,
    precomputed: dict,
    af_spectra: np.ndarray,
    chunk_size: int = 50_000,
) -> dict:
    """
    Per-cell AF extraction and OLS unmixing (fluorescence channels only).

    Parameters
    ----------
    raw_data : ndarray, shape (n_cells, n_channels)
        Raw fluorescence channels only.
    precomputed : dict
        Output of precompute_af_matrices().
    af_spectra : ndarray, shape (n_af, n_channels)
    chunk_size : int
        Cells processed per batch.

    Returns
    -------
    dict with keys:
        unmixed  : ndarray (n_cells, n_fluors) — AF-corrected OLS abundances
        af_scale : ndarray (n_cells,)          — scale factor of best-fit AF
        af_idx   : ndarray (n_cells,)          — 1-based index of best-fit AF
    """
    P         = precomputed['P']           # (n_fluors, n_channels)
    v_library = precomputed['v_library']   # (n_fluors, n_af)
    r_library = precomputed['r_library']   # (n_channels, n_af)
    r_dots    = precomputed['r_dots']      # (n_af,)

    n_cells, n_channels = raw_data.shape
    n_fluors = P.shape[0]
    n_af = af_spectra.shape[0]

    unmixed_out = np.empty((n_cells, n_fluors), dtype=np.float64)
    af_scale_out = np.empty(n_cells, dtype=np.float64)
    af_idx_out = np.empty(n_cells, dtype=np.int32)

    for start in range(0, n_cells, chunk_size):
        end = min(start + chunk_size, n_cells)
        chunk = raw_data[start:end].astype(np.float64)   # (B, n_channels)
        B = end - start

        # Initial OLS unmix
        init_fluor = chunk @ P.T   # (B, n_fluors)

        # For each AF candidate j: scale k_j = (cell · r_j) / r_dots_j
        # shape: (B, n_af)
        r_dots_chunk = (chunk @ r_library) / r_dots[np.newaxis, :]   # k_j per cell

        # L1 error: |init_fluor - k_j * v_library_j|  summed over fluors
        # init_fluor: (B, n_fluors), v_library: (n_fluors, n_af)
        # error[b, j] = sum_f |init_fluor[b,f] - k[b,j] * v_library[f,j]|
        error = np.sum(
            np.abs(
                init_fluor[:, :, np.newaxis]                      # (B, n_fluors, 1)
                - r_dots_chunk[:, np.newaxis, :] * v_library[np.newaxis, :, :]  # (B, n_fluors, n_af)
            ),
            axis=1,
        )   # (B, n_af)

        best_j = np.argmin(error, axis=1)   # (B,)
        best_k = r_dots_chunk[np.arange(B), best_j]   # (B,)

        # Subtract best AF from raw, re-unmix residual
        best_af = af_spectra[best_j]   # (B, n_channels)
        residual = chunk - best_k[:, np.newaxis] * best_af   # (B, n_channels)
        final_unmixed = residual @ P.T   # (B, n_fluors)

        unmixed_out[start:end] = final_unmixed
        af_scale_out[start:end] = best_k
        af_idx_out[start:end] = best_j + 1   # 1-based, matching R convention

    return {
        'unmixed': unmixed_out,
        'af_scale': af_scale_out,
        'af_idx': af_idx_out,
    }


# ---------------------------------------------------------------------------
# AF spectra identification (training step)
# ---------------------------------------------------------------------------

def get_af_spectra(
    unstained_raw: np.ndarray,
    fluor_spectra: np.ndarray,
    n_clusters: int = 100,
    similarity_threshold: float = 0.995,
    min_cells: int = 200,
    random_state: int = 42,
) -> np.ndarray:
    """
    Identify AF spectral profiles from an unstained sample.

    Parameters
    ----------
    unstained_raw : ndarray, shape (n_cells, n_channels)
        Raw fluorescence channel data from the unstained control.
    fluor_spectra : ndarray, shape (n_fluors, n_channels)
        L-infinity-normalised fluorophore spectra (from spectral model).
    n_clusters : int
        Target KMeans cluster count (capped by sample size).
    similarity_threshold : float
        Cosine similarity above which an AF candidate is discarded as
        likely fluorophore contamination.
    min_cells : int
        Minimum number of events required; raises ValueError if not met.
    random_state : int
        Random seed for reproducibility.

    Returns
    -------
    ndarray, shape (n_af, n_channels)
        Row 0 is the population mean; rows 1..n are cluster centroids that
        passed the contamination QC filter.
    """
    from sklearn.cluster import KMeans, MiniBatchKMeans

    n_cells, n_channels = unstained_raw.shape

    if n_cells < min_cells:
        raise ValueError(
            f'Insufficient cells in unstained sample: {n_cells} < {min_cells}. '
            f'Provide a larger unstained control.'
        )

    n_clusters = max(2, min(n_clusters, n_cells // 3))
    logger.info(f'get_af_spectra: n_cells={n_cells}, n_clusters={n_clusters}')

    # Initial OLS unmix (no AF) for clustering input
    P = np.linalg.solve(fluor_spectra @ fluor_spectra.T, fluor_spectra)
    unmixed_no_af = unstained_raw @ P.T

    cluster_input = np.concatenate([unstained_raw, unmixed_no_af], axis=1)

    if n_cells > 200_000:
        km = MiniBatchKMeans(n_clusters=n_clusters, random_state=random_state, n_init='auto')
    else:
        km = KMeans(n_clusters=n_clusters, random_state=random_state, n_init='auto')

    km.fit(cluster_input)

    centres_spectral = km.cluster_centers_[:, :n_channels]

    # L-infinity normalise
    peak_vals = np.abs(centres_spectral).max(axis=1, keepdims=True)
    peak_vals = np.where(peak_vals < 1e-12, 1.0, peak_vals)
    af_candidates = centres_spectral / peak_vals
    af_candidates = af_candidates[~np.isnan(af_candidates).any(axis=1)]

    # Prepend population mean
    mean_af = af_candidates.mean(axis=0)
    mean_peak = np.abs(mean_af).max()
    if mean_peak > 1e-12:
        mean_af = mean_af / mean_peak
    af_spectra = np.vstack([mean_af[np.newaxis, :], af_candidates])

    # Contamination QC
    af_spectra = _remove_fluorophore_contaminants(af_spectra, fluor_spectra, similarity_threshold)

    logger.info(f'get_af_spectra: returning {af_spectra.shape[0]} AF spectra after QC')
    return af_spectra


def _remove_fluorophore_contaminants(
    af_spectra: np.ndarray,
    fluor_spectra: np.ndarray,
    threshold: float,
) -> np.ndarray:
    """
    Remove AF candidates whose cosine similarity to any known fluorophore
    exceeds *threshold*.  Row 0 (population mean) is always kept.
    """
    if af_spectra.shape[0] == 0:
        return af_spectra

    # Normalise for cosine similarity
    af_norms = np.linalg.norm(af_spectra, axis=1, keepdims=True)
    af_norms = np.where(af_norms < 1e-12, 1.0, af_norms)
    af_unit = af_spectra / af_norms

    fl_norms = np.linalg.norm(fluor_spectra, axis=1, keepdims=True)
    fl_norms = np.where(fl_norms < 1e-12, 1.0, fl_norms)
    fl_unit = fluor_spectra / fl_norms

    # cosine similarity matrix: (n_af, n_fluors)
    cos_sim = af_unit @ fl_unit.T
    max_sim = cos_sim.max(axis=1)   # worst-case similarity per AF candidate

    # Always keep row 0 (mean)
    keep = max_sim < threshold
    keep[0] = True

    n_removed = (~keep).sum()
    if n_removed:
        logger.info(
            f'_remove_fluorophore_contaminants: removed {n_removed} '
            f'AF candidates (cosine similarity >= {threshold:.2f})'
        )

    return af_spectra[keep]
