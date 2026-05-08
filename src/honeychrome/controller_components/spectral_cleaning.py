"""
spectral_cleaning.py

Public API:
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
    scatter_pos:              np.ndarray
    scatter_neg:              np.ndarray
    hull_vertices:            np.ndarray | None # convex hull of smooth contour used for matching; None if fallback taken
    n_removed_saturation:     int
    n_removed_af:             int               # 0 when af_remove=False
    n_scatter_matched:        int
    n_surviving_positive:     int
    positivity_quantile_used: float
    # AF removal diagnostics for the viewer.
    # af_boundary_neg: (k, 2) polygon vertices in (af_ch, peak_ch) space
    #   defining the exclusion zone on the unstained (where the boundary was fitted).
    # af_boundary_pos: same polygon transformed into the positive sample's coordinates
    #   (identical polygon — the gate applies in the same channel space).
    # af_ch_idx / peak_ch_idx: channel indices for the two axes of the AF biplot.
    af_boundary_neg:          np.ndarray | None = None
    af_boundary_pos:          np.ndarray | None = None
    af_ch_idx:                int | None = None
    af_peak_ch_idx:           int | None = None
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
# scatter_match_negative
# ---------------------------------------------------------------------------

def scatter_match_negative(
    scatter_pos: np.ndarray,
    scatter_neg: np.ndarray,
    min_neg_n: int = 50,
    density_percentile: float = 0.20,
    max_expand_steps: int = 5,
    grid_n: int = 50,
    bw_factor: float = 1.0,
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
# remove_af_contamination
# ---------------------------------------------------------------------------

def remove_af_contamination(
    positive_events: np.ndarray,   # (n_pos, n_fluor_ch) — sat-excluded positives
    negative_events: np.ndarray,   # (n_neg, n_fluor_ch) — sat-excluded negatives
    peak_ch_idx: int,
    af_percentile_cutoff: float = 0.99,
    af_spline_sd_n: float = 2.5,
    af_spline_expand: float = 1.05,
    downsample_neg_n: int = 2000,
) -> tuple[np.ndarray, int, np.ndarray | None, int | None]:
    """
    Remove events from positive_events that are contaminated by intrusive
    autofluorescence, using a boundary fitted on the matched negative (unstained).

    Algorithm (mirrors AutoSpectral's remove.af() / fit.af.spline()):
      1. Downsample negative to downsample_neg_n for speed.
      2. Median/MAD-scale spectral channels. Run PCA (n_components=2).
      3. Identify AF-bright events: those above af_percentile_cutoff of PC1 scores.
      4. Derive AF spectrum: median(AF-bright) − median(AF-dim), normalised.
      5. Find AF peak channel (argmax). If it equals peak_ch_idx, find best
         alternative using MAD-normalised separation index.
      6. Fit a boundary polygon in (af_ch, peak_ch) 2D space using an RLM
         spline on AF-bright + AF-dim events, then expand with a convex hull.
      7. Exclude positive events whose (af_ch, peak_ch) coordinates fall
         inside the boundary polygon.

    Returns
    -------
    cleaned_positive  : positive events with AF-contaminated rows removed
    n_removed_af      : number of rows removed
    boundary_polygon  : (k, 2) polygon vertices in (af_ch, peak_ch) space,
                        or None if fallback taken (no removal)
    af_ch_idx         : index of the AF channel used (for biplot axis labelling)
    """
    from sklearn.decomposition import PCA
    from sklearn.linear_model import HuberRegressor
    from scipy.spatial import ConvexHull
    from matplotlib.path import Path

    n_ch = negative_events.shape[1]

    # --- 1. Downsample negative ---
    neg = negative_events
    if len(neg) > downsample_neg_n:
        rng = np.random.default_rng(42)
        idx = rng.choice(len(neg), downsample_neg_n, replace=False)
        neg = neg[idx]

    # --- 2. Median/MAD scale + PCA ---
    center = np.median(neg, axis=0)
    scale  = np.median(np.abs(neg - center), axis=0)
    scale[scale < 1e-9] = 1.0        # protect against zero-MAD channels
    scaled = (neg - center) / scale

    if np.any(~np.isfinite(scaled)):
        # NaN/Inf in scaled data — skip AF removal
        return positive_events, 0, None, None

    try:
        pca = PCA(random_state=42)
        pca.fit(scaled)
        pc_scores = pca.transform(scaled)[:, :2]
    except Exception:
        return positive_events, 0, None, None

    # --- 3. AF-bright / AF-dim split on PC1 ---
    pc1 = pc_scores[:, 0]
    cutoff = np.quantile(pc1, af_percentile_cutoff)
    af_bright_mask = pc1 > cutoff
    af_dim_mask    = ~af_bright_mask

    if af_bright_mask.sum() < 5 or af_dim_mask.sum() < 5:
        return positive_events, 0, None, None

    # --- 4. AF spectrum ---
    af_median     = np.median(neg[af_bright_mask], axis=0)
    non_af_median = np.median(neg[af_dim_mask],    axis=0)
    af_spectrum   = af_median - non_af_median
    abs_max = np.abs(af_spectrum).max()
    if abs_max < 1e-9:
        return positive_events, 0, None, None
    af_spectrum /= abs_max
    if af_spectrum.max() < -af_spectrum.min():  # flip if inverted
        af_spectrum = -af_spectrum

    # --- 5. Find AF peak channel (not equal to fluorophore peak) ---
    af_ch_idx = int(np.argmax(af_spectrum))
    if af_ch_idx == peak_ch_idx:
        # Use MAD-normalised separation index on non-peak channels
        neg_mad = np.median(np.abs(neg[af_dim_mask] - non_af_median), axis=0)
        neg_mad[neg_mad < 1e-9] = 1e-9
        sep_index = (af_median - non_af_median) / neg_mad
        candidates = [i for i in range(n_ch) if i != peak_ch_idx]
        af_ch_idx = candidates[int(np.argmax(sep_index[candidates]))]

    # --- 6. Fit boundary polygon in (af_ch, peak_ch) space ---
    af_data  = neg[af_bright_mask][:, [af_ch_idx, peak_ch_idx]]    # (n_bright, 2)
    dim_data = neg[af_dim_mask][:,    [af_ch_idx, peak_ch_idx]]    # (n_dim,    2)
    # Downsample dim data to ≤500 points
    if len(dim_data) > 500:
        rng2 = np.random.default_rng(43)
        dim_data = dim_data[rng2.choice(len(dim_data), 500, replace=False)]

    boundary = _fit_af_boundary(af_data, dim_data,
                                af_spline_sd_n=af_spline_sd_n,
                                af_spline_expand=af_spline_expand)

    if boundary is None:
        return positive_events, 0, None, af_ch_idx

    # --- 7. Exclude positive events inside the boundary ---
    pos_2d = positive_events[:, [af_ch_idx, peak_ch_idx]]
    hull_path = Path(boundary)
    inside_mask = hull_path.contains_points(pos_2d)
    n_removed = int(inside_mask.sum())
    cleaned = positive_events[~inside_mask]

    return cleaned, n_removed, boundary, af_ch_idx


def _fit_af_boundary(
    af_cells: np.ndarray,     # (n_af, 2) — x=af_ch, y=peak_ch
    non_af_cells: np.ndarray, # (n_dim, 2)
    af_spline_sd_n: float = 2.5,
    af_spline_expand: float = 1.05,
) -> np.ndarray | None:
    """
    Fit a convex-hull boundary around the AF-bright events in 2D channel space,
    mirroring AutoSpectral's fit.af.spline().

    Returns (k, 2) polygon vertices or None on failure.
    """
    from sklearn.linear_model import HuberRegressor
    from scipy.spatial import ConvexHull

    if len(af_cells) < 10 or len(non_af_cells) < 10:
        return None

    all_data = np.vstack([af_cells, non_af_cells])  # (n, 2)
    x = all_data[:, 0].reshape(-1, 1)
    y = all_data[:, 1]

    try:
        rlm = HuberRegressor(epsilon=1.35, max_iter=300, fit_intercept=True)
        rlm.fit(x, y)
    except Exception:
        return None

    predicted = rlm.predict(x)
    residuals = y - predicted
    sd_res = np.std(residuals)
    if sd_res < 1e-9:
        sd_res = 1e-9

    within_mask = np.abs(residuals) <= af_spline_sd_n * sd_res
    model_fit = all_data[within_mask]

    # Use AF cells above the 99th percentile of x (AF channel) to define boundary
    x_bound_low = np.quantile(non_af_cells[:, 0], 0.9)
    model_fit_data = model_fit[model_fit[:, 0] > x_bound_low]

    # Expand iteratively if not enough points
    for _ in range(10):
        if len(model_fit_data) >= 10:
            break
        x_bound_low *= 0.9
        model_fit_data = model_fit[model_fit[:, 0] > x_bound_low]

    if len(model_fit_data) < 5:
        return None

    # Expand upper-quartile points to catch extreme AF events
    q_vals = np.quantile(model_fit_data, 0.75, axis=0)
    upper_mask = (model_fit_data[:, 0] >= q_vals[0]) | (model_fit_data[:, 1] >= q_vals[1])
    upper_pts = model_fit_data[upper_mask] * af_spline_expand
    expanded = np.unique(np.vstack([model_fit_data, upper_pts]), axis=0)

    if len(expanded) < 4:
        return None

    try:
        hull = ConvexHull(expanded)
        return expanded[hull.vertices]
    except Exception:
        return None
    

# ---------------------------------------------------------------------------
# clean_control  (saturation exclusion + scatter matching)
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
    saturation exclusion + scatter matching.

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

    # --- saturation exclusion ---
    sat_threshold = ceiling * 0.9995
    pos_sat_mask = ~np.any(positive_events >= sat_threshold, axis=1)
    neg_sat_mask = ~np.any(negative_events >= sat_threshold, axis=1)

    pos_clean = positive_events[pos_sat_mask]
    neg_clean = negative_events[neg_sat_mask]
    n_sat_pos = int(np.sum(~pos_sat_mask))
    n_sat_neg = int(np.sum(~neg_sat_mask))
    n_removed_saturation = n_sat_pos + n_sat_neg

    # Keep scatter arrays aligned using the same masks.
    scatter_pos_clean = scatter_pos[pos_sat_mask] if (scatter_pos is not None and len(scatter_pos) == len(positive_events)) else np.empty((0, 2))
    scatter_neg_clean = scatter_neg[neg_sat_mask] if (scatter_neg is not None and len(scatter_neg) == len(negative_events)) else np.empty((0, 2))

    # --- AF removal (optional, off by default) ---
    n_removed_af = 0
    af_boundary_neg: np.ndarray | None = None
    af_boundary_pos: np.ndarray | None = None
    af_ch_idx_result: int | None = None
    if opts.get("af_remove", False):
        cleaned_pos, n_removed_af, af_boundary_neg, af_ch_idx_result = remove_af_contamination(
            pos_clean, neg_clean, peak_ch_idx
        )
        af_boundary_pos = af_boundary_neg
        if n_removed_af > 0:
            # Derive the keep mask from pos_clean before reassigning it,
            # so scatter_pos_clean stays aligned with cleaned_pos.
            if scatter_pos_clean.shape[0] == len(pos_clean) and af_boundary_neg is not None:
                from matplotlib.path import Path as _Path
                pos_2d = pos_clean[:, [af_ch_idx_result, peak_ch_idx]]
                inside = _Path(af_boundary_neg).contains_points(pos_2d)
                scatter_pos_clean = scatter_pos_clean[~inside]
            pos_clean = cleaned_pos

    # --- scatter matching ---
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
        af_boundary_neg=af_boundary_neg,
        af_boundary_pos=af_boundary_pos,
        af_ch_idx=af_ch_idx_result,
        af_peak_ch_idx=peak_ch_idx if opts.get("af_remove", False) else None,
        warnings=result_warnings,
    )