import json
import re
import warnings

import numpy as np
from PySide6.QtCore import QObject, Signal, QTimer
# from PySide6.QtWidgets import QApplication
import flowkit as fk

from honeychrome.controller_components.functions import timer
from honeychrome.controller_components.spectral_functions import get_best_channel, get_profile
from honeychrome.controller_components.spectral_librarian import SpectralLibrary
from honeychrome.experiment_model import check_fcs_matches_experiment
from honeychrome.view_components.busy_cursor import with_busy_cursor

# connect to spectral library
spectral_library = SpectralLibrary()

class ProfileUpdater:
    def __init__(self, controller, bus):
        self.controller = controller
        self.bus = bus
        self.experiment_dir = controller.experiment_dir
        self.samples = controller.experiment.samples
        self.spectral_model = controller.experiment.process['spectral_model']
        self.profiles = controller.experiment.process['profiles']
        self.event_channels_pnn = controller.experiment.settings['raw']['event_channels_pnn']
        self.raw_gating = controller.raw_gating
        self.n_fluorophore_channels = None
        self.fluorescence_channels_pnn = []
        self.refresh()

    def refresh(self):
        self.controller.filter_raw_fluorescence_channels()
        self.n_fluorophore_channels = len(self.controller.filtered_raw_fluorescence_channel_ids)
        self.fluorescence_channels_pnn.clear()
        self.fluorescence_channels_pnn.extend([self.event_channels_pnn[i] for i in self.controller.filtered_raw_fluorescence_channel_ids])

    def flush(self):
        self.refresh()
        controls = [control['label'] for control in self.spectral_model]
        labels = list(self.profiles.keys())
        for label in labels:
            if label not in controls:
                self.profiles.pop(label)

        # n_fluorophore_channels_changed = False
        # labels = list(self.profiles.keys())
        # for label in labels:
        #     if len(self.profiles[label]) != self.n_fluorophore_channels:
        #         self.profiles.pop(label)
        #         n_fluorophore_channels_changed = True
        #
        # if n_fluorophore_channels_changed:
        #     warnings.warn('Selected number of fluorophores has changed. Previous controls have been flushed.')
        #     if self.bus:
        #         self.bus.warningMessage.emit('Selected number of fluorophores has changed. Previous controls have been flushed.')

    def generate(self, control, search_results):
        if control['control_type'] == 'Single Stained Spectral Control':
            if control['sample_name'] and control['gate_label']:
                all_samples_reverse_lookup = {v: k for k, v in self.samples['all_samples'].items()}
                tubename = control['sample_name']
                sample_path = all_samples_reverse_lookup[tubename]
                nevents = self.samples['all_sample_nevents'][sample_path]
                if nevents > 0:
                    full_sample_path = str(self.experiment_dir / sample_path)
                    sample = fk.Sample(full_sample_path)
                    control['sample_path'] = full_sample_path
                    profile = get_profile(sample, control['gate_label'], self.raw_gating, self.controller.filtered_raw_fluorescence_channel_ids)
                    control['gate_channel'] = self.fluorescence_channels_pnn[np.argmax(profile)]
                    profile = profile.tolist()
                    self.profiles[control['label']] = profile

                    profile_dict = dict(zip(self.fluorescence_channels_pnn, profile))
                    spectral_library.deposit_control_with_profile_and_experiment_dir(control, profile_dict, str(self.experiment_dir))

                    return True

        elif control['control_type'] == 'Single Stained Spectral Control from Library':
            if control['sample_name'] and search_results:
                for n in search_results:
                    if control['sample_name'] == search_results[n]['current_control_list']:
                        profile = list(json.loads(search_results[n]['profile_dict']).values())
                        self.profiles[control['label']] = profile
                        return True

        elif control['control_type'] == 'Channel Assignment':
            if control['gate_channel']:
                n = self.fluorescence_channels_pnn.index(control['gate_channel'])
                profile = np.zeros(self.n_fluorophore_channels)
                profile[n] = 1
                self.profiles[control['label']] = profile.tolist()
                return True

        # remove control from profiles dict if not set correctly
        self.profiles[control['label']] = None
        self.profiles.pop(control['label'])
        return False

    def pop_control(self, label):
        self.profiles[label] = None
        self.profiles.pop(label)

class SpectralAutoGenerator(QObject):
    def __init__(self, bus, controller):
        super().__init__()

        # connect
        self.controller = controller
        self.bus = bus

        self.event_channels_pnn = self.controller.experiment.settings['raw']['event_channels_pnn']

        self.controller.filter_raw_fluorescence_channels()
        self.fluorescence_channel_ids = self.controller.filtered_raw_fluorescence_channel_ids
        self.fluorescence_channels_pnn = [self.event_channels_pnn[i] for i in self.fluorescence_channel_ids]

        self.raw_gating = self.controller.raw_gating
        self.raw_plots = self.controller.data_for_cytometry_plots_raw['plots']
        self.spectral_model = self.controller.experiment.process['spectral_model']
        self.profiles = self.controller.experiment.process['profiles']
        self.samples = self.controller.experiment.samples
        self.experiment_dir = self.controller.experiment_dir

        self.spectral_model.clear()
        self.profiles.clear()
        self.unstained_negative = None
        self.progress_target = len(self.samples['single_stain_controls'])
        # self.progress_target = len(self.samples['single_stain_controls'][:5]) # quick test

        # (sample name, label, sample path, particle_type (cells/beads), control_type (positive only, positive and negative, autofluorescence), gate channel
        self.base_gate_label = 'root'
        raw_gate_names = [g[0].lower() for g in self.controller.raw_gating.get_gate_ids()]
        for gate in self.controller.experiment.process['base_gate_priority_order']:
            if gate.lower() in raw_gate_names:
                self.base_gate_label = gate
                break

    @with_busy_cursor
    def run(self):
        if self.controller.experiment.process['negative_type'] == 'unstained':
            success = self.get_unstained_negative()
            if not success:
                if self.bus:
                    QTimer.singleShot(100, lambda: self.bus.statusMessage.emit(f'Failed to generate profile of unstained negative.'))
        for n in range(self.progress_target):
            if self.bus:
                self.bus.progress.emit(n, self.progress_target)
            success = self.generate_spectral_control(n)   # do your expensive work here
            if not success:
                if self.bus:
                    QTimer.singleShot(100, lambda: self.bus.statusMessage.emit(f'Failed to generate profile of spectral control {n}.'))
                break # is this necessary?
            if self.bus:
                self.bus.spectralControlAdded.emit()

        # update all raw plots at end to avoid timing issues in main loop
        for index, plot in enumerate(self.raw_plots):
            if self.bus:
                self.bus.updateRois.emit('raw', index)

        print('SpectralAutoGenerator: regenerated spectral model and raw gating hierarchy:')
        print(self.raw_gating.get_gate_hierarchy())

        if self.bus:
            # self.bus.changedGatingHierarchy.emit('raw', 'root')
            self.bus.progress.emit(self.progress_target, self.progress_target)
            self.bus.spectralModelUpdated.emit()
            self.bus.showSelectedProfiles.emit(None)

    def get_unstained_negative(self):
        try:
            sample_path = None
            for path in self.samples['all_samples']:
                match_path = re.findall('([Uu]nstained)', path)
                match_tubename = re.findall('([Uu]nstained)', self.samples['all_samples'][path])
                if match_path or match_tubename:
                    sample_path = path
                    break
            if sample_path:
                full_sample_path = str(self.experiment_dir / sample_path)
                sample = fk.Sample(full_sample_path)

                # using unstained negative, define Pos and Neg Unstained if they don't already exist
                positive_gate_label = 'Pos Unstained'
                negative_gate_label = 'Neg Unstained'

                for target_gate_label in [positive_gate_label, negative_gate_label]:
                    if not self.raw_gating.find_matching_gate_paths(target_gate_label):
                        channel_x = 'FSC-A'
                        channel_y = 'SSC-A'
                        dim_x = fk.Dimension(channel_x, range_min=0.2, range_max=0.8, transformation_ref=channel_x)
                        dim_y = fk.Dimension(channel_y, range_min=(0.1 if target_gate_label==positive_gate_label else 0.3), range_max=(0.7 if target_gate_label==positive_gate_label else 0.9), transformation_ref=channel_y)
                        target_gate = fk.gates.RectangleGate(target_gate_label, dimensions=[dim_x, dim_y])
                        self.raw_gating.add_gate(target_gate, gate_path=('root',))

                        #### if raw_plots contains a 2D hist on channel_x and channel_y with no child gates except for pos and neg, add gate to it, otherwise create it
                        target_plot = None
                        for n, plot in enumerate(self.raw_plots):
                            if (plot['type'] == 'hist2d'
                                    and plot['channel_x'] == channel_x
                                    and plot['channel_y'] == channel_y
                                    and plot['source_gate'] == 'root'
                                    and not set(plot['child_gates']) - {positive_gate_label, negative_gate_label}):
                                target_plot = plot
                        if not target_plot:
                            # append plot
                            target_plot = {'type': 'hist2d', 'channel_x': channel_x, 'channel_y': channel_y, 'source_gate': 'root', 'child_gates': [positive_gate_label, negative_gate_label]}
                            self.raw_plots.append(target_plot)
                            self.bus.showNewPlot.emit('raw')
                        if target_gate_label not in target_plot['child_gates']:
                            target_plot['child_gates'].append(target_gate_label)

                self.unstained_negative = get_profile(sample, negative_gate_label, self.raw_gating, self.fluorescence_channel_ids)
                return True
            else:
                raise Exception(f'No sample in Single Stain Controls is named "Unstained". ')
        except Exception as e:
            text = f'Failed to generate profile of unstained negative. {e} Setting negative type to "internal".'
            warnings.warn(text)
            if self.bus:
                self.bus.warningMessage.emit(text)
            self.controller.experiment.process['negative_type'] = 'internal'
            return False

    @timer
    def generate_spectral_control(self, n):
        sample_path = self.samples['single_stain_controls'][n]

        nevents = self.samples['all_sample_nevents'][sample_path]
        tubename = self.samples['all_samples'][sample_path]
        if nevents > 0:
            particle_type = 'Cells'
            match = re.findall('([Cc]ells|[Bb]eads)', tubename)
            if match:
                if 'cells' in match[0].lower():
                    particle_type = 'Cells'
                else:
                    particle_type = 'Beads'
            else:
                warnings.warn(f'Unknown particle type from name, assigning as {particle_type}')

            match = re.findall(r'^(.*?)(?=\(|cell|bead)', tubename, re.IGNORECASE)
            if match:
                label = match[0].strip()

            # discard if label is already in spectral model
            if label in [control['label'] for control in self.spectral_model]:
                pass
            else:
                full_sample_path = str(self.experiment_dir / sample_path)
                if check_fcs_matches_experiment(full_sample_path, self.controller.experiment.settings['raw']['event_channels_pnn'], self.controller.experiment.settings['raw']['magnitude_ceiling']):
                    sample = fk.Sample(full_sample_path)

                    match = re.findall('([Uu]nstained)', label)
                    if match:
                        target_plot = None
                        gate_channel = None
                        if self.controller.experiment.process['negative_type'] == 'internal': # using internal negatives, just use base gate for unstained
                            positive_gate_label = self.base_gate_label
                            negative_gate_label = self.base_gate_label
                        else: # using unstained negative, use Pos and Neg Unstained that have already been created
                            positive_gate_label = 'Pos Unstained'
                            negative_gate_label = 'Neg Unstained'

                    else:
                        # put a sample in, get a channel and brightest fluorescence values out
                        best_channel_response = get_best_channel(sample, self.raw_gating,
                                                                 self.base_gate_label,
                                                                 self.fluorescence_channel_ids)
                        if best_channel_response:
                            channel_id_best_match, fl_top, fl_bottom, explained_variance = best_channel_response

                            channel_x = self.event_channels_pnn[channel_id_best_match]
                            gate_channel = channel_x
                            pos_range_min = self.raw_gating.transformations[channel_x].apply(np.array([fl_top[0]]))[0]
                            pos_range_max = self.raw_gating.transformations[channel_x].apply(np.array([fl_top[1]]))[0]
                            pos_dim_x = fk.Dimension(channel_x, range_min=pos_range_min, range_max=pos_range_max, transformation_ref=channel_x)
                            positive_gate_label = 'Pos ' + label
                            positive_gate = fk.gates.RectangleGate(positive_gate_label, dimensions=[pos_dim_x])

                            neg_range_min = self.raw_gating.transformations[channel_x].apply(np.array([fl_bottom[0]]))[0]
                            neg_range_max = self.raw_gating.transformations[channel_x].apply(np.array([fl_bottom[1]]))[0]
                            neg_dim_x = fk.Dimension(channel_x, range_min=neg_range_min, range_max=neg_range_max, transformation_ref=channel_x)
                            negative_gate_label = 'Neg ' + label
                            negative_gate = fk.gates.RectangleGate(negative_gate_label, dimensions=[neg_dim_x])

                            # add all positive gates to the same gating strategy: they are distinguished by their label and by the sample_id that they refer to
                            # if gate already exists, remove it first
                            if self.raw_gating.find_matching_gate_paths(positive_gate_label):
                                self.raw_gating.remove_gate(positive_gate_label)
                            if self.raw_gating.find_matching_gate_paths(negative_gate_label):
                                self.raw_gating.remove_gate(negative_gate_label)
                            # Note: adding a gate below takes an increasing amount of time, even though we are not actually applying it. Why?
                            self.raw_gating.add_gate(positive_gate, gate_path=tuple(list(self.raw_gating.find_matching_gate_paths(self.base_gate_label)[0]) + [self.base_gate_label]))
                            self.raw_gating.add_gate(negative_gate, gate_path=tuple(list(self.raw_gating.find_matching_gate_paths(self.base_gate_label)[0]) + [self.base_gate_label]))
                            # gating_strategy.add_gate(positive_gate, gate_path=('root', base_gate_label), sample_id=sample_path) # needs to be done twice to be a custom sample gate
                            #### if raw_plots contains a 1D hist on channel_x, add gate to it, otherwise create it
                            target_plot = None
                            for n, plot in enumerate(self.raw_plots):
                                if plot['type'] == 'hist1d' and plot['channel_x'] == channel_x:
                                    target_plot = plot
                            if not target_plot:
                                # append plot
                                target_plot = {
                                    'type': 'hist1d',
                                    'channel_x': channel_x,
                                    'source_gate': self.base_gate_label,
                                    'child_gates': [positive_gate_label, negative_gate_label]
                                }
                                self.raw_plots.append(target_plot)
                                if self.bus:
                                    self.bus.showNewPlot.emit('raw')
                            if positive_gate_label not in target_plot['child_gates']:
                                target_plot['child_gates'].append(positive_gate_label)
                                target_plot['child_gates'].append(negative_gate_label)
                        else:
                            warnings.warn(f'Control sample has less than two events in base gate {self.base_gate_label}: cannot define spectral control')
                            if self.bus:
                                self.bus.warningMessage.emit(f'{sample_path} has less than two events in "{self.base_gate_label}" gate: cannot define spectral control.\n\n'
                                                         f'The spectral auto generator is using "{self.base_gate_label}" as a base gate '
                                                         f'within your raw data. Adjust this gate to make sure the relevant events for '
                                                         f'all your single stain control samples are within it.')
                            return False

                    if self.bus is not None:
                        self.bus.changedGatingHierarchy.emit('raw', negative_gate_label)
                        self.bus.changedGatingHierarchy.emit('raw', positive_gate_label)

                    ##### uncomment this to get more info to console. consider adding to gui
                    # report = self.raw_gating.gate_sample(sample).report.set_index('gate_name')  # Note this is slow
                    # print(f'{label}: explained variance {int(explained_variance * 100)}, best channel {self.event_channels_pnn[channel_id_best_match]}, brightest events {int(best_match)}/100, gate {report.loc[positive_gate_label]['count']}/100')

                    control = {'label': label, 'control_type': 'Single Stained Spectral Control', 'particle_type': particle_type,
                               'gate_channel': gate_channel, 'sample_name': tubename,
                               'sample_path': full_sample_path, 'gate_label': positive_gate_label}
                    self.spectral_model.append(control)

                    positive_profile = get_profile(sample, control['gate_label'], self.raw_gating, self.fluorescence_channel_ids)
                    if self.controller.experiment.process['negative_type'] == 'unstained':
                        negative_profile = self.unstained_negative
                    else:
                        negative_profile = get_profile(sample, negative_gate_label, self.raw_gating, self.fluorescence_channel_ids)
                    profile = positive_profile - negative_profile
                    if profile.sum() == 0:
                        profile = positive_profile

                    if profile.sum() > 0:
                        profile = profile / profile.max()  # max normalisation
                    else:
                        text = (f'Failed to create label: {control['label']}. '
                                f'{sample_path} has no events within the positive gate. '
                                f'Go back to the raw data and adjust your gates.')
                        warnings.warn(text)
                        if self.bus:
                            self.bus.warningMessage.emit(text)
                            return False

                    profile = profile.tolist()
                    self.profiles[control['label']] = profile

                    profile_dict = dict(zip(self.fluorescence_channels_pnn, profile))
                    spectral_library.deposit_control_with_profile_and_experiment_dir(control, profile_dict, str(self.experiment_dir))
                    return True
                else:
                    warnings.warn('Control sample file does not match experiment')
                    # self.bus.warningMessage.emit('Failed to load control sample: sample channels (names and ranges) not consistent with experiment configuration.\n\n'
                    #                              'Were your controls and samples acquired by the same instrument and settings? \n'
                    #                              'If so, run Import FCS Files (from the File menu). \n'
                    #                              'Otherwise, these controls cannot be used.')
                    if self.bus:
                        self.bus.openImportFCSWidget.emit(True)
                    return False

        else:
            warnings.warn('Invalid spectral control, no events')
            return True
