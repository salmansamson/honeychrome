"""
spectral_cleaning.py

Public API:
    exclude_saturated(events, ceiling, threshold_frac=0.99)
    find_empirical_peak(spec_events, af_mean)
    cosine_filter(spec_events, af_median, peak_ch_idx, ...)
    knn_scatter_match(spec_pos, scatter_pos, spec_neg, scatter_neg, k=3)
    CleanResult
"""

from __future__ import annotations
from dataclasses import dataclass, field

import numpy as np


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class CleanResult:
    spectral_sub:             np.ndarray        # kNN-subtracted spectral events
    scatter_pos:              np.ndarray        # scatter of selected positives
    scatter_neg_matched:      np.ndarray        # mean kNN-matched neg scatter
    n_removed_saturation:     int
    n_surviving_positive:     int
    empirical_peak_ch_idx:    int
    expected_peak_ch_idx:     int
    cs_vals:                  np.ndarray | None = None
    cosine_selected_idx:      np.ndarray | None = None
    warnings:                 list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# exclude_saturated
# ---------------------------------------------------------------------------

def exclude_saturated(
    events: np.ndarray,
    ceiling: float,
    threshold_frac: float = 0.999,
) -> tuple[np.ndarray, int, np.ndarray]:
    """
    ...
    Returns
    -------
    filtered_events : rows surviving the filter
    n_removed : number of rows removed
    saturated_mask : boolean mask (True = saturated, length = input row count)
    """
    sat_threshold = ceiling * threshold_frac
    saturated_mask = np.any(events >= sat_threshold, axis=1)
    n_removed = int(saturated_mask.sum())
    return events[~saturated_mask], n_removed, saturated_mask


# ---------------------------------------------------------------------------
# select_positive_events
# ---------------------------------------------------------------------------
def find_empirical_peak(
    spec_events: np.ndarray,
    af_mean: np.ndarray,
) -> int:
    """
    AF orthogonalisation -> empirical peak column index.

    Projects events onto the unit AF vector, subtracts the projection,
    returns the column with the highest mean in the orthogonalised space.
    """
    norm = np.sqrt(np.dot(af_mean, af_mean)) + 1e-9
    v_unit = af_mean / norm
    proj = spec_events @ v_unit
    mat_orth = spec_events - np.outer(proj, v_unit)
    return int(np.argmax(mat_orth.mean(axis=0)))

def knn_scatter_match(
    spec_pos: np.ndarray,      # (n_pos, n_ch)
    scatter_pos: np.ndarray,   # (n_pos, 2) FSC/SSC selected positives
    spec_neg: np.ndarray,      # (n_neg, n_ch)
    scatter_neg: np.ndarray,   # (n_neg, 2) FSC/SSC negative events
    k: int = 3,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Per-event AF subtraction via kNN scatter matching.

    Returns
    -------
    spectral_sub        : (n_pos, n_ch) AF-subtracted spectral events
    matched_neg_scatter : (n_pos, 2) mean scatter of matched negatives
                         (for display in ScatterCleaningViewer)
    """
    from sklearn.neighbors import NearestNeighbors

    if len(scatter_neg) == 0 or len(scatter_pos) == 0:
        return spec_pos.copy(), np.empty((0, 2))

    k_actual = min(k, len(scatter_neg))
    nn = NearestNeighbors(n_neighbors=k_actual, algorithm='ball_tree')
    nn.fit(scatter_neg)
    _, indices = nn.kneighbors(scatter_pos)         # (n_pos, k)

    af_matched = spec_neg[indices].mean(axis=1)     # (n_pos, n_ch)
    spectral_sub = spec_pos - af_matched
    matched_neg_scatter = scatter_neg[indices].mean(axis=1)  # (n_pos, 2)

    return spectral_sub, matched_neg_scatter

def cosine_filter(
    spec_events: np.ndarray,
    af_median: np.ndarray,
    peak_ch_idx: int,
    n_candidates: int = 1000,
    n_spectral: int = 200,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Select events least similar to AF by cosine similarity.

    1. Top n_candidates events by peak channel value.
    2. Cosine similarity of each to af_median.
    3. Keep n_spectral with the lowest cosine similarity.

    Returns
    -------
    selected_idx : (n_spectral,) indices into spec_events
    cs_vals      : (n_candidates,) cosine similarity values (for QC plot)
    """
    n_cand = min(n_candidates, len(spec_events))
    peak_vals = spec_events[:, peak_ch_idx]
    top_idx = np.argpartition(peak_vals, -n_cand)[-n_cand:]

    top_mat  = spec_events[top_idx]
    norm_af   = np.sqrt(np.dot(af_median, af_median)) + 1e-9
    norm_rows = np.linalg.norm(top_mat, axis=1) + 1e-9
    cs_vals   = (top_mat @ af_median) / (norm_rows * norm_af)

    n_spec       = min(n_spectral, n_cand)
    keep_order   = np.argsort(cs_vals)[:n_spec]
    selected_idx = top_idx[keep_order]

    return selected_idx, cs_vals