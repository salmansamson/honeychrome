"""
autospectral_functions.py
--------------------------
AutoSpectral AF extraction for Honeychrome.

Public API
----------
get_af_spectra(unstained_raw, fluor_spectra, n_clusters)
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

try:
    from honeychrome.controller_components.af_kernel_wrapper import (
        joint_cov_l1_argmin as _c_joint_cov_l1_argmin,
        AF_KERNEL_AVAILABLE,
    )
except ImportError:
    _c_joint_cov_l1_argmin = None
    AF_KERNEL_AVAILABLE    = False


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


def precompute_joint_cov_extras(precomputed: dict, af_spectra: np.ndarray) -> dict:
    """
    Compute covariance-based fluorophore error weights for joint-cov L1 scoring.
    Call once after precompute_af_matrices(); cache alongside af_precomputed.
    """
    P = precomputed['P']   # (n_fluors, n_channels)
    n_channels = af_spectra.shape[1]
    af_cov = (np.cov(af_spectra, rowvar=False)
              if af_spectra.shape[0] > 1
              else np.zeros((n_channels, n_channels)))
    fluor_cov = P @ af_cov @ P.T
    af_error_weights = np.sqrt(np.abs(np.diag(fluor_cov)))
    if af_error_weights.max() < 1e-12:
        af_error_weights = np.ones(P.shape[0])
    return {'af_error_weights': af_error_weights}


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
                      filtered_fl_ids_raw=None, spillover=None):
    """
    Assemble a full unmixed event array with AF-corrected fluorescence columns.
    Scatter, time, and event_id columns come from the standard transfer_matrix path.

    The AF unmixing (apply_af_unmixing) produces abundances in plain OLS fluorophore
    space. If a spillover matrix is provided, compensation (inv(spillover).T) is applied
    to those fluorescence columns so the result matches the compensated transfer_matrix
    path. The transpose matches spillover's row-spills-into-column convention to the
    column-vector multiplication used below (see controller.py::initialise_transfer_matrix).
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
    af_unmixed_fl = result['unmixed']  # (n_cells, n_fluors) — plain OLS space

    if spillover is not None:
        compensation = np.linalg.inv(np.array(spillover)).T
        af_unmixed_fl = (compensation @ af_unmixed_fl.T).T

    unmixed[:, fl_ids_unmixed] = af_unmixed_fl

    return {
        'unmixed': unmixed,
        'af_scale': result['af_scale'],   # (n_cells,)
        'af_idx':   result['af_idx'],     # (n_cells,)
    }


# ---------------------------------------------------------------------------
# Per-sample unmixing
# ---------------------------------------------------------------------------

# after
def apply_af_unmixing(
    raw_data: np.ndarray,
    precomputed: dict,
    af_spectra: np.ndarray,
    chunk_size: int = 50_000,
) -> dict:
    """
    Per-cell AF extraction and OLS unmixing (fluorescence channels only).

    When the compiled C kernel is available (AF_KERNEL_AVAILABLE), uses joint
    covariance-weighted L1 fluorophore × L2 residual scoring, parallelised
    over cells with OpenMP.  Falls back to plain NumPy L1 if the extension
    is absent or if af_error_weights is missing from precomputed.

    Parameters
    ----------
    raw_data    : (n_cells, n_channels) raw fluorescence only
    precomputed : dict from precompute_af_matrices(), optionally extended
                  with precompute_joint_cov_extras() merged in
    af_spectra  : (n_af, n_channels)
    chunk_size  : cells per processing batch

    Returns
    -------
    dict with keys: unmixed (n_cells, n_fluors), af_scale (n_cells,),
                    af_idx (n_cells,) 1-based
    """
    P         = precomputed['P']           # (n_fluors, n_channels)
    v_library = precomputed['v_library']   # (n_fluors, n_af)
    r_library = precomputed['r_library']   # (n_channels, n_af)
    r_dots    = precomputed['r_dots']      # (n_af,)
    S_t       = precomputed['S_t']         # (n_channels, n_fluors)

    w = precomputed.get('af_error_weights')
    use_c = AF_KERNEL_AVAILABLE and w is not None

    n_cells, _ = raw_data.shape
    n_fluors   = P.shape[0]

    unmixed_out  = np.empty((n_cells, n_fluors), dtype=np.float64)
    af_scale_out = np.empty(n_cells,             dtype=np.float64)
    af_idx_out   = np.empty(n_cells,             dtype=np.int32)

    if use_c:
        w       = np.ascontiguousarray(w, dtype=np.float64)
        v_lib_c = np.ascontiguousarray(v_library, dtype=np.float64)

    for start in range(0, n_cells, chunk_size):
        end   = min(start + chunk_size, n_cells)
        chunk = np.ascontiguousarray(raw_data[start:end], dtype=np.float64)
        B     = end - start

        init_fluor = chunk @ P.T
        K          = (chunk @ r_library) / r_dots[np.newaxis, :]

        if use_c:
            # L2 residual term — vectorised NumPy
            init_fluor_nn = np.where(init_fluor < 0.0, 0.0, init_fluor)
            resid_base    = chunk - init_fluor_nn @ S_t.T
            rb_sq         = np.sum(resid_base ** 2, axis=1)
            rb_rl         = resid_base @ r_library
            er_sq         = (rb_sq[:, np.newaxis]
                             - 2.0 * K * rb_rl
                             + K ** 2 * r_dots[np.newaxis, :])
            e_resid      = np.ascontiguousarray(np.sqrt(np.maximum(er_sq, 0.0)))
            base_e_resid = np.sqrt(rb_sq) + 1e-6
            base_e_fluor = (np.sum(w[np.newaxis, :] * np.abs(init_fluor), axis=1)
                            + 1e-6)

            # C kernel: L1 fluor scoring + argmin, OpenMP-parallel
            best_j = _c_joint_cov_l1_argmin(
                np.ascontiguousarray(init_fluor),
                np.ascontiguousarray(K),
                v_lib_c,
                w,
                np.ascontiguousarray(base_e_fluor),
                e_resid,
                np.ascontiguousarray(base_e_resid),
            )
        else:
            # NumPy fallback: plain L1, 3D temporary
            error = np.sum(
                np.abs(
                    init_fluor[:, :, np.newaxis]
                    - K[:, np.newaxis, :] * v_library[np.newaxis, :, :]
                ),
                axis=1,
            )
            best_j = np.argmin(error, axis=1)

        best_k   = K[np.arange(B), best_j]
        best_af  = af_spectra[best_j]
        residual = chunk - best_k[:, np.newaxis] * best_af
        unmixed_out[start:end]  = residual @ P.T
        af_scale_out[start:end] = best_k
        af_idx_out[start:end]   = best_j + 1

    return {'unmixed': unmixed_out, 'af_scale': af_scale_out, 'af_idx': af_idx_out}


# ---------------------------------------------------------------------------
# AF spectra identification (training step)
# ---------------------------------------------------------------------------

def _cosine_similarity_matrix(a: np.ndarray) -> np.ndarray:
    """
    Compute pairwise cosine similarity for rows of a.
    Returns an (n, n) matrix in [-1, 1].
    """
    norms = np.linalg.norm(a, axis=1, keepdims=True)
    norms = np.where(norms < 1e-12, 1.0, norms)
    a_norm = a / norms
    return a_norm @ a_norm.T


def _deduplicate_spectra(
    spectra: np.ndarray,
    cosine_threshold: float = 0.99,
) -> np.ndarray:
    """
    Greedy cosine-similarity deduplication.

    Iterates through rows in order, keeping a row only if its cosine
    similarity to every already-kept row is below cosine_threshold.

    Parameters
    ----------
    spectra : ndarray, shape (n, n_channels)
        L-inf-normalised spectra.
    cosine_threshold : float
        Rows more similar than this to any kept row are dropped.

    Returns
    -------
    ndarray, shape (m, n_channels), m <= n
    """
    if len(spectra) == 0:
        return spectra

    sim = _cosine_similarity_matrix(spectra)
    kept = []
    for i in range(len(spectra)):
        if all(sim[i, j] < cosine_threshold for j in kept):
            kept.append(i)
    return spectra[kept]


def _qc_af_spectra(
    af_spectra: np.ndarray,
    fluor_spectra: np.ndarray,
    cosine_threshold: float = 0.99,
) -> np.ndarray:
    """
    Remove any AF spectrum whose cosine similarity to any fluorophore
    spectrum exceeds cosine_threshold — these are likely contamination
    from single-stained controls in the unstained sample.

    Parameters
    ----------
    af_spectra : ndarray, shape (n_af, n_channels)
    fluor_spectra : ndarray, shape (n_fluors, n_channels)
    cosine_threshold : float

    Returns
    -------
    ndarray — filtered af_spectra (may be shorter than input)
    """
    if len(af_spectra) == 0:
        return af_spectra

    # Normalise both sets
    def _row_normalise(m):
        norms = np.linalg.norm(m, axis=1, keepdims=True)
        norms = np.where(norms < 1e-12, 1.0, norms)
        return m / norms

    af_norm    = _row_normalise(af_spectra)
    fluor_norm = _row_normalise(fluor_spectra)

    # sim[i, j] = cosine similarity of af_spectra[i] to fluor_spectra[j]
    sim = af_norm @ fluor_norm.T   # (n_af, n_fluors)
    contaminated = (sim >= cosine_threshold).any(axis=1)
    n_removed = contaminated.sum()
    if n_removed:
        logger.warning(
            f'get_af_spectra: removed {n_removed} AF spectrum/spectra '
            f'with cosine similarity >= {cosine_threshold} to a fluorophore '
            f'(likely control contamination in unstained sample).'
        )
    return af_spectra[~contaminated]

def _filter_contaminant_events(
    event_mat: np.ndarray,
    spectra_mat: np.ndarray,
    threshold: float = 0.99,
) -> np.ndarray:
    """
    Return a boolean mask (True = keep) for events whose cosine similarity
    to every fluorophore spectrum is below threshold.

    More sensitive than post-clustering centroid QC: a small number of
    contaminating events will not dominate an entire cluster node.

    Parameters
    ----------
    event_mat   : ndarray (n_events, n_channels)
    spectra_mat : ndarray (n_fluors, n_channels)
    threshold   : float

    Returns
    -------
    ndarray, bool, shape (n_events,)
    """
    event_norms = np.sqrt(np.sum(event_mat ** 2, axis=1)) + 1e-9  # (n_events,)
    keep = np.ones(len(event_mat), dtype=bool)

    for spec in spectra_mat:
        spec_norm = np.sqrt(np.dot(spec, spec)) + 1e-9
        dots = event_mat @ spec          # (n_events,)
        cs = dots / (event_norms * spec_norm)
        keep &= cs < threshold
        if not keep.any():
            break

    return keep


def get_af_spectra(
    unstained_raw: np.ndarray,
    fluor_spectra: np.ndarray,
    n_clusters: int = 100,
    min_cells: int = 200,
    random_state: int = 42,
    cosine_threshold: float = 0.99,
    refine: bool = True,
    problem_quantile: float = 0.99,
    contaminant_threshold: float = 0.99,
) -> np.ndarray:
    """
    Identify AF spectral profiles from an unstained sample.

    Stage 1 — Base spectra
    ----------------------
    KMeans clusters the unstained events in raw+OLS-unmixed space, as before.
    After L-inf normalisation the centroids are deduplicated by cosine
    similarity (threshold cosine_threshold) to remove near-identical profiles
    that cause spurious matching of near-zero events.  A contamination QC
    filter then removes any spectrum resembling a fluorophore.  The population
    mean is prepended as row 0.

    Stage 2 — Refine
    -----------------------------------------
    Runs a first-pass AF unmixing on the unstained sample using the base
    spectra.  Cells whose post-correction fluorophore L2 norm exceeds
    problem_quantile are "problem cells" — inadequately corrected events still
    far from zero.  Their per-channel error is normalised by the AF scale
    factor (spill ratios) and re-clustered.  For each error cluster, modulated
    versions of the contributing base spectra are created:
        updated = base_spec * (1 + median_ratio),  re-normalised L-inf
    These targeted spectra are appended to the base library and the full set
    is passed through contamination QC again.

    Parameters
    ----------
    unstained_raw : ndarray, shape (n_cells, n_channels)
        Raw fluorescence channel data from the unstained control.
    fluor_spectra : ndarray, shape (n_fluors, n_channels)
        L-infinity-normalised fluorophore spectra (from spectral model).
    n_clusters : int
        Target KMeans cluster count for the base stage (capped by sample
        size).  After deduplication the actual count will typically be much
        lower.
    min_cells : int
        Minimum number of events required; raises ValueError if not met.
    random_state : int
        Random seed for reproducibility.
    cosine_threshold : float
        Cosine similarity threshold for deduplicating base spectra.
        Rows more similar than this to any already-kept row are dropped.
        Default 0.99.
    refine : bool
        Whether to run the second-pass refinement stage.  Default False.
    problem_quantile : float
        Quantile of post-correction fluorophore L2 norm used to define
        "problem cells" for the refine stage.  Default 0.99 (top 1%).
    contaminant_threshold : float
        Used twice: (1) per-event pre-clustering filter — events in the
        mean-background-subtracted unstained sample whose cosine similarity
        to any fluorophore spectrum meets or exceeds this value are dropped
        before clustering; (2) post-clustering QC — cosine similarity to a
        fluorophore above which a resulting AF spectrum is considered
        contamination and removed.  Default 0.99.

    Returns
    -------
    ndarray, shape (n_af, n_channels)
        Row 0 is the population mean of the base spectra; subsequent rows
        are deduplicated base spectra and (if refine=True) modulated spectra
        for problem cells.
    """
    from sklearn.cluster import KMeans, MiniBatchKMeans

    n_cells, n_channels = unstained_raw.shape
    n_fluors = fluor_spectra.shape[0]

    if n_cells < min_cells:
        raise ValueError(
            f'Insufficient cells in unstained sample: {n_cells} < {min_cells}. '
            f'Provide a larger unstained control.'
        )

    n_clusters = max(2, min(n_clusters, n_cells // 3))

    # -------------------------------------------------------------------------
    # Stage 1 — Base spectra via KMeans
    # -------------------------------------------------------------------------

    # OLS unmix without AF — used as additional clustering features
    P = np.linalg.solve(fluor_spectra @ fluor_spectra.T, fluor_spectra)
    unmixed_no_af = unstained_raw @ P.T   # (n_cells, n_fluors)

    # Per-event contaminant filter before clustering.
    # Subtract mean background first so the cosine-similarity check targets
    # contamination spikes rather than the baseline AF shape itself.
    sample_mean = unstained_raw.mean(axis=0)
    unstained_orth = unstained_raw - sample_mean[np.newaxis, :]
    keep = _filter_contaminant_events(unstained_orth, fluor_spectra, contaminant_threshold)
    n_removed = int((~keep).sum())
    if n_removed > 0:
        logger.info(
            f'get_af_spectra: removed {n_removed} event(s) prior to clustering '
            f'(cosine similarity >= {contaminant_threshold} to a fluorophore spectrum '
            f'on background-subtracted data)'
        )
    unstained_raw_cl = unstained_raw[keep]
    unmixed_no_af_cl = unmixed_no_af[keep]

    cluster_input = np.concatenate([unstained_raw_cl, unmixed_no_af_cl], axis=1)

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

    # Deduplicate: collapse near-identical spectral shapes
    af_candidates = _deduplicate_spectra(af_candidates, cosine_threshold)
    logger.info(
        f'get_af_spectra: {len(af_candidates)} base spectra after deduplication '
        f'(cosine_threshold={cosine_threshold})'
    )

    # Contamination QC: remove any spectrum resembling a fluorophore
    af_candidates = _qc_af_spectra(af_candidates, fluor_spectra, contaminant_threshold)

    if len(af_candidates) == 0:
        raise ValueError(
            'All AF candidate spectra were removed by contamination QC. '
            'Check whether the unstained sample contains single-stained events.'
        )

    # Prepend population mean of the deduplicated base spectra
    mean_af = af_candidates.mean(axis=0)
    mean_peak = np.abs(mean_af).max()
    if mean_peak > 1e-12:
        mean_af = mean_af / mean_peak
    af_spectra = np.vstack([mean_af[np.newaxis, :], af_candidates])

    logger.info(f'get_af_spectra: {af_spectra.shape[0]} spectra after stage 1')

    # -------------------------------------------------------------------------
    # Stage 2 — Refine: targeted modulation for problem cells
    # -------------------------------------------------------------------------

    if refine:

        # First-pass per-cell unmixing on the unstained sample using base spectra
        precomputed = precompute_af_matrices(fluor_spectra, af_spectra)
        first_pass  = apply_af_unmixing(unstained_raw, precomputed, af_spectra)

        unmixed_fluors = first_pass['unmixed']   # (n_cells, n_fluors)
        af_scale       = first_pass['af_scale']  # (n_cells,)  — scalar k per cell
        af_idx_0based  = first_pass['af_idx'] - 1  # convert to 0-based

        # Error magnitude: L2 norm of fluorophore channels after correction.
        # In an unstained sample any residual fluorophore signal is correction error.
        error_magnitude = np.sqrt(np.sum(unmixed_fluors ** 2, axis=1))  # (n_cells,)

        # Identify problem cells — those still furthest from zero.
        # Step the quantile down in 5% increments until we have enough cells,
        # mirroring the R fallback loop.
        pq = problem_quantile
        while True:
            threshold   = np.quantile(error_magnitude, pq)
            problem_idx = np.where(error_magnitude > threshold)[0]
            problem_n   = len(problem_idx)
            if problem_n >= 500:
                break
            pq -= 0.05
            if pq < 0.5:
                # Accept whatever we have at the 50% mark
                threshold   = np.quantile(error_magnitude, pq)
                problem_idx = np.where(error_magnitude > threshold)[0]
                problem_n   = len(problem_idx)
                break

        if problem_n > 10:
            # Per-channel error for the problem cells.
            # error = residuals + proj_fluor in R; here we use the unmixed
            # fluorophore values directly — in an unstained sample these are
            # purely error (no true fluorophore signal present).
            # Shape: (problem_n, n_fluors)
            fluor_error = unmixed_fluors[problem_idx]

            # Normalise by AF scale to get dimensionless spill ratios,
            # matching R: spill.ratios = error[problem.idx, ] / af.abundance
            af_scale_problem = af_scale[problem_idx]
            af_scale_problem = np.where(
                np.abs(af_scale_problem) < 1e-6, 1e-6, af_scale_problem
            )
            spill_ratios = fluor_error / af_scale_problem[:, np.newaxis]  # (problem_n, n_fluors)

            # Re-cluster the spill ratios to find distinct error patterns
            error_som_dim = max(2, int(np.floor(np.sqrt(problem_n / 3))))
            n_error_clusters = error_som_dim ** 2

            if problem_n > 200_000:
                km_err = MiniBatchKMeans(
                    n_clusters=n_error_clusters, random_state=random_state, n_init='auto'
                )
            else:
                km_err = KMeans(
                    n_clusters=n_error_clusters, random_state=random_state, n_init='auto'
                )
            km_err.fit(spill_ratios)
            error_labels = km_err.labels_   # (problem_n,)

            # For each error cluster: find contributing base AF indices,
            # compute the median spill ratio, modulate each contributing spectrum.
            modulated = []
            for cl in np.unique(error_labels):
                cl_mask    = error_labels == cl
                cl_ratios  = spill_ratios[cl_mask]            # (cl_n, n_fluors)
                global_idx = problem_idx[cl_mask]

                # Median correction pattern for this cluster
                median_ratio = np.median(cl_ratios, axis=0)   # (n_fluors,)

                # Which base AF spectra were assigned to these problem cells?
                contributing = np.unique(af_idx_0based[global_idx])

                for base_idx in contributing:
                    base_spec = af_spectra[base_idx]                        # (n_channels,)
                    # The spill_ratios are in fluorophore space (n_fluors),
                    # but we need to modulate in detector space (n_channels).
                    # Project the median ratio back to detector space via S_t.
                    # ratio_detector = S_t @ median_ratio  (n_channels,)
                    ratio_detector = fluor_spectra.T @ median_ratio          # (n_channels,)
                    updated = base_spec * (1.0 + ratio_detector)
                    peak = np.abs(updated).max()
                    if peak > 1e-12:
                        updated = updated / peak
                    if not np.isnan(updated).any():
                        modulated.append(updated)

            if modulated:
                modulated_arr = np.vstack(modulated)   # (n_modulated, n_channels)

                # Step 1: deduplicate modulated spectra against each other
                modulated_arr = _deduplicate_spectra(modulated_arr, cosine_threshold)

                # Step 2: drop any modulated spectrum too similar to an
                # already-kept base spectrum.
                # Build cross-similarity: (n_modulated, n_af_existing)
                def _row_normalise(m):
                    norms = np.linalg.norm(m, axis=1, keepdims=True)
                    norms = np.where(norms < 1e-12, 1.0, norms)
                    return m / norms

                mod_norm      = _row_normalise(modulated_arr)
                existing_norm = _row_normalise(af_spectra)
                cross_sim     = mod_norm @ existing_norm.T   # (n_modulated, n_af_existing)
                novel_mask    = (cross_sim < cosine_threshold).all(axis=1)
                modulated_arr = modulated_arr[novel_mask]

                n_novel = len(modulated_arr)
                logger.info(
                    f'get_af_spectra refine: {n_novel} novel modulated spectra after '
                    f'deduplication (dropped {len(modulated) - n_novel} redundant)'
                )

                if n_novel > 0:
                    af_spectra = np.vstack([af_spectra, modulated_arr])

                    # NA guard
                    af_spectra = af_spectra[~np.isnan(af_spectra).any(axis=1)]

                    # Contamination QC on the expanded set
                    af_spectra = _qc_af_spectra(
                        af_spectra, fluor_spectra, contaminant_threshold
                    )

                    if len(af_spectra) == 0:
                        raise ValueError(
                            'All AF spectra were removed by contamination QC '
                            'after refine stage.'
                        )
                else:
                    logger.info(
                        'get_af_spectra refine: all modulated spectra were '
                        'duplicates of existing base spectra — nothing appended.'
                    )

        else:
            logger.info(
                f'get_af_spectra refine: only {problem_n} problem cells found — '
                f'skipping modulation (need > 10).'
            )

    logger.info(f'get_af_spectra: returning {af_spectra.shape[0]} AF spectra total')
    return af_spectra

