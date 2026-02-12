import warnings
from copy import deepcopy

import numpy as np
from PySide6.QtCore import QObject, Signal, QTimer
from flowkit import GatingStrategy, Dimension, gates
from flowio import FlowData

from honeychrome.controller_components.functions import timer, apply_gates_in_place, apply_transfer_matrix, calc_stats, all_same, assign_default_transforms, generate_transformations
from honeychrome.controller_components.gml_functions_mod_from_flowkit import to_gml
from honeychrome.settings import settings_default, process_default, cytometry_default
from honeychrome.view_components.busy_cursor import with_busy_cursor

import logging
logger = logging.getLogger(__name__)

class ImportFCSController(QObject):
    finished = Signal()

    def __init__(self, experiment, bus=None):
        super().__init__()

        # connect
        self.experiment = experiment
        self.bus = bus

    @with_busy_cursor
    def reconfigure_experiment_from_fcs_files(self):
        self.experiment.scan_sample_tree()
        experiment_dir = self.experiment.generate_subdirs()
        # single_stain_controls = self.experiment.samples['single_stain_controls']
        all_samples = self.experiment.samples['all_samples']
        raw_samples = all_samples.keys()

        if len(raw_samples) > 0:
            try:
                # load samples one by one, print name, datetime, number of events, file location
                # all_sample_meta = {}
                # all_sample_channels = {}
                all_sample_pnn = {}
                all_sample_pnr = {}
                for n, sample_path in enumerate(raw_samples):
                    sample_metadata = FlowData(experiment_dir / sample_path, only_text=True, use_header_offsets=True)
                    all_sample_pnn[sample_path] = sample_metadata.pnn_labels
                    all_sample_pnr[sample_path] = sample_metadata.pnr_values

                    if self.bus:
                        self.bus.progress.emit(n, len(raw_samples))

                # extract channel names - check that channel names are consistent
                all_sample_pnn = [list(all_sample_pnn[sample_path]) for sample_path in raw_samples]
                all_sample_pnr = [list(all_sample_pnr[sample_path]) for sample_path in raw_samples]
                all_sample_pnr_scatter_and_fluorescence = np.array(all_sample_pnr)[:,sample_metadata.scatter_indices + sample_metadata.fluoro_indices]

                if all_same(all_sample_pnn):  # then reconstitute, else warn
                    # check all pnr the same
                    pnr_same = [all_same(list(all_sample_pnr_scatter_and_fluorescence[:, n])) for n in range(len(sample_metadata.scatter_indices + sample_metadata.fluoro_indices))]
                    if not np.array(pnr_same).prod():
                        pnr_values = set(list(all_sample_pnr_scatter_and_fluorescence.flatten()))
                        text = f'Channel range values (PNR) are not consistent in FCS files. The following values were found: {pnr_values}. This could cause errors when applying gates.'
                        warnings.warn(text)
                        # if self.bus:
                        #     self.bus.warningMessage.emit(text)

                    # other bits of experiment reset to default
                    self.experiment.settings['unmixed'] = deepcopy(settings_default['unmixed'])
                    self.experiment.process = deepcopy(process_default)
                    self.experiment.cytometry = deepcopy(cytometry_default)

                    # set up all raw settings
                    time_channel_id = sample_metadata.time_index
                    scatter_channel_ids = sample_metadata.scatter_indices
                    fluorescence_channel_ids = sample_metadata.fluoro_indices
                    event_channels_pnn = all_sample_pnn[0]
                    event_channels_pnn_stripped = event_channels_pnn.copy()
                    for suffix in ['-A', '-H', '-W']:
                        event_channels_pnn_stripped = [c.removesuffix(suffix) if c.endswith(suffix) else c for c in event_channels_pnn_stripped]

                    if 'event_id' in event_channels_pnn:
                        event_id_channel_id = event_channels_pnn.index('event_id')
                    else:
                        event_id_channel_id = None

                    area_channels = [s.removesuffix('-A') for s in event_channels_pnn if s.endswith("-A")]
                    height_channels = [s.removesuffix('-H') for s in event_channels_pnn if s.endswith("-H")]
                    width_channels = [s.removesuffix('-W') for s in event_channels_pnn if s.endswith("-W")]
                    pnr = all_sample_pnr[0]
                    magnitude_ceiling = self.experiment.settings['raw']['magnitude_ceiling']
                    width_ceiling = self.experiment.settings['raw']['width_ceiling']
                    default_ceiling = self.experiment.settings['raw']['default_ceiling']
                    if len(area_channels) > 0:
                        magnitude_ceiling = float(np.max([pnr[event_channels_pnn_stripped.index(c)] for c in area_channels]))
                    if len(height_channels) > 0:
                        magnitude_ceiling = float(np.max([pnr[event_channels_pnn_stripped.index(c)] for c in height_channels]))
                    if len(width_channels) > 0:
                        width_ceiling = float(np.max([pnr[event_channels_pnn_stripped.index(c)] for c in width_channels]))
                    n_scatter_channels = len(scatter_channel_ids)
                    n_fluorophore_channels = len(fluorescence_channel_ids)

                    self.experiment.settings['raw']['area_channels'] = area_channels
                    self.experiment.settings['raw']['height_channels'] = height_channels
                    self.experiment.settings['raw']['width_channels'] = width_channels
                    self.experiment.settings['raw']['scatter_channels'] = list(set([event_channels_pnn_stripped[i] for i in scatter_channel_ids]))
                    self.experiment.settings['raw']['fluorescence_channels'] = list(set([event_channels_pnn_stripped[i] for i in fluorescence_channel_ids]))
                    self.experiment.settings['raw']['event_channels_pnn'] = event_channels_pnn
                    self.experiment.settings['raw']['width_ceiling'] = width_ceiling
                    self.experiment.settings['raw']['magnitude_ceiling'] = magnitude_ceiling
                    self.experiment.settings['raw']['default_ceiling'] = default_ceiling
                    self.experiment.settings['raw']['time_channel_id'] = time_channel_id
                    self.experiment.settings['raw']['event_id_channel_id'] = event_id_channel_id
                    self.experiment.settings['raw']['scatter_channel_ids'] = scatter_channel_ids
                    self.experiment.settings['raw']['n_scatter_channels'] = n_scatter_channels
                    self.experiment.settings['raw']['fluorescence_channel_ids'] = fluorescence_channel_ids
                    self.experiment.settings['raw']['n_fluorophore_channels'] = n_fluorophore_channels

                    # set up raw transforms
                    self.experiment.cytometry['raw_transforms'] = assign_default_transforms(self.experiment.settings['raw'])
                    raw_transformations = generate_transformations(self.experiment.cytometry['raw_transforms'])

                    # set up raw gating
                    raw_gating = GatingStrategy()
                    for label in event_channels_pnn:
                        raw_gating.transformations[label] = raw_transformations[label].xform

                    if 'FSC' in area_channels:
                        morph_x = 'FSC-A'
                    elif 'FSC' in height_channels:
                        morph_x = 'FSC-H'
                    else:
                        morph_x = None

                    if morph_x is not None:
                        if 'SSC' in area_channels:
                            morph_y = 'SSC-A'
                        elif 'SSC' in height_channels:
                            morph_y = 'SSC-H'
                        else:
                            morph_y = None

                    if (morph_x is not None) and (morph_y is not None):
                        sing_x = morph_x
                        if 'FSC' in width_channels:
                            sing_y = 'FSC-W'
                        elif (sing_x == 'FSC-A') and 'FSC' in height_channels:
                            sing_y = 'FSC-H'
                        else:
                            sing_y = None

                    time_plot = None
                    morph_plot = None
                    singlet_plot = None
                    label = 'root'
                    if (morph_x is not None) and (morph_y is not None):
                        label = 'Cells'
                        # range_max_x = raw_transformations[morph_x].xform.inverse(1)
                        # range_max_y = raw_transformations[morph_y].xform.inverse(1)
                        dim_x = Dimension(morph_x, range_min=0.2, range_max=0.8, transformation_ref=morph_x)
                        dim_y = Dimension(morph_y, range_min=0.2, range_max=0.8, transformation_ref=morph_y)
                        gate = gates.RectangleGate(label, dimensions=[dim_x, dim_y])
                        raw_gating.add_gate(gate, gate_path=('root',))
                        morph_plot = [{'type': 'hist2d', 'channel_x': morph_x, 'channel_y': morph_y, 'source_gate': 'root', 'child_gates': ['Cells']}]

                        if (sing_x is not None) and (sing_y is not None):
                            label = 'Singlets'
                            if sing_y == 'FSC-W':
                                dim_x = Dimension(sing_x, range_min=0.2, range_max=0.8, transformation_ref=sing_x)
                                dim_y = Dimension(sing_y, range_min=0.2, range_max=0.8, transformation_ref=sing_y)
                                gate = gates.RectangleGate(label, dimensions=[dim_x, dim_y])
                            else:  # FSC-H
                                dim_x = Dimension(sing_x, range_min=0, range_max=1, transformation_ref=sing_x)
                                dim_y = Dimension(sing_y, range_min=0, range_max=1, transformation_ref=sing_y)
                                vertices = [(0.2, 0.1), (0.8, 0.7), (0.8, 0.9), (0.2, 0.3)]
                                gate = gates.PolygonGate(label, dimensions=[dim_x, dim_y], vertices=vertices)
                            raw_gating.add_gate(gate, gate_path=('root', 'Cells'))
                            singlet_plot = [{'type': 'hist2d', 'channel_x': sing_x, 'channel_y': sing_y, 'source_gate': 'Cells', 'child_gates': ['Singlets']}]

                    # set up raw plots
                    # plots is list of dicts
                    # type:
                    # ---hist1d: channel_x, source_gate, child_gates
                    # ---hist2d: channel_x, channel_y, source_gate, child_gates
                    # ---ribbon: source_gate, child_gates
                    if time_channel_id:
                        time_plot = [{'type': 'hist1d', 'channel_x': event_channels_pnn[time_channel_id], 'source_gate': 'root', 'child_gates': []}]
                    ribbon_plot = [{'type': 'ribbon', 'source_gate': label, 'child_gates': []}]
                    fluorescence_plots = [{'type': 'hist1d', 'channel_x': event_channels_pnn[i], 'source_gate': label, 'child_gates': []} for i in fluorescence_channel_ids]

                    raw_plots = []
                    if time_plot:
                        raw_plots += time_plot
                    if morph_plot:
                        raw_plots += morph_plot
                    if singlet_plot:
                        raw_plots += singlet_plot
                    raw_plots += ribbon_plot
                    raw_plots += fluorescence_plots

                    self.experiment.cytometry['raw_gating'] = to_gml(raw_gating)
                    self.experiment.cytometry['raw_plots'] = raw_plots
                    self.experiment.cytometry['gating'] = None
                    self.experiment.save()

                    text = (f'Experiment successfully configured for imported FCS files.\n\n'
                            f'Number of FCS files imported: {len(raw_samples)}\n'
                            f'Number of scatter channels: {n_scatter_channels}\n'
                            f'Number of fluorescence channels: {n_fluorophore_channels}\n'
                            f'Area channels: {self.experiment.settings['raw']['area_channels']}\n'
                            f'Height channels: {self.experiment.settings['raw']['height_channels']}\n'
                            f'Width channels: {self.experiment.settings['raw']['width_channels']}\n'
                            f'Scatter channels: {self.experiment.settings['raw']['scatter_channels']}\n'
                            f'Fluorescence channels: {self.experiment.settings['raw']['fluorescence_channels']}\n'
                            f'Magnitude ceiling: {self.experiment.settings['raw']['magnitude_ceiling']}\n'
                            f'Time channel ID: {self.experiment.settings['raw']['time_channel_id']}\n'
                            f'Event ID channel ID: {self.experiment.settings['raw']['event_id_channel_id']}\n'
                            )
                    logger.info(text)
                    if self.bus:
                        self.bus.reloadExpRequested.emit()
                        self.bus.popupMessage.emit(text)
                else:
                    text = ('Cannot set up the experiment file: \n'
                            'the FCS files supplied do not have a consistent set of channels (channel names and ranges). \n'
                            'Please make sure the FCS files are all from a single experiment on a single instrument.')
                    warnings.warn(text)
                    if self.bus:
                        self.bus.warningMessage.emit(text)

            except Exception as e:
                text = (f'Cannot set up the experiment file: \n'
                        f'the FCS files supplied do not have a consistent set of channels (channel names and ranges). \n'
                        f'Please make sure the FCS files are all from a single experiment on a single instrument.\n'
                        f'Exception:\n'
                        f'{e}')
                warnings.warn(text)
                if self.bus:
                    self.bus.warningMessage.emit(text)

        else:
            text = 'No FCS files found in the experiment <tt>Raw</tt> folder.'
            warnings.warn(text)
            if self.bus:
                self.bus.warningMessage.emit(text)

        self.finished.emit()



if __name__ == "__main__":
    from pathlib import Path
    from honeychrome.controller import Controller

    kc = Controller()
    base_directory = Path.home() / 'spectral_cytometry'
    experiment_name = base_directory / '20240620 Spectral Symposium-poor cell unmixed'
    experiment_path = experiment_name.with_suffix('.kit')
    kc.load_experiment(experiment_path) # note this loads first sample too and runs calculate all histograms and statistics
    import_fcs_controller = ImportFCSController(kc.experiment, None)
    import_fcs_controller.reconfigure_experiment_from_fcs_files()

