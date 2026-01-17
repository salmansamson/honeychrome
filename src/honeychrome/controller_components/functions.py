import numpy as np
import flowkit as fk
from PySide6.QtCore import QSettings
from queue import Empty
from time import perf_counter
from functools import wraps
from pathlib import Path

from honeychrome.controller_components.transform import Transform
from honeychrome.settings import linear_a, logicle_w, logicle_m, logicle_a, log_m

q_settings = QSettings("honeychrome", "ExperimentSelector")


def define_process_plots(fluorescence_channels_x, fluorescence_channels_y, source_gate):
    process_plots = [{'type': 'hist2d', 'channel_x': x, 'channel_y': y, 'source_gate': source_gate, 'child_gates': []} if x != y
                     else {'type': 'hist1d', 'channel_x': x, 'source_gate': source_gate, 'child_gates': []}
                     for x in fluorescence_channels_x for y in fluorescence_channels_y]
    return process_plots

def all_same(lst):
    if not lst:  # Handle empty list
        return True  # or False, depending on your needs
    return all(x == lst[0] for x in lst)

def empty_queue_nowait(q):
    """Empty queue using get_nowait()"""
    items_removed = 0
    while True:
        try:
            q.get_nowait()
            items_removed += 1
        except Empty:
            break
    return items_removed

def add_recent_file(path):
    path = str(path)
    recent = q_settings.value("recent_files", [])
    if isinstance(recent, str):
        recent = [recent]
    if path in recent:
        recent.remove(path)
    recent.insert(0, path)
    q_settings.setValue("recent_files", recent)  # store full history

def export_unmixed_sample(sample_name, unmixed_folder, unmixed_event_data_without_fine_tuning, unmixed_event_channels_pnn, spillover, subsample=None):
    # note that FlowKit compensation matrix is actually spillover matrix
    unmixed_sample_name = sample_name + ' (Unmixed).fcs'
    unmixed_sample = fk.Sample(unmixed_event_data_without_fine_tuning,
                                    channel_labels=unmixed_event_channels_pnn,
                                    null_channel_list=['event_id'],
                                    compensation=spillover,
                                    sample_id=sample_name)
    unmixed_sample.export(unmixed_sample_name, subsample=subsample, directory=unmixed_folder, source='comp', include_metadata=True)

# All subfolders recursively
def get_all_subfolders_recursive(path, experiment_dir):
    """Get all subfolders recursively using pathlib"""
    p = Path(path)
    return [p.relative_to(experiment_dir)] + [folder.relative_to(experiment_dir) for folder in p.rglob('*') if folder.is_dir()]

def timer(func):
    """Decorator to report execution time of a function."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = perf_counter()
        result = func(*args, **kwargs)
        end_time = perf_counter()
        execution_time = end_time - start_time
        print(f"Function '{func.__name__}' executed in {execution_time:0.6f} seconds")
        return result
    return wrapper

def assign_default_transforms(settings, channels=None):
    if channels is None:
        channels = settings['event_channels_pnn']
    transforms = {}

    ceiling = settings['magnitude_ceiling']
    transforms['ribbon'] = {'scale_t': ceiling, 'linear_a': linear_a, 'logicle_w': logicle_w, 'logicle_m': logicle_m,
                            'logicle_a': logicle_a, 'log_m': log_m, 'id': 1, 'limits': [0, 1]}

    for label in channels:
        index = settings['event_channels_pnn'].index(label)
        if index in settings['scatter_channel_ids'] or index in settings['fluorescence_channel_ids']:
            ceiling = settings['magnitude_ceiling']
        else:
            ceiling = settings['default_ceiling']

        if label[-2:] == '-W' or label in settings['width_channels']:
            ceiling = settings['width_ceiling']

        if index in settings['scatter_channel_ids']:
            id = 0  # linear
            limits = [0, 1]
        elif index in settings['fluorescence_channel_ids']:
            id = 1  # logicle
            limits = [0, 1]
        else:
            id = 'default'
            limits = [0, 100]

        transforms[label] = {'scale_t': ceiling, 'linear_a': linear_a, 'logicle_w': logicle_w, 'logicle_m': logicle_m,
                             'logicle_a': logicle_a, 'log_m': log_m, 'id': id, 'limits': limits}

    return transforms


def update_transforms(transforms, transformations):
    for label in transformations:
        transformation = transformations[label]
        linear_a = transformation.linear_a
        logicle_w = transformation.logicle_w
        logicle_m = transformation.logicle_m
        logicle_a = transformation.logicle_a
        scale_t = transformation.scale_t
        id = transformation.id
        limits = transformation.limits
        if scale_t is not None:
            transforms[label]['scale_t'] = scale_t
        if linear_a is not None:
            transforms[label]['linear_a'] = linear_a
        if logicle_w is not None:
            transforms[label]['logicle_w'] = logicle_w
        if logicle_m is not None:
            transforms[label]['logicle_m'] = logicle_m
        if logicle_a is not None:
            transforms[label]['logicle_a'] = logicle_a
        if log_m is not None:
            transforms[label]['log_m'] = log_m
        if id is not None:
            transforms[label]['id'] = id
        if limits is not None:
            transforms[label]['limits'] = limits


def generate_transformations(transforms):
    transformations = {}
    for label in transforms:
        transform = transforms[label]
        transformations[label] = Transform(scale_t=transform['scale_t'], linear_a=transform['linear_a'],
                                           logicle_w=transform['logicle_w'], logicle_m=transform['logicle_m'],
                                           logicle_a=transform['logicle_a'], log_m=transform['log_m'])
        transformations[label].set_transform(id=transform['id'], limits=transform['limits'])

    return transformations


def apply_transfer_matrix(transfer_matrix, raw_event_data):
    return raw_event_data @ transfer_matrix


def define_quad_gates(x, y, channel_x, channel_y, transformations):
    # QuadrantDivider instances are similar to a Dimension, they take compensation_ref and tranformation_ref
    transformation_ref_x = channel_x if transformations[channel_x].xform else None
    transformation_ref_y = channel_y if transformations[channel_y].xform else None
    quad_div_x = fk.QuadrantDivider('xdiv', channel_x, compensation_ref='uncompensated', transformation_ref=transformation_ref_x, values=[x])
    quad_div_y = fk.QuadrantDivider('ydiv', channel_y, compensation_ref='uncompensated', transformation_ref=transformation_ref_y, values=[y])

    quad_divs = [quad_div_x, quad_div_y]

    # the 2 dividers above will be used to divide the space into 4 quadrants
    quad_pp = fk.gates.Quadrant(quadrant_id=f'{channel_x}+ {channel_y}+', divider_refs=['xdiv', 'ydiv'],
        divider_ranges=[(x, None), (y, None)])
    quad_pn = fk.gates.Quadrant(quadrant_id=f'{channel_x}+ {channel_y}-', divider_refs=['xdiv', 'ydiv'],
        divider_ranges=[(x, None), (None, y)])
    quad_np = fk.gates.Quadrant(quadrant_id=f'{channel_x}- {channel_y}+', divider_refs=['xdiv', 'ydiv'],
        divider_ranges=[(None, x), (y, None)])
    quad_nn = fk.gates.Quadrant(quadrant_id=f'{channel_x}- {channel_y}-', divider_refs=['xdiv', 'ydiv'],
        divider_ranges=[(None, x), (None, y)])
    quadrants = [quad_pp, quad_pn, quad_np, quad_nn]

    return quad_divs, quadrants

def define_range_gate(x1, x2, channel_x, transformations):
    transformation_ref = channel_x if transformations[channel_x].xform else None
    dim_x = fk.Dimension(channel_x, compensation_ref='uncompensated', transformation_ref=transformation_ref, range_min=x1,
                         range_max=x2)
    return dim_x

def define_polygon_gate(points, channel_x, channel_y, transformations):
    # print(points)
    transformation_ref_x = channel_x if transformations[channel_x].xform else None
    transformation_ref_y = channel_y if transformations[channel_y].xform else None
    dim_x = fk.Dimension(channel_x, compensation_ref='uncompensated', transformation_ref=transformation_ref_x, range_min=0, range_max=1)
    dim_y = fk.Dimension(channel_y, compensation_ref='uncompensated', transformation_ref=transformation_ref_y, range_min=0, range_max=1)
    return points, dim_x, dim_y

def define_rectangle_gate(pos, size, channel_x, channel_y, transformations):
    x0, y0 = pos
    Dx, Dy = size
    # x0, y0 = np.array(pos)
    # Dx, Dy = np.array(size) / 2

    transformation_ref_x = channel_x if transformations[channel_x].xform else None
    transformation_ref_y = channel_y if transformations[channel_y].xform else None
    dim_x = fk.Dimension(channel_x, compensation_ref='uncompensated', transformation_ref=transformation_ref_x, range_min=x0,
                         range_max=x0 + Dx)
    dim_y = fk.Dimension(channel_y, compensation_ref='uncompensated', transformation_ref=transformation_ref_y, range_min=y0,
                         range_max=y0 + Dy)

    return dim_x, dim_y

def define_ellipse_gate(pos, size, angle, channel_x, channel_y, transformations):
    theta = np.deg2rad(angle)
    R = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    coordinates = np.array(pos) + 0.5 * R @ np.array(size)

    w, h = np.array(size)

    # Covariance matrix
    D = np.diag([w, h])
    covariance_matrix = R @ D @ R.T
    distance_square = w * h

    transformation_ref_x = channel_x if transformations[channel_x].xform else None
    transformation_ref_y = channel_y if transformations[channel_y].xform else None

    dim_x = fk.Dimension(channel_x, compensation_ref='uncompensated', transformation_ref=transformation_ref_x, range_min=0,
                         range_max=1)
    dim_y = fk.Dimension(channel_y, compensation_ref='uncompensated', transformation_ref=transformation_ref_y, range_min=0,
                         range_max=1)

    # print(pos, size, angle)
    # print(coordinates)
    # print(w, h)
    # print(covariance_matrix)
    # print(distance_square)
    # print(transformations[channel_x].limits)
    # print(transformations[channel_y].limits)

    return dim_x, dim_y, coordinates, covariance_matrix, distance_square


def apply_gates_in_place(data_for_cytometry_plots, gates_to_calculate=None):
    # calculate only gates in gates_to_calculate
    # gates_to_calculate should be in order of ancestry (parent to child)

    events = data_for_cytometry_plots['event_data']
    pnn = data_for_cytometry_plots['pnn']
    transforms = data_for_cytometry_plots['transformations']
    lookup_tables = data_for_cytometry_plots['lookup_tables']
    gating = data_for_cytometry_plots['gating']
    gate_membership = data_for_cytometry_plots['gate_membership']

    # loop through gates, produce gate_membership mask for each
    # ignore quadrants but loop through them in parent quadrantgate
    gate_ids = gating.get_gate_ids()
    for gate_id in gate_ids:
        if gate_id[0] in gates_to_calculate:
            if gating._get_gate_node(gate_id[0], gate_id[1]).gate_type != 'Quadrant': # bit of a hack. Can't find a better way of excluding Quadrant
                gate = gating.get_gate(gate_id[0])
                parent_id = gating.get_parent_gate_id(gate_id[0])
                if parent_id is None:
                    parent_id = ('root',)

                channels = gate.get_dimension_ids()
                if len(channels) == 1:
                    xchan = channels[0]
                    ix = pnn.index(xchan)
                    x = events[:, ix]
                    transform_x = transforms[xchan]
                    scale_x = transform_x.scale
                    indices_x_data_searchsorted = np.searchsorted(scale_x, x) - 2
                    if len(scale_x) > len(lookup_tables[gate_id[0]]):
                        indices_x_data_searchsorted[indices_x_data_searchsorted >= len(lookup_tables[gate_id[0]])] = len(lookup_tables[gate_id[0]]) - 1 #todo temporary solution until we implement custom sample gates for time
                    indices_data_digitized_flattened = indices_x_data_searchsorted

                else:#len(channels) == 2:
                    if gate.gate_type != 'QuadrantGate':  # 2 channels
                        xchan = channels[0]
                        ychan = channels[1]
                    else:  # quad gate
                        xchan = gate.dimensions[0].dimension_ref
                        ychan = gate.dimensions[1].dimension_ref
                    ix = pnn.index(xchan)
                    iy = pnn.index(ychan)
                    x = events[:, ix]
                    y = events[:, iy]
                    transform_x = transforms[xchan]
                    transform_y = transforms[ychan]
                    scale_x = transform_x.scale
                    scale_y = transform_y.scale
                    indices_x_data_searchsorted = np.searchsorted(scale_x, x) - 2
                    indices_y_data_searchsorted = np.searchsorted(scale_y, y) - 2
                    hist_bins_x = transform_x.scale_bins + 1
                    indices_data_digitized_flattened = indices_x_data_searchsorted * hist_bins_x + indices_y_data_searchsorted

                if gate.gate_type == 'QuadrantGate':
                    quadrant_names = gate.quadrants.keys()
                    for name in quadrant_names:
                        mask = lookup_tables[name][indices_data_digitized_flattened]
                        gate_membership[name] = mask * gate_membership[parent_id[0]]
                else:
                    mask = lookup_tables[gate_id[0]][indices_data_digitized_flattened]
                    gate_membership[gate_id[0]] = mask * gate_membership[parent_id[0]]

    # return gate_membership

def initialise_hists(plots, data_for_cytometry_plots):
    # loop over plots, produce set of histograms, default stats
    fluoro_indices = data_for_cytometry_plots['fluoro_indices']
    transformations = data_for_cytometry_plots['transformations']
    hists = []
    if plots:
        for n, plot in enumerate(plots):
            if plot['type'] == 'hist1d':
                bins = transformations[plot['channel_x']].scale_bins
                histogram = np.zeros(bins+1)
            elif plot['type'] == 'hist2d':
                bins_x = transformations[plot['channel_x']].scale_bins
                bins_y = transformations[plot['channel_y']].scale_bins
                histogram = np.zeros((bins_x+1, bins_y+1))
            else:  # 'ribbon'
                bins = transformations['ribbon'].scale_bins
                histogram = np.zeros((bins+1, len(fluoro_indices)))
            hists.append(histogram)
    return hists

def initialise_stats(gating):
    statistics = {'root': {'n_events_gate': 0, 'p_gate_total': 1., 'p_gate_parent': 1., 'event_conc': np.nan}}
    if gating:
        for gate_id in gating.get_gate_ids():
            if gating._get_gate_node(gate_id[0], gate_id[1]).gate_type != 'QuadrantGate': # bit of a hack. Can't find a better way of excluding Quadrants
                statistics[gate_id[0]] = {'n_events_gate': 0, 'p_gate_total': 0, 'p_gate_parent': 0, 'event_conc': np.nan}
    return statistics


def calc_hists(data_for_cytometry_plots, indices_plots_to_calculate=None):
    plots = data_for_cytometry_plots['plots']
    gate_membership = data_for_cytometry_plots['gate_membership']

    if indices_plots_to_calculate is not None:
        plots = [plots[n] for n in indices_plots_to_calculate]
    pnn = data_for_cytometry_plots['pnn']
    transformations = data_for_cytometry_plots['transformations']
    event_data = data_for_cytometry_plots['event_data']
    fluoro_indices = data_for_cytometry_plots['fluoro_indices']

    hists = []
    for n, plot in enumerate(plots):
        source_gate = plot['source_gate']
        mask = gate_membership[source_gate]
        if plot['type'] == 'hist1d':
            id_channel = pnn.index(plot['channel_x'])
            transform = transformations[plot['channel_x']]
            histogram = calc_hist1d(event_data, mask, id_channel, transform)
        elif plot['type'] == 'hist2d':
            id_channel_x = pnn.index(plot['channel_x'])
            id_channel_y = pnn.index(plot['channel_y'])
            transform_x = transformations[plot['channel_x']]
            transform_y = transformations[plot['channel_y']]
            histogram = calc_hist2d(event_data, mask, id_channel_x, id_channel_y, transform_x, transform_y)
        else: # 'ribbon'
            histogram = calc_ribbon_plot(event_data, mask, fluoro_indices, transformations['ribbon'])

        # add to existing array
        hists.append(histogram)
    return hists

def calc_stats(data_for_cytometry_plots, initialise=True):
    statistics = {}
    # gate_ids = data_for_cytometry_plots['lookup_tables'].keys()
    gating = data_for_cytometry_plots['gating']
    gate_membership = data_for_cytometry_plots['gate_membership']
    event_data = data_for_cytometry_plots['event_data']

    if event_data is not None:
        if initialise:
            statistics_old = initialise_stats(gating)
        else:
            statistics_old = data_for_cytometry_plots['statistics']

        ###### first version does total stats
        # n_events_total = len(data_for_cytometry_plots['event_data'])
        # statistics['root'] = {'n_events_gate': n_events_total, 'p_gate_total': 1., 'p_gate_parent': 1.}
        # for gate_id in gate_ids:
        #     n_events_gate = gate_membership[gate_id[0]].sum()
        #     p_gate_total = n_events_gate / n_events_total
        #     if gate_ids[0][1]==('root',):
        #         p_gate_parent = p_gate_total
        #     else:
        #         n_events_parent = gate_membership[gate_id[0][1][-1]].sum()
        #         p_gate_parent = n_events_gate / n_events_parent
        #     statistics[gate_id[0]] = {'n_events_gate':n_events_gate, 'p_gate_total':p_gate_total, 'p_gate_parent':p_gate_parent}

        ###### second version adds to previous stats
        n_events_total_old = statistics_old['root']['n_events_gate']
        n_events_total_new = len(event_data)
        n_events_total = n_events_total_old + n_events_total_new
        statistics['root'] = {'n_events_gate': n_events_total, 'p_gate_total': 1., 'p_gate_parent': 1., 'event_conc': np.nan}
        for gate_id_full in gating.get_gate_ids():
            if gating._get_gate_node(gate_id_full[0], gate_id_full[1]).gate_type != 'QuadrantGate':  # bit of a hack. Can't find a better way of excluding Quadrants
                gate_id = gate_id_full[0]
                # parent_id = gate_id[0][1][-1]
                parent_id = data_for_cytometry_plots['gating'].get_parent_gate_id(gate_id)
                if parent_id is None:
                    parent_id = 'root'
                else:
                    parent_id = gating.get_parent_gate_id(gate_id)
                    if gating._get_gate_node(parent_id[0], parent_id[1]).gate_type != 'QuadrantGate':
                        parent_id = parent_id[0]
                    else:
                        parent_id = parent_id[1][-1]

                n_events_gate_old = statistics_old[gate_id]['n_events_gate']
                n_events_gate_new = gate_membership[gate_id].sum()
                n_events_gate = int(n_events_gate_old + n_events_gate_new)
                p_gate_total = n_events_gate / n_events_total if n_events_total != 0 else 0

                if parent_id == 'root':
                    p_gate_parent = p_gate_total
                else:
                    n_events_parent_old = statistics_old[parent_id]['n_events_gate']
                    n_events_parent_new = gate_membership[parent_id].sum()
                    n_events_parent = n_events_parent_old + n_events_parent_new
                    p_gate_parent = n_events_gate / n_events_parent if n_events_parent != 0 else 0

                # print(gate_id, parent_id)

                statistics[gate_id] = {'n_events_gate': n_events_gate, 'p_gate_total': p_gate_total, 'p_gate_parent': p_gate_parent, 'event_conc': np.nan}

    return statistics

def calc_ribbon_plot(event_data, mask, fluoro_indices, transform):
    heatmap = np.apply_along_axis(lambda x: np.histogram(x, bins=transform.scale)[0], axis=0, arr=event_data[mask][:, fluoro_indices])

    # make sure all unit bins get lowest LUT
    max_value = heatmap.max()
    mask_1 = (heatmap > 1)
    heatmap[mask_1] += max_value//255+1  # Maps to LUT[1]

    return heatmap


def calc_hist2d(event_data, mask, id_channel_x, id_channel_y, transform_x, transform_y):
    x = event_data[mask, id_channel_x]
    y = event_data[mask, id_channel_y]

    # Calculate 2D histogram (density)
    heatmap, xedges, yedges = np.histogram2d(x, y, bins=[transform_x.scale, transform_y.scale])

    # make sure all unit bins get lowest LUT
    max_value = heatmap.max()
    mask_1 = (heatmap > 1)
    heatmap[mask_1] += max_value//255+1  # Maps to LUT[1]

    return heatmap


def calc_hist1d(event_data, mask, id_channel, transform):
    x = event_data[mask, id_channel]

    # Calculate 1D histogram
    count, xedges = np.histogram(x, bins=transform.scale)
    return count  # note need to pad length + 1 at end

def raw_gates_list(gating):
    gate_ids = gating.get_gate_ids()
    gate_list = [g[0] for g in gate_ids]
    return gate_list

def get_set_or_initialise_label_offset(plot, gate_name, label_offset=None):
    if 'label_offsets' not in plot:
        plot['label_offsets'] = {gate_name: label_offset} #initialise
    else:
        if label_offset is None:
            if gate_name in plot['label_offsets']:
                label_offset = plot['label_offsets'][gate_name] #get
        else:
            plot['label_offsets'][gate_name] = label_offset #set

    return label_offset

def rename_label_offset(plot, old_gate_name, gate_name):
    if 'label_offsets' in plot:
        if old_gate_name in plot['label_offsets']:
            plot['label_offsets'][gate_name] = plot['label_offsets'][old_gate_name]
            plot['label_offsets'].pop(old_gate_name)