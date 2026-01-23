import warnings

import numpy as np
from flowkit import GatingStrategy


import honeychrome.settings as settings


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

def calculate_spectral_process(raw_settings, spectral_model, profiles):
    from sklearn.metrics.pairwise import cosine_similarity
    import pandas as pd

    profiles_df = pd.DataFrame(profiles)
    similarity_matrix = cosine_similarity(np.array(profiles_df).T)

    # calculate unmixing matrix
    M = np.array(profiles_df).T
    raw_length = np.shape(M)[1]
    variance_per_detector = np.ones(raw_length)  # trivial example... try something better like cv on each detector for brightest fluorophores?
    Omega_inv = np.diag(1 / variance_per_detector)  # This is our weight matrix
    unmixing_matrix = np.linalg.inv(M @ Omega_inv @ M.T) @ M @ Omega_inv  # "W" matrix in Novo paper

    # define unmixed channels
    pnn_raw = raw_settings['event_channels_pnn']
    fluorescence_channels = [control['label'] for control in spectral_model]
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

    # set up default spillover matrix
    spillover = np.eye(unmixed_settings['n_fluorophore_channels'])

    # populate process variables
    spectral_process = {
        'similarity_matrix': similarity_matrix.tolist(),
        'unmixing_matrix': unmixing_matrix.tolist(),
        'spillover': spillover.tolist()
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
        control['gate_channel'] = ''
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
