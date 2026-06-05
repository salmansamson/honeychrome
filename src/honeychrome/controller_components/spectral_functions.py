import warnings
import logging

import numpy as np
from flowkit import GatingStrategy


import honeychrome.settings as settings

logger = logging.getLogger(__name__)

def get_best_channel(sample, gating_strategy, base_gate_label, fluorescence_channel_ids):
    from sklearn.decomposition import PCA

    # gate first by cells
    if base_gate_label != 'root':
        base_event_mask = gating_strategy.gate_sample(sample).get_gate_membership(base_gate_label) # Note this is slow
    else:
        base_event_mask = np.ones(sample.event_count, dtype=bool)
    # base_event_mask_indices = np.where(base_event_mask)[0]

    if np.sum(base_event_mask) < 2:
        return None
    else:
        pca = PCA(n_components=1)
        event_data_base_gate = sample.get_events('raw')[base_event_mask]
        event_data_fluorescence = event_data_base_gate[:, fluorescence_channel_ids]
        pca.fit(event_data_fluorescence)
        explained_variance = pca.explained_variance_ratio_[0]

        # # get top n events in principle axis
        # events_transformed_to_pca = pca.transform(event_data_fluorescence).flatten()
        # n_to_gate = 100
        # # More efficient for large arrays - doesn't fully sort array
        # indices_top_n_events = np.argpartition(events_transformed_to_pca, -n_to_gate)[-n_to_gate:]
        # # Sort the top 100 indices by value (descending)
        # indices_top_n_events = base_event_mask_indices[indices_top_n_events[np.argsort(events_transformed_to_pca[indices_top_n_events])][::-1]]

        # define gates
        # n_matches_per_fluorescence_channel = {}
        # matches_per_fluorescence_channel = {}
        # fl_raw = sample.get_events('raw')
        # for channel_id in fluorescence_channel_ids:
        #     fl = fl_raw[base_event_mask, channel_id]
        #     indices_top_n_events_fluorescence_channels = base_event_mask_indices[np.argpartition(fl, -n_to_gate)[-n_to_gate:]]
        #     matches_per_fluorescence_channel[channel_id] = list(set(indices_top_n_events) & set(indices_top_n_events_fluorescence_channels))
        #     n_matches_per_fluorescence_channel[channel_id] = len(matches_per_fluorescence_channel[channel_id])
        # # in which single channel are most of those top n events at the top?
        # channel_id_best_match = np.argmax(n_matches_per_fluorescence_channel)
        # or just peak of spectral profile (PCA component)
        channel_id_best_match = fluorescence_channel_ids[np.argmax(pca.components_[0])]
        # best_match = n_matches_per_fluorescence_channel[channel_id_best_match]
        # fl_top = fl_raw[matches_per_fluorescence_channel[channel_id_best_match], channel_id_best_match]

        fluorescence_on_best_channel = event_data_base_gate[:, channel_id_best_match]
        if len(fluorescence_on_best_channel) > 100:
            pos_percentile = settings.spectral_positive_gate_percent_retrieved
            neg_percentile = settings.spectral_negative_gate_percent_retrieved
        else:
            pos_percentile = 50
            neg_percentile = 50

        # define top gate
        fl_top = np.percentile(fluorescence_on_best_channel, [100 - pos_percentile, 100])

        # define bottom gate
        fl_bottom = np.percentile(fluorescence_on_best_channel, [0, neg_percentile])

        # print([len(fluorescence_on_best_channel), pos_percentile, neg_percentile, fl_top, fl_bottom])
        return channel_id_best_match, fl_top, fl_bottom, explained_variance

def get_profile(sample, gate_label, raw_gating, fluorescence_channel_ids):
    gate_ids = list(raw_gating.find_matching_gate_paths(gate_label)[0]) + [gate_label]
    temp_gating_strategy = GatingStrategy()
    for n, gate_id in enumerate(gate_ids):
        if gate_id != 'root':
            gate = raw_gating.get_gate(gate_id)
            temp_gating_strategy.add_gate(gate, gate_path=tuple(gate_ids[:n]))
            for channel in gate.dimensions:
                temp_gating_strategy.transformations[channel.id] = raw_gating.transformations[channel.id]

    if gate_label != 'root':
        event_mask = temp_gating_strategy.gate_sample(sample).get_gate_membership(gate_label)
    else:
        event_mask = np.ones(sample.event_count, dtype=bool)

    if event_mask.sum() > 0:
        profile = sample.get_events('raw')[event_mask].mean(axis=0)
        profile = profile[fluorescence_channel_ids]
    else:
        profile = np.zeros(len(fluorescence_channel_ids))
        warnings.warn('No events in gate')

    return profile

def get_profile_from_events(
    positive_events: np.ndarray,   # (n, n_fluor_ch) — cleaned, scatter-matched
    negative_events: np.ndarray,   # (n, n_fluor_ch) — scatter-matched negative
    peak_ch_idx: int,
    label: str = '',
) -> np.ndarray:
    """
    Fit a robust linear model (RLM) for each channel regressed on the peak
    channel, using the combined positive+negative event pool.

    Each off-peak channel is modelled as:
        other_ch ~ peak_ch
    using sklearn's HuberRegressor (IRLS with Huber loss — equivalent to
    MASS::rlm in R).  The slope is the spectral coefficient for that channel.
    IRLS down-weighting means saturated outliers or residual AF events
    have minimal influence even if they survive cleaning.

    Returns an L-infinity normalised profile vector.
    """
    from sklearn.linear_model import HuberRegressor

    combined = np.vstack([positive_events, negative_events])
    n_pos = len(positive_events)
    n_neg = len(negative_events)
    if n_neg > n_pos:
        rng = np.random.default_rng(42)
        neg_idx = rng.choice(n_neg, n_pos, replace=False)
        combined = np.vstack([positive_events, negative_events[neg_idx]])
    x = combined[:, peak_ch_idx]
    n_ch = positive_events.shape[1]
    profile = np.zeros(n_ch)
    profile[peak_ch_idx] = 1.0

    # Vectorised IRLS: fit all channels simultaneously using a single shared
    # weight vector derived from the peak-channel residuals.
    x_c = x - x.mean()
    # Exclude peak channel from regression — hardcoded to 1.0 as in R
    off_peak = [ch for ch in range(n_ch) if ch != peak_ch_idx]
    Y = combined[:, off_peak] - combined[:, off_peak].mean(axis=0)

    # Per-channel OLS initialisation for delta (one value per channel)
    slopes_ols = (x_c @ Y) / (x_c @ x_c + 1e-9)
    residuals_ols = Y - x_c[:, None] * slopes_ols
    mad_per_ch = np.median(np.abs(residuals_ols - np.median(residuals_ols, axis=0)), axis=0)
    delta = 1.345 * np.where(mad_per_ch > 1e-9, mad_per_ch, residuals_ols.std(axis=0))

    # Per-channel weight matrix: W is (n_events, n_ch)
    n_off = len(off_peak)
    W = np.ones((len(x_c), n_off))
    prev_slopes = np.zeros(n_off)
    for i in range(50):
        # Weighted regression per channel: slope_ch = sum(w_ch * x * y_ch) / sum(w_ch * x^2)
        wx = W * x_c[:, None]
        slopes = (wx * Y).sum(axis=0) / ((wx * x_c[:, None]).sum(axis=0) + 1e-9)
        residuals = Y - x_c[:, None] * slopes
        # Huber weights independently per channel
        W = np.where(np.abs(residuals) <= delta, 1.0, delta / (np.abs(residuals) + 1e-9))
        slope_change = np.max(np.abs(slopes - prev_slopes))
        prev_slopes[:] = slopes
        if slope_change < 1e-6:
            break
    else:
        pos_mean = positive_events.mean(axis=0)
        neg_mean = negative_events.mean(axis=0)
        peak_denom = pos_mean[peak_ch_idx] - neg_mean[peak_ch_idx]
        if abs(peak_denom) > 1e-9:
            slopes = (pos_mean - neg_mean)[off_peak] / peak_denom
        else:
            slopes = pos_mean[off_peak]

    full_slopes = np.zeros(n_ch)
    full_slopes[off_peak] = slopes
    full_slopes[peak_ch_idx] = 1.0
    profile = np.clip(full_slopes, 0, None)

    profile = np.clip(profile, 0, None)
    if profile.max() > 0:
        profile /= profile.max()
    return profile

def compute_sample_means_for_wls(
    experiment_dir,
    experiment_samples: dict,
    fluorescence_channel_ids: list,
) -> 'np.ndarray | None':
    """
    Compute per-detector mean raw fluorescence across real experimental samples,
    for use as WLS (Poisson) weights.

    Selection priority:
      1. Samples in all_samples that are NOT in single_stain_controls and NOT
         tagged or named as unstained.
      2. If none qualify, fall back to all samples in all_samples.

    Returns a (n_channels,) float64 array, or None if no files could be read.
    """
    import re
    from pathlib import Path
    from honeychrome.controller_components.functions import sample_from_fcs

    all_samples = experiment_samples.get('all_samples', {})
    controls = set(experiment_samples.get('single_stain_controls', []))
    unstained = set(experiment_samples.get('unstained_samples', []))

    def _is_unstained(path, name):
        return (path in unstained
                or re.search(r'unstained', name, re.IGNORECASE)
                or re.search(r'unstained', path, re.IGNORECASE))

    preferred = [
        p for p, name in all_samples.items()
        if p not in controls and not _is_unstained(p, name)
    ]
    candidates = preferred if preferred else list(all_samples.keys())

    if not candidates:
        return None

    channel_sums = None
    n_events_total = 0
    for path in candidates:
        try:
            sample = sample_from_fcs(Path(experiment_dir) / path)
            fl = sample.get_events('raw')[:, fluorescence_channel_ids].astype(np.float64)
            channel_sums = fl.sum(axis=0) if channel_sums is None else channel_sums + fl.sum(axis=0)
            n_events_total += fl.shape[0]
        except Exception:
            continue

    if channel_sums is None or n_events_total == 0:
        return None

    return channel_sums / n_events_total


def _build_omega_inv(
    M: np.ndarray,
    method: str = 'OLS',
    sample_means: 'np.ndarray | None' = None,
) -> np.ndarray:
    """
    Build diagonal weight matrix Ω⁻¹ for spectral unmixing.
    M shape: (n_fluors, n_channels). Returns (n_channels, n_channels).

    For WLS (Poisson), sample_means must be provided: a (n_channels,) array of
    mean raw fluorescence across the experiment's real samples.
    Falls back to OLS if sample_means is None.
    """
    n_channels = M.shape[1]
    if method == 'WLS' and sample_means is not None:
        weights = np.where(sample_means > 1e-9, sample_means, 1.0)
    else:
        weights = np.ones(n_channels)
    return np.diag(1.0 / weights)

def calculate_spectral_process(raw_settings, spectral_model, profiles,
                                existing_spillover=None, unmixing_method='OLS',
                                experiment_dir=None, experiment_samples=None):
    from sklearn.metrics.pairwise import cosine_similarity
    from pandas import DataFrame

    fluorescence_channels = [control['label'] for control in spectral_model]
    
    # Build DataFrame with columns in spectral_model order, not dict insertion order.
    # profiles dict key order may differ from spectral_model order after JSON round-trip.
    profiles_df = DataFrame({label: profiles[label] for label in fluorescence_channels})
    M = np.array(profiles_df).T
    raw_length = np.shape(M)[1]
    unmixed_length = np.shape(M)[0]

    Mnorm = M / np.tile(np.sqrt(np.sum(M**2, axis=0)), (unmixed_length,1))
    Mnorm[np.isnan(Mnorm)] = 0
    similarity_matrix = cosine_similarity(Mnorm)
    hotspot_matrix = np.sqrt(np.abs(np.linalg.inv(similarity_matrix)))

    # calculate unmixing matrix
    variance_per_detector = np.ones(raw_length)  # trivial example... try something better like cv on each detector for brightest fluorophores?
    # otb: pure variance is too noisy and varies between samples. could be done per experiment
    # sd is a bit better, but mean (Poisson-like) works well empirically
    # we probably will want to measure the noise in the detectors on the CytKit
    sample_means = None
    if unmixing_method == 'WLS' and experiment_dir is not None and experiment_samples is not None:
        fl_ids = raw_settings.get('fluorescence_channel_ids', [])
        sample_means = compute_sample_means_for_wls(experiment_dir, experiment_samples, fl_ids)
    Omega_inv = _build_omega_inv(M, method=unmixing_method, sample_means=sample_means)
    unmixing_matrix = np.linalg.inv(M @ Omega_inv @ M.T) @ M @ Omega_inv  # "W" matrix in Novo paper

    # define unmixed channels
    pnn_raw = raw_settings['event_channels_pnn']
    scatter_channel_ids_raw = raw_settings['scatter_channel_ids']
    scatter_channels_pnn = [pnn_raw[n] for n in scatter_channel_ids_raw]
    fluorescence_channels_pnn = fluorescence_channels
    event_channels_pnn = [raw_settings['event_channels_pnn'][raw_settings['time_channel_id']], 'event_id'] + scatter_channels_pnn + fluorescence_channels_pnn
    area_channels = [s.removesuffix('-A') for s in event_channels_pnn if s.endswith("-A")]
    height_channels = [s.removesuffix('-H') for s in event_channels_pnn if s.endswith("-H")]
    width_channels = [s.removesuffix('-W') for s in event_channels_pnn if s.endswith("-W")]

    time_channel_id = 0
    event_id_channel_id = 1

    scatter_channel_ids = [event_channels_pnn.index(c) for c in scatter_channels_pnn]
    n_scatter_channels = len(scatter_channel_ids)
    fluorescence_channel_ids = [event_channels_pnn.index(c) for c in fluorescence_channels_pnn]
    n_fluorophore_channels = len(fluorescence_channel_ids)

    unmixed_settings = {
        'unmixed_samples_subdirectory': 'Unmixed',
        'area_channels': area_channels,
        'height_channels': height_channels,
        'width_channels': width_channels,
        'scatter_channels': scatter_channels_pnn, # consider stripping the -A, -H -W from this, but not sure if it matters
        'fluorescence_channels': fluorescence_channels,
        'event_channels_pnn': event_channels_pnn,
        'width_ceiling': raw_settings['width_ceiling'],
        'magnitude_ceiling': raw_settings['magnitude_ceiling'],
        'default_ceiling': raw_settings['default_ceiling'],
        'time_channel_id': time_channel_id,
        'event_id_channel_id': event_id_channel_id,
        'scatter_channel_ids': scatter_channel_ids,
        'n_scatter_channels': n_scatter_channels,
        'fluorescence_channel_ids': fluorescence_channel_ids,
        'n_fluorophore_channels': n_fluorophore_channels
    }

    # Preserve existing spillover if it is the right size; otherwise reset to identity.
    if (existing_spillover is not None
            and np.array(existing_spillover).shape == (n_fluorophore_channels, n_fluorophore_channels)):
        spillover = np.array(existing_spillover)
    else:
        spillover = np.eye(n_fluorophore_channels)


    # Extract the diagonal weights for FCS export (Ω diagonal = 1/weight)
    omega_diag = np.diag(Omega_inv)
    weights_vector = np.where(omega_diag > 0, 1.0 / omega_diag, 1.0)

    # populate process variables
    spectral_process = {
        'similarity_matrix': similarity_matrix.tolist(),
        'hotspot_matrix': hotspot_matrix.tolist(),
        'unmixing_matrix': unmixing_matrix.tolist(),
        'spillover': spillover.tolist(),
        'unmixing_method': unmixing_method,
        'unmixing_weights': weights_vector.tolist(),
    }

    # # set up unmixed channels with default transforms
    # unmixed_cytometry = {
    #     'transforms': assign_default_transforms(unmixed_settings),
    #     'plots': []
    # }
    # transformations = generate_transformations(unmixed_cytometry['transforms'])
    #
    # # initialise unmixed gating and plots
    # gating = fk.GatingStrategy()
    # for label in event_channels_pnn:
    #     gating.transformations[label] = transformations[label].xform

    return unmixed_settings, spectral_process

def sanitise_control_in_place(control):
    if control['control_type'] == 'Single Stained Spectral Control':
        pass  # gate_channel is set by the auto-generator and must not be cleared on re-generation
    elif control['control_type'] == 'Single Stained Spectral Control from Library':
        control['particle_type'] = ''
        control['gate_channel'] = ''
        control['gate_label'] = ''
    elif control['control_type'] == 'Channel Assignment':
        control['particle_type'] = ''
        control['sample_name'] = ''
        control['gate_label'] = ''
    else:
        control['particle_type'] = ''
        control['gate_channel'] = ''
        control['sample_name'] = ''
        control['gate_label'] = ''

    # print(json.dumps(control, indent=2))

def _find_default_unstained(samples: dict) -> str | None:
    """Return the tube name of the first sample whose path or name matches 'unstained', or None."""
    import re
    for path, name in samples.items():
        if re.search(r'unstained', path, re.IGNORECASE) or re.search(r'unstained', name, re.IGNORECASE):
            return name
    return None


def get_raw_events(
    sample,
    fluorescence_channel_ids: list,
    gate_label: str | None = None,
    gating_strategy=None,
    extra_channel_ids: list | None = None,
    col_order: list | None = None,
) -> np.ndarray | tuple[np.ndarray, np.ndarray]:
    """
    Return a (n_events, n_channels) float64 array of raw fluorescence values.

    If gate_label is supplied (and gating_strategy is not None), only events
    inside that gate are returned. Otherwise all events are returned.

    If extra_channel_ids is supplied (e.g. scatter channel indices), a second
    array of shape (n_events, len(extra_channel_ids)) is returned as a tuple:
        (fluorescence_array, extra_array)
    This is the foundation that every subsequent cleaning stage builds on.

    col_order: if supplied, passed to get_events() to select/reorder columns by
    PnN name (used for FACSDiscover files with inconsistent derived-parameter sets).
    """
    try:
        all_events = sample.get_events('raw', col_order=col_order)
    except (KeyError, ValueError) as e:
        logger.warning('get_raw_events: col_order failed (%s) — reading all channels', e)
        all_events = sample.get_events('raw')

    if np.any(np.isnan(all_events)):
        n_nan = int(np.isnan(all_events).sum())
        logger.warning('get_raw_events: %d NaN values — replacing with 0', n_nan)
        all_events = np.where(np.isnan(all_events), 0.0, all_events)

    if gate_label and gating_strategy:
        gate_paths = gating_strategy.find_matching_gate_paths(gate_label)
        if gate_paths:
            event_mask = gating_strategy.gate_sample(sample).get_gate_membership(gate_label)
        else:
            warnings.warn(f'get_raw_events: gate "{gate_label}" not found — returning all events.')
            event_mask = np.ones(sample.event_count, dtype=bool)
    else:
        event_mask = np.ones(sample.event_count, dtype=bool)

    gated = all_events[event_mask]
    fluor = gated[:, fluorescence_channel_ids].astype(np.float64)

    if extra_channel_ids is not None:
        extra = gated[:, extra_channel_ids].astype(np.float64)
        return fluor, extra

    return fluor
