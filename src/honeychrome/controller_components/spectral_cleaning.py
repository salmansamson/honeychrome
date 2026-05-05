"""
spectral_cleaning.py
Stages 2–4 of the AutoSpectral integration.

Public API after Stage 2:
    exclude_saturated(events, ceiling, threshold_frac=0.99)
    select_positive_events(positive_events, negative_events, peak_ch_idx, ...)
    CleanResult
    clean_control(positive_events, negative_events, peak_ch_idx, ceiling, opts=None)
"""

from __future__ import annotations
from dataclasses import dataclass, field

import numpy as np


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class CleanResult:
    positive:                 np.ndarray
    negative:                 np.ndarray
    scatter_pos:              np.ndarray   # empty until Stage 3
    scatter_neg:              np.ndarray   # empty until Stage 3
    n_removed_saturation:     int
    n_removed_af:             int          # always 0 until Stage 4
    n_scatter_matched:        int          # always len(negative) until Stage 3
    n_surviving_positive:     int
    positivity_quantile_used: float
    warnings:                 list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# exclude_saturated
# ---------------------------------------------------------------------------

def exclude_saturated(
    events: np.ndarray,
    ceiling: float,
    threshold_frac: float = 0.999,
) -> tuple[np.ndarray, int]:
    """
    Remove rows where any fluorescence channel >= ceiling * threshold_frac.

    Parameters
    ----------
    events : (n, n_fluor_ch) — may also have scatter columns appended; only
             the first n_fluor_ch columns are checked against the ceiling.
             Pass n_fluor_ch via the caller if the array is a combined
             [fluor | scatter] matrix, or pass the fluorescence-only slice here.
    ceiling : raw_settings["magnitude_ceiling"]
    threshold_frac : fraction of ceiling above which an event is considered
                     saturated (default 0.999)

    Returns
    -------
    filtered_events : rows surviving the filter
    n_removed : number of rows removed
    """
    sat_threshold = ceiling * threshold_frac
    saturated_mask = np.any(events >= sat_threshold, axis=1)
    n_removed = int(saturated_mask.sum())
    return events[~saturated_mask], n_removed


# ---------------------------------------------------------------------------
# select_positive_events
# ---------------------------------------------------------------------------

def select_positive_events(
    positive_events: np.ndarray,
    negative_events: np.ndarray,
    peak_ch_idx: int,
    initial_n: int = 250,
    positivity_quantile: float = 0.9995,
    min_positivity_quantile: float = 0.95,   # kept for caller reference; not used internally
    quantile_step: float = 0.01,             # kept for caller reference; not used internally
) -> tuple[np.ndarray, np.ndarray, float]:
    """
    Select the top-N brightest positive events above a threshold derived from
    the negative's peak-channel distribution.

    Parameters
    ----------
    positive_events : (n_pos, n_fluor_ch)
    negative_events : (n_neg, n_fluor_ch)
    peak_ch_idx     : index into axis-1 for the fluorophore's peak channel
    initial_n       : maximum number of events to return
    positivity_quantile : quantile of the negative peak-channel used as threshold

    Returns
    -------
    selected_events  : (k, n_fluor_ch), k <= initial_n
    selected_indices : integer indices into positive_events
    threshold_used   : the positivity threshold value
    """
    if len(negative_events) == 0:
        # No negative available — return top-N without thresholding
        peak_values = positive_events[:, peak_ch_idx]
        n = min(initial_n, len(positive_events))
        top_idx = np.argpartition(peak_values, -n)[-n:] if n < len(positive_events) else np.arange(len(positive_events))
        top_idx = top_idx[np.argsort(peak_values[top_idx])[::-1]]
        return positive_events[top_idx], top_idx, 0.0

    threshold = float(np.quantile(negative_events[:, peak_ch_idx], positivity_quantile))

    pos_peak = positive_events[:, peak_ch_idx]
    above_mask = pos_peak > threshold
    above_idx = np.where(above_mask)[0]

    if len(above_idx) == 0:
        # Nothing above threshold; return empty but preserve dtype
        empty = positive_events[:0]
        return empty, np.array([], dtype=int), threshold

    # Sort descending by peak channel value, take top initial_n
    sorted_order = above_idx[np.argsort(pos_peak[above_idx])[::-1]]
    selected_idx = sorted_order[: initial_n]
    return positive_events[selected_idx], selected_idx, threshold


# ---------------------------------------------------------------------------
# clean_control  (Stage 2: saturation exclusion only)
# ---------------------------------------------------------------------------

def clean_control(
    positive_events: np.ndarray,
    negative_events: np.ndarray,
    peak_ch_idx: int,
    ceiling: float,
    positivity_quantile: float = 0.995,
    opts: dict | None = None,
) -> CleanResult:
    """
    Run the full cleaning pipeline for one control.
    After Stage 2 this comprises saturation exclusion only.
    Scatter matching (Stage 3) and AF removal (Stage 4) are placeholders.

    Parameters
    ----------
    positive_events : (n_pos, n_fluor_ch)
    negative_events : (n_neg, n_fluor_ch)
    peak_ch_idx     : peak channel index (into axis-1)
    ceiling         : raw_settings["magnitude_ceiling"]
    positivity_quantile : passed through to select_positive_events
    opts            : future options dict (e.g. {"af_remove": True})
    """
    opts = opts or {}
    result_warnings: list[str] = []

    # --- Stage 2a: saturation exclusion ---
    pos_clean, n_sat_pos = exclude_saturated(positive_events, ceiling)
    neg_clean, n_sat_neg = exclude_saturated(negative_events, ceiling)
    n_removed_saturation = n_sat_pos + n_sat_neg

    # --- TODO Stage 4: AF removal ---
    # if opts.get("af_remove", False):
    #     pos_clean, n_removed_af = remove_af_contamination(pos_clean, neg_clean, peak_ch_idx)
    # else:
    n_removed_af = 0

    # --- TODO Stage 3: scatter matching ---
    # scatter_mask, n_matched = scatter_match_negative(scatter_pos, scatter_neg)
    # neg_clean = neg_clean[scatter_mask]
    n_scatter_matched = len(neg_clean)

    return CleanResult(
        positive=pos_clean,
        negative=neg_clean,
        scatter_pos=np.empty((0, 0)),
        scatter_neg=np.empty((0, 0)),
        n_removed_saturation=n_removed_saturation,
        n_removed_af=n_removed_af,
        n_scatter_matched=n_scatter_matched,
        n_surviving_positive=len(pos_clean),
        positivity_quantile_used=positivity_quantile,
        warnings=result_warnings,
    )