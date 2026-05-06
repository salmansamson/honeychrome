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
@dataclass
class CleanResult:
    positive:                 np.ndarray
    negative:                 np.ndarray
    scatter_pos:              np.ndarray        # empty until Stage 3
    scatter_neg:              np.ndarray        # empty until Stage 3
    hull_vertices:            np.ndarray | None # convex hull of smooth contour used for matching; None if fallback taken
    n_removed_saturation:     int
    n_removed_af:             int               # always 0 until Stage 4
    n_scatter_matched:        int               # always len(negative) until Stage 3
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
    positivity_quantile: float = 0.995,
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
# scatter_match_negative  (Stage 3)
# ---------------------------------------------------------------------------

def scatter_match_negative(
    scatter_pos: np.ndarray,
    scatter_neg: np.ndarray,
    min_neg_n: int = 50,
    density_percentile: float = 0.30,
    max_expand_steps: int = 5,
    grid_n: int = 50,
    bw_factor: float = 2.0,
) -> tuple[np.ndarray, int, np.ndarray | None]:
    """
    Restrict negative events to those whose FSC/SSC lies inside a smooth
    boundary derived from the dense core of the positive scatter cloud.

    Matches the R gate.scatter.match() approach:
      1. Estimate a 2D KDE on a regular grid (scipy.stats.gaussian_kde).
      2. Find the cumulative-density threshold at density_percentile.
      3. Extract the iso-density contour at that threshold (matplotlib contour).
      4. Take the convex hull of those smooth contour coordinates.
      5. Test which negative events fall inside that hull.

    Parameters
    ----------
    scatter_pos        : (n_pos, 2) FSC, SSC of the selected positive events
    scatter_neg        : (n_neg, 2) FSC, SSC of all negative events
    min_neg_n          : minimum acceptable matched count before expanding
    density_percentile : cumulative density fraction defining the contour (default 0.50)
    max_expand_steps   : how many times to relax density_percentile by 0.1
    grid_n             : resolution of the KDE grid (default 50)
    bw_factor          : bandwidth multiplier for the KDE (default 5.0, matches R)

    Returns
    -------
    mask          : boolean array over scatter_neg rows (True = inside hull)
    n_matched     : number of True entries
    hull_vertices : (k, 2) convex hull vertices of the smooth contour actually used,
                   or None if the fallback (all events) was used.
    """
    from scipy.stats import gaussian_kde
    from scipy.spatial import ConvexHull
    from matplotlib.path import Path
    import matplotlib
    import matplotlib.figure
    import matplotlib.contour  # noqa — ensure ContourSet is available

    if len(scatter_pos) < 4:
        return np.ones(len(scatter_neg), dtype=bool), len(scatter_neg), None

    # Estimate per-axis Scott bandwidth, scaled by bw_factor
    std_x = np.std(scatter_pos[:, 0])
    std_y = np.std(scatter_pos[:, 1])
    n = len(scatter_pos)
    bw_x = 1.06 * std_x * n ** (-1 / 5) * bw_factor
    bw_y = 1.06 * std_y * n ** (-1 / 5) * bw_factor

    x_min, x_max = scatter_pos[:, 0].min(), scatter_pos[:, 0].max()
    y_min, y_max = scatter_pos[:, 1].min(), scatter_pos[:, 1].max()
    xi = np.linspace(x_min, x_max, grid_n)
    yi = np.linspace(y_min, y_max, grid_n)
    xx, yy = np.meshgrid(xi, yi)
    grid_pts = np.vstack([xx.ravel(), yy.ravel()])

    # Pre-whiten: scale each axis by its bandwidth so that scipy's scalar
    # bandwidth of 1.0 is equivalent to the desired per-axis bandwidths.
    scale = np.array([bw_x, bw_y])
    pos_whitened = scatter_pos / scale
    kde = gaussian_kde(pos_whitened.T, bw_method=1.0)

    # Build the grid in whitened space, evaluate, then the contour coordinates
    # will be un-whitened back to original scatter space below.
    xi_w = np.linspace(pos_whitened[:, 0].min(), pos_whitened[:, 0].max(), grid_n)
    yi_w = np.linspace(pos_whitened[:, 1].min(), pos_whitened[:, 1].max(), grid_n)
    xx_w, yy_w = np.meshgrid(xi_w, yi_w)
    grid_pts_w = np.vstack([xx_w.ravel(), yy_w.ravel()])
    zz = kde(grid_pts_w).reshape(grid_n, grid_n)

    percentile = density_percentile
    for _ in range(max_expand_steps + 1):
        try:
            # Cumulative density threshold matching R's which.min(abs(cumsum - percentile))
            z_sorted = np.sort(zz.ravel())[::-1]
            cum_dens = np.cumsum(z_sorted) / z_sorted.sum()
            threshold = z_sorted[np.argmin(np.abs(cum_dens - percentile))]

            # Extract contour at that level using matplotlib
            fig = matplotlib.figure.Figure()
            ax = fig.add_subplot(111)
            cs = ax.contour(xi_w, yi_w, zz, levels=[threshold])

            all_paths = [path.vertices for path in cs.get_paths()]
            if not all_paths:
                percentile = max(0.0, percentile - 0.1)
                continue
            # Un-whiten contour coordinates back to original scatter space
            contour_pts = max(all_paths, key=len) * scale

            if len(contour_pts) < 4:
                percentile = max(0.0, percentile - 0.1)
                continue

            hull = ConvexHull(contour_pts)
            hull_verts = contour_pts[hull.vertices]
            hull_path = Path(hull_verts)
            mask = hull_path.contains_points(scatter_neg)
            n_matched = int(mask.sum())

            if n_matched >= min_neg_n:
                return mask, n_matched, hull_verts

            percentile = max(0.0, percentile - 0.1)

        except Exception:
            break

    return np.ones(len(scatter_neg), dtype=bool), len(scatter_neg), None


# ---------------------------------------------------------------------------
# clean_control  (Stage 3: saturation exclusion + scatter matching)
# ---------------------------------------------------------------------------

def clean_control(
    positive_events: np.ndarray,
    negative_events: np.ndarray,
    peak_ch_idx: int,
    ceiling: float,
    positivity_quantile: float = 0.995,
    scatter_pos: np.ndarray | None = None,
    scatter_neg: np.ndarray | None = None,
    opts: dict | None = None,
) -> CleanResult:
    """
    Run the full cleaning pipeline for one control.
    Stage 3: saturation exclusion + scatter matching.

    Parameters
    ----------
    positive_events : (n_pos, n_fluor_ch)  fluorescence only
    negative_events : (n_neg, n_fluor_ch)  fluorescence only
    peak_ch_idx     : peak channel index (into axis-1)
    ceiling         : raw_settings["magnitude_ceiling"]
    positivity_quantile : passed through to select_positive_events
    scatter_pos     : (n_pos, 2) FSC/SSC for positive events, aligned with positive_events
    scatter_neg     : (n_neg, 2) FSC/SSC for negative events, aligned with negative_events
    opts            : future options dict (e.g. {"af_remove": True})
    """
    opts = opts or {}
    result_warnings: list[str] = []

    # --- Stage 2a: saturation exclusion ---
    pos_clean, n_sat_pos = exclude_saturated(positive_events, ceiling)
    neg_clean, n_sat_neg = exclude_saturated(negative_events, ceiling)
    n_removed_saturation = n_sat_pos + n_sat_neg

    # Keep scatter arrays aligned with their fluorescence counterparts after
    # saturation exclusion.  We track which rows survive using boolean masks.
    if scatter_pos is not None and len(scatter_pos) == len(positive_events):
        sat_threshold = ceiling * 0.9995
        pos_sat_mask = ~np.any(positive_events >= sat_threshold, axis=1)
        scatter_pos_clean = scatter_pos[pos_sat_mask]
    else:
        scatter_pos_clean = np.empty((0, 2))

    if scatter_neg is not None and len(scatter_neg) == len(negative_events):
        sat_threshold = ceiling * 0.9995
        neg_sat_mask = ~np.any(negative_events >= sat_threshold, axis=1)
        scatter_neg_clean = scatter_neg[neg_sat_mask]
    else:
        scatter_neg_clean = np.empty((0, 2))

    # --- TODO Stage 4: AF removal ---
    # if opts.get("af_remove", False):
    #     pos_clean, n_removed_af = remove_af_contamination(pos_clean, neg_clean, peak_ch_idx)
    n_removed_af = 0

    # --- Stage 3: scatter matching ---
    # --- Stage 3: scatter matching ---
    hull_vertices: np.ndarray | None = None
    if (scatter_pos_clean.shape[0] >= 4 and scatter_neg_clean.shape[0] > 0):
        scatter_mask, n_scatter_matched, hull_vertices = scatter_match_negative(
            scatter_pos_clean, scatter_neg_clean
        )
        neg_clean = neg_clean[scatter_mask]
        scatter_neg_clean = scatter_neg_clean[scatter_mask]
    else:
        n_scatter_matched = len(neg_clean)

    return CleanResult(
        positive=pos_clean,
        negative=neg_clean,
        scatter_pos=scatter_pos_clean,
        scatter_neg=scatter_neg_clean,
        hull_vertices=hull_vertices,
        n_removed_saturation=n_removed_saturation,
        n_removed_af=n_removed_af,
        n_scatter_matched=n_scatter_matched,
        n_surviving_positive=len(pos_clean),
        positivity_quantile_used=positivity_quantile,
        warnings=result_warnings,
    )