import json
import re
import warnings

import numpy as np
from PySide6.QtCore import QObject, Signal, QTimer
# from PySide6.QtWidgets import QApplication
from flowkit import Dimension, gates

from honeychrome.controller_components.functions import timer, sample_from_fcs
from honeychrome.controller_components.spectral_functions import get_best_channel, get_profile, get_profile_from_events
from honeychrome.controller_components.label_matching import match_fluorophore, match_marker, get_fluorophore_db, get_marker_db
from honeychrome.controller_components.spectral_librarian import SpectralLibrary
from honeychrome.experiment_model import check_fcs_matches_experiment
from honeychrome.view_components.busy_cursor import with_busy_cursor


import logging
logger = logging.getLogger(__name__)

# connect to spectral library
spectral_library = SpectralLibrary()

def _find_default_unstained_tube(all_samples: dict) -> str | None:
    """Return tube name of the first sample whose path or name contains 'unstained'."""
    import re
    for path, name in all_samples.items():
        if re.search(r'unstained', path, re.IGNORECASE) or re.search(r'unstained', name, re.IGNORECASE):
            return name
    return None

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
        self.unstained_negative = None          # legacy mean-vector cache — kept for existing generate() path
        self._negative_events_cache: dict[str, np.ndarray] = {}
        self.refresh()

    def refresh(self):
        self.controller.filter_raw_fluorescence_channels()
        self.n_fluorophore_channels = len(self.controller.filtered_raw_fluorescence_channel_ids)
        self.fluorescence_channels_pnn.clear()
        self.fluorescence_channels_pnn.extend([self.event_channels_pnn[i] for i in self.controller.filtered_raw_fluorescence_channel_ids])

    def flush(self):
        self.unstained_negative = None
        self._negative_events_cache.clear()
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

    def get_unstained_negative(self):
        try:
            sample_path = None
            for path in self.samples.get('unstained_samples', []):
                if path in self.samples['all_samples']:
                    sample_path = path
                    break
            if sample_path is None:
                for path in self.samples['all_samples']:
                    if re.search(r'(unstained|negative)', path, re.IGNORECASE) or \
                    re.search(r'(unstained|negative)', self.samples['all_samples'][path], re.IGNORECASE):
                        sample_path = path
                        break
            if sample_path:
                full_sample_path = str(self.experiment_dir / sample_path)
                sample = sample_from_fcs(full_sample_path)

                positive_gate_label = 'Pos Unstained'
                negative_gate_label = 'Neg Unstained'
                # Use the persistent cytometry store, not the ephemeral runtime view —
                # data_for_cytometry_plots_raw['plots'] may be None if no sample is loaded.
                raw_plots = self.controller.experiment.cytometry['raw_plots']

                for target_gate_label in [positive_gate_label, negative_gate_label]:
                    if not self.raw_gating.find_matching_gate_paths(target_gate_label):
                        channel_x = 'FSC-A'
                        channel_y = 'SSC-A'
                        dim_x = Dimension(channel_x, range_min=0.2, range_max=0.8, transformation_ref=channel_x)
                        dim_y = Dimension(channel_y, range_min=(0.1 if target_gate_label == positive_gate_label else 0.3),
                                                    range_max=(0.7 if target_gate_label == positive_gate_label else 0.9),
                                                    transformation_ref=channel_y)
                        target_gate = gates.RectangleGate(target_gate_label, dimensions=[dim_x, dim_y])
                        base_gate_priority = self.controller.experiment.process.get('base_gate_priority_order', [])
                        raw_gate_names = [g[0].lower() for g in self.controller.raw_gating.get_gate_ids()]
                        base_gate_label = 'root'
                        for gate in base_gate_priority:
                            if gate.lower() in raw_gate_names:
                                base_gate_label = gate
                                break
                        if base_gate_label != 'root' and self.raw_gating.find_matching_gate_paths(base_gate_label):
                            base_path = tuple(list(self.raw_gating.find_matching_gate_paths(base_gate_label)[0]) + [base_gate_label])
                        else:
                            base_path = ('root',)
                        self.raw_gating.add_gate(target_gate, gate_path=base_path)

                        target_plot = None
                        for plot in raw_plots:
                            if (plot['type'] == 'hist2d'
                                    and plot['channel_x'] == channel_x
                                    and plot['channel_y'] == channel_y
                                    and plot['source_gate'] == 'root'
                                    and not set(plot['child_gates']) - {positive_gate_label, negative_gate_label}):
                                target_plot = plot
                        if not target_plot:
                            target_plot = {'type': 'hist2d', 'channel_x': channel_x, 'channel_y': channel_y,
                                        'source_gate': 'root', 'child_gates': [positive_gate_label, negative_gate_label]}
                            raw_plots.append(target_plot)
                            if self.bus:
                                self.bus.showNewPlot.emit('raw')
                        if target_gate_label not in target_plot['child_gates']:
                            target_plot['child_gates'].append(target_gate_label)

                        if self.bus:
                            self.bus.changedGatingHierarchy.emit('raw', target_gate_label)

                self.unstained_negative = get_profile(sample, negative_gate_label, self.raw_gating,
                                                    self.controller.filtered_raw_fluorescence_channel_ids)
                return True
            else:
                raise Exception(
                    'No unstained sample found. Name a control "Unstained", or right-click '
                    'any sample in the sample panel and choose "Mark as Unstained".'
                )
        except Exception as e:
            text = f'Failed to generate profile of unstained negative. {e}.'
            warnings.warn(text)
            if self.bus:
                self.bus.warningMessage.emit(text)
            return False


    def _get_negative_events(self, control) -> np.ndarray | None:
        """
        Resolve and return raw fluorescence event array for the negative of *control*.

        Priority order:
          1. control["universal_negative_name"] — per-control assignment
          2. Global unstained fallback (negative_type == "unstained")
          3. None — caller falls back to existing gate-mean path

        Results are cached by tube name so each FCS file is loaded at most once.
        """
        from honeychrome.controller_components.spectral_functions import get_raw_events
        from honeychrome.controller_components.functions import sample_from_fcs
        from honeychrome.settings import INTERNAL_NEGATIVE_SENTINEL

        tube_name = control.get('universal_negative_name') or ''

        # Explicit per-control opt-out: use the internal (same-sample) negative
        if tube_name == INTERNAL_NEGATIVE_SENTINEL:
            return None

        # Fallback to global unstained if no per-control assignment
        if not tube_name:
            if self.controller.experiment.process.get('negative_type') == 'unstained':
                tube_name = _find_default_unstained_tube(self.samples['all_samples']) or ''
            if not tube_name:
                return None

        if tube_name in self._negative_events_cache:
            return self._negative_events_cache[tube_name]

        # Resolve path from tube name
        all_samples_reverse = {v: k for k, v in self.samples['all_samples'].items()}
        rel_path = all_samples_reverse.get(tube_name)
        if rel_path is None:
            warnings.warn(f'_get_negative_events: tube "{tube_name}" not found in samples.')
            return None

        full_path = str(self.experiment_dir / rel_path)
        try:
            sample = sample_from_fcs(full_path)
            gate_label = 'Neg Unstained' if self.raw_gating.find_matching_gate_paths('Neg Unstained') else None
            events = get_raw_events(sample, self.controller.filtered_raw_fluorescence_channel_ids,
                                    gate_label=gate_label, gating_strategy=self.raw_gating)
            self._negative_events_cache[tube_name] = events
            return events
        except Exception as e:
            warnings.warn(f'_get_negative_events: failed to load "{tube_name}": {e}')
            return None
    

    def generate(self, control, search_results):
        if control['control_type'] == 'Single Stained Spectral Control':
            try:
                if control['sample_name'] and control['gate_label']:
                    all_samples_reverse_lookup = {v: k for k, v in self.samples['all_samples'].items()}
                    tubename = control['sample_name']
                    sample_path = all_samples_reverse_lookup[tubename]
                    nevents = self.samples['all_sample_nevents'][sample_path]
                    if nevents > 0:
                        full_sample_path = str(self.experiment_dir / sample_path)
                        control['sample_path'] = full_sample_path

                        positive_gate_label = control['gate_label']
                        
                        # use cleaned event pool when available and opted in
                        cleaned_store = self.controller.cleaned_events
                        cleaned = cleaned_store.get(control['label']) if control.get('use_cleaned') is not False else None
                        if cleaned is not None and len(cleaned.get('positive', [])) > 0:
                            pos_events = cleaned['positive']
                            neg_events = cleaned['negative']

                            # RLM profile extraction
                            peak_ch_name = control.get('gate_channel', '')
                            cleaned_fluor_ch_ids = cleaned.get('fluor_ch_ids') or self.controller.filtered_raw_fluorescence_channel_ids
                            try:
                                peak_ch_idx = cleaned_fluor_ch_ids.index(
                                    self.event_channels_pnn.index(peak_ch_name)
                                ) if peak_ch_name else int(np.argmax(pos_events.mean(axis=0)))
                            except (ValueError, IndexError):
                                peak_ch_idx = int(np.argmax(pos_events.mean(axis=0)))

                            profile = get_profile_from_events(pos_events, neg_events, peak_ch_idx, label=control.get('label', ''))

                            if profile.sum() == 0:
                                raise Exception(f'RLM profile for "{control["label"]}" is zero — check event pool.')
                            if not control.get('gate_channel_locked'):
                                control['gate_channel'] = self.fluorescence_channels_pnn[np.argmax(profile)]
                            profile = profile.tolist()
                            self.profiles[control['label']] = profile
                            profile_dict = dict(zip(self.fluorescence_channels_pnn, profile))
                            spectral_library.deposit_control_with_profile_and_experiment_dir(control, profile_dict, str(self.experiment_dir))
                            return True

                        # FCS load only needed for non-cleaned path
                        if not self.raw_gating.find_matching_gate_paths(positive_gate_label):
                            raise Exception(f'Positive gate label {positive_gate_label} not present in Raw Data. ')
                        sample = sample_from_fcs(full_sample_path)

                        positive_profile = get_profile(sample, positive_gate_label, self.raw_gating, self.controller.filtered_raw_fluorescence_channel_ids)

                        from honeychrome.settings import INTERNAL_NEGATIVE_SENTINEL
                        universal_neg_name = control.get('universal_negative_name') or ''
                        explicit_internal = (universal_neg_name == INTERNAL_NEGATIVE_SENTINEL)
                        use_unstained = (
                            self.controller.experiment.process['negative_type'] == 'unstained'
                            and not explicit_internal
                        )

                        if use_unstained:
                            # Resolve the specific unstained FCS for this control:
                            # (1) per-control universal_negative_name, (2) global Unstained sample.
                            # If neither is available, fall back to internal negative with a warning.
                            resolved_unstained = None

                            if universal_neg_name and not explicit_internal:
                                # Per-control assignment — load it directly.
                                # Ensure Neg Unstained gate exists first (get_unstained_negative
                                # creates it if absent; it is idempotent if already present).
                                if self.unstained_negative is None:
                                    self.get_unstained_negative()
                                all_samples_rev = {v: k for k, v in self.samples['all_samples'].items()}
                                neg_rel_path = all_samples_rev.get(universal_neg_name)
                                if neg_rel_path:
                                    neg_full_path = str(self.experiment_dir / neg_rel_path)
                                    neg_sample = sample_from_fcs(neg_full_path)
                                    neg_gate_label = 'Neg Unstained'
                                    if self.raw_gating.find_matching_gate_paths(neg_gate_label):
                                        resolved_unstained = get_profile(neg_sample, neg_gate_label, self.raw_gating, self.controller.filtered_raw_fluorescence_channel_ids)
                                    else:
                                        warnings.warn(f'{control["label"]}: unstained negative "{universal_neg_name}" has no "Neg Unstained" gate — using internal negative.')
                                else:
                                    warnings.warn(f'{control["label"]}: unstained negative "{universal_neg_name}" not found in samples — using internal negative.')
                            else:
                                # Global unstained fallback
                                if self.unstained_negative is None:
                                    self.get_unstained_negative()
                                resolved_unstained = self.unstained_negative

                            if resolved_unstained is not None:
                                negative_profile = resolved_unstained
                            else:
                                # No unstained available for this control — fall back gracefully
                                warnings.warn(f'{control["label"]}: no unstained negative available — using internal negative.')
                                if self.bus:
                                    self.bus.warningMessage.emit(f'{control["label"]}: no unstained negative available, using internal negative.')
                                use_unstained = False  # drop through to internal path below

                        if not use_unstained:
                            if 'unstained' in control['label'].lower():
                                negative_gate_label = positive_gate_label
                            else:
                                # Prefer an explicitly set neg_gate_label; fall back to
                                # the auto-constructed name for backwards compatibility
                                # with experiments generated before this field existed.
                                negative_gate_label = (
                                    control.get('neg_gate_label')
                                    or f'Neg {control["label"]}'
                                )

                            if not self.raw_gating.find_matching_gate_paths(negative_gate_label):
                                raise Exception(f'Internal negative gate "{negative_gate_label}" not present in Raw Data. '
                                                f'Please run Auto-Generate to recreate spectral gates, '
                                                f'or select the correct Negative Gate in the Spectral Model Editor.')

                            negative_profile = get_profile(sample, negative_gate_label, self.raw_gating, self.controller.filtered_raw_fluorescence_channel_ids)

                        profile = positive_profile - negative_profile
                        if profile.sum() == 0:
                            profile = positive_profile

                        if profile.sum() > 0:
                            profile = profile / profile.max()  # max normalisation
                        else:
                            if profile.sum() == 0:
                                raise Exception(f'Failed to create label: {control['label']}. '
                                    f'{sample_path} has no events within the positive gate. '
                                    f'Go back to the raw data and adjust your gates. ')
                            else:
                                raise Exception(f'Profile {control['label']} is negative: this will yield nonsense results. '
                                    f'Make sure the unstained negative has lower fluorescence than the positive. '
                                    f'Go back to the raw data and adjust your gates (or use internal negatives).')

                        if not control.get('gate_channel_locked'):
                            control['gate_channel'] = self.fluorescence_channels_pnn[np.argmax(profile)]
                        profile = profile.tolist()
                        self.profiles[control['label']] = profile
                        profile_dict = dict(zip(self.fluorescence_channels_pnn, profile))
                        spectral_library.deposit_control_with_profile_and_experiment_dir(control, profile_dict, str(self.experiment_dir))
                        return True

            except Exception as e:
                text = f'Failed to generate profile. {e}'
                warnings.warn(text)
                if self.bus:
                    self.bus.warningMessage.emit(text)
                return False

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
            success = self.generate_spectral_control(n)
            if not success:
                if self.bus:
                    QTimer.singleShot(100, lambda: self.bus.statusMessage.emit(f'Failed to generate profile of spectral control {n}.'))
                continue
            if self.bus:
                self.bus.spectralControlAdded.emit()

        # update all raw plots at end to avoid timing issues in main loop
        for index, plot in enumerate(self.raw_plots):
            if self.bus:
                self.bus.updateRois.emit('raw', index)

        logger.info('SpectralAutoGenerator: regenerated spectral model and raw gating hierarchy:')
        logger.info(self.raw_gating.get_gate_hierarchy(output='json'))

        if self.bus:
            # self.bus.changedGatingHierarchy.emit('raw', 'root')
            self.bus.progress.emit(self.progress_target, self.progress_target)
            self.bus.spectralModelUpdated.emit()
            self.bus.showSelectedProfiles.emit([]) # refresh everything

    def get_unstained_negative(self):
        try:
            sample_path = None
            # 1. Check manually designated unstained samples first
            for path in self.samples.get('unstained_samples', []):
                if path in self.samples['all_samples']:
                    sample_path = path
                    break
            # 2. Fall back to filename/tubename regex
            if sample_path is None:
                for path in self.samples['all_samples']:
                    if re.search(r'(unstained|negative)', path, re.IGNORECASE) or \
                       re.search(r'(unstained|negative)', self.samples['all_samples'][path], re.IGNORECASE):
                        sample_path = path
                        break
            if sample_path:
                full_sample_path = str(self.experiment_dir / sample_path)
                sample = sample_from_fcs(full_sample_path)

                # Only Neg Unstained is needed
                negative_gate_label = 'Neg Unstained'

                # Resolve gate path: place under base gate (e.g. Singlets), not at root
                if self.base_gate_label != 'root' and self.raw_gating.find_matching_gate_paths(self.base_gate_label):
                    base_path = tuple(list(self.raw_gating.find_matching_gate_paths(self.base_gate_label)[0]) + [self.base_gate_label])
                else:
                    base_path = ('root',)

                # Only create the gate if it does not already exist — avoids duplicate-gate
                # errors if one gate exists but the other does not (Issue 5).
                if not self.raw_gating.find_matching_gate_paths(negative_gate_label):
                    # Use the first fluorescence channel as a broad 1D gate
                    # covering all events — the gate exists only to anchor the profile extraction
                    # in the gating hierarchy; its range covers the full transformed space.
                    channel_x = self.fluorescence_channels_pnn[0]
                    dim_x = Dimension(channel_x, range_min=0.0, range_max=1.0, transformation_ref=channel_x)
                    neg_gate = gates.RectangleGate(negative_gate_label, dimensions=[dim_x])
                    self.raw_gating.add_gate(neg_gate, gate_path=base_path)
                    if self.bus:
                        self.bus.changedGatingHierarchy.emit('raw', negative_gate_label)  # Issue 3

                    # Add or update the plot for this gate
                    # Look for an existing 1D hist on channel_x sourced from base gate.
                    target_plot = None
                    for plot in self.raw_plots:
                        if (plot['type'] == 'hist1d'
                                and plot['channel_x'] == channel_x
                                and plot['source_gate'] == self.base_gate_label
                                and not set(plot['child_gates']) - {negative_gate_label}):
                            target_plot = plot
                    if not target_plot:
                        target_plot = {'type': 'hist1d', 'channel_x': channel_x,
                                       'source_gate': self.base_gate_label, 'child_gates': []}
                        self.raw_plots.append(target_plot)
                        if self.bus:
                            self.bus.showNewPlot.emit('raw')
                    if negative_gate_label not in target_plot['child_gates']:
                        target_plot['child_gates'].append(negative_gate_label)

                # All events within the base gate of the unstained sample form the negative reference.
                self.unstained_negative = get_profile(sample, self.base_gate_label, self.raw_gating,
                                                      self.fluorescence_channel_ids)
                return True
            else:
                raise Exception(
                    'No unstained sample found. Name a control "Unstained", or right-click '
                    'any sample in the sample panel and choose "Mark as Unstained".'
                )
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
            # Skip samples whose name or path contains "Unstained" or "Negative",
            # or that have been manually marked as unstained by the user.
            # Users can still add them manually via the +Add Control button.
            manually_unstained = set(self.samples.get('unstained_samples', []))
            if re.search(r'(unstained|negative)', tubename, re.IGNORECASE) or \
               re.search(r'(unstained|negative)', sample_path, re.IGNORECASE) or \
               sample_path in manually_unstained:
                logger.info(f'generate_spectral_control: skipping "{tubename}" (matches unstained/negative pattern or manually marked as unstained)')
                return True

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
            raw_label = match[0].strip() if match else tubename

            # Strip leading plate-position prefixes like "A1 ", "B12 " before label matching
            raw_label = re.sub(r'^[A-H]\d{1,2}\s+', '', raw_label).strip()

            canonical_fluor = match_fluorophore(raw_label, get_fluorophore_db())
            label = canonical_fluor if canonical_fluor else raw_label

            canonical_marker = match_marker(raw_label, get_marker_db())
            antigen = canonical_marker or ''

            # discard if label is already in spectral model
            if label in [control['label'] for control in self.spectral_model]:
                pass
            else:
                full_sample_path = str(self.experiment_dir / sample_path)
                if check_fcs_matches_experiment(full_sample_path, self.controller.experiment.settings['raw']['event_channels_pnn'], self.controller.experiment.settings['raw']['magnitude_ceiling']):
                    sample = sample_from_fcs(full_sample_path)

                    match = re.findall('([Uu]nstained)', label)
                    if match:
                        target_plot = None
                        gate_channel = None
                        if self.controller.experiment.process['negative_type'] == 'internal': # using internal negatives, just use base gate for unstained
                            positive_gate_label = self.base_gate_label
                            negative_gate_label = self.base_gate_label
                        else: # using unstained negative: all events in base gate are the positive,
                              # Neg Unstained (created by get_unstained_negative) is the reference
                            positive_gate_label = self.base_gate_label
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
                            pos_dim_x = Dimension(channel_x, range_min=pos_range_min, range_max=pos_range_max, transformation_ref=channel_x)
                            positive_gate_label = 'Pos ' + label
                            positive_gate = gates.RectangleGate(positive_gate_label, dimensions=[pos_dim_x])

                            neg_range_min = self.raw_gating.transformations[channel_x].apply(np.array([fl_bottom[0]]))[0]
                            neg_range_max = self.raw_gating.transformations[channel_x].apply(np.array([fl_bottom[1]]))[0]
                            neg_dim_x = Dimension(channel_x, range_min=neg_range_min, range_max=neg_range_max, transformation_ref=channel_x)
                            negative_gate_label = 'Neg ' + label
                            negative_gate = gates.RectangleGate(negative_gate_label, dimensions=[neg_dim_x])

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

                    default_unstained = _find_default_unstained_tube(self.samples['all_samples'])
                    assigned_negative = default_unstained or ''  # default; overridden for Beads below
                    # For bead controls, only use an unstained negative if available
                    if particle_type == 'Beads':
                        # Mirror the combobox builder logic exactly: iterate all_samples,
                        # accept anything unstained (manually tagged OR regex), then
                        # filter to those whose name contains "Beads".
                        manually_tagged = set(self.samples.get('unstained_samples', []))
                        default_unstained_bead = None
                        for path, name in self.samples['all_samples'].items():
                            is_unstained = (
                                path in manually_tagged
                                or bool(re.search(r'unstained', name, re.IGNORECASE))
                                or bool(re.search(r'unstained', path, re.IGNORECASE))
                            )
                            if not is_unstained:
                                continue
                            if re.search(r'bead', name, re.IGNORECASE) or re.search(r'bead', path, re.IGNORECASE):
                                default_unstained_bead = name
                                break
                        assigned_negative = default_unstained_bead or ''
                    control = {
                        'label': label,
                        'antigen': antigen,
                        'control_type': 'Single Stained Spectral Control', 
                        'particle_type': particle_type,
                        'gate_channel': gate_channel, 
                        'sample_name': tubename,
                        'sample_path': full_sample_path, 
                        'gate_label': positive_gate_label,
                        'neg_gate_label': negative_gate_label,
                        'universal_negative_name': assigned_negative,
                    }

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
                        if profile.sum() == 0:
                            text = (f'Failed to create label: {control['label']}. '
                                    f'{sample_path} has no events within the positive gate. '
                                    f'Go back to the raw data and adjust your gates.')
                        else:
                            text = (f'Profile {control['label']} is negative: this will yield nonsense results. '
                                    f'Make sure the unstained negative has lower fluorescence than tha positive. '
                                    f'Go back to the raw data and adjust your gates (or use internal negatives).')
                        warnings.warn(text)
                        if self.bus:
                            self.bus.warningMessage.emit(text)
                        return False

                    # add control and profile if there wasn't a warning / exception above
                    self.spectral_model.append(control)

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



# ---------------------------------------------------------------------------
# SpectralCleaner
# Runs saturation exclusion + brightest-event selection for all cell controls
# that have a universal_negative_name.  Stores CleanResult in
# controller.cleaned_events[label].
# ---------------------------------------------------------------------------

TARGET_N  = 50   # minimum events needed for a reliable profile
INITIAL_N = 250   # starting cushion


class SpectralCleaner(QObject):
    """
    Runs the AutoSpectral cleaning pipeline (saturation exclusion +
    brightest-event selection) for every eligible cell control.

    Instantiate, optionally move to a QThread, then call run().
    The caller is responsible for emitting bus.spectralModelUpdated after run()
    completes (e.g. via a QThread.finished signal).
    """
    cleaningFinished = Signal()

    def __init__(self, bus, controller):
        super().__init__()
        self.bus = bus
        self.controller = controller
        self.experiment_dir  = controller.experiment_dir
        self.samples         = controller.experiment.samples
        self.spectral_model  = controller.experiment.process['spectral_model']
        self.cleaned_events  = controller.cleaned_events
        self.raw_gating      = controller.raw_gating
        self.event_channels_pnn = controller.experiment.settings['raw']['event_channels_pnn']
        controller.filter_raw_fluorescence_channels()
        self.fluor_ch_ids    = controller.filtered_raw_fluorescence_channel_ids
        self.ceiling         = controller.experiment.settings['raw']['magnitude_ceiling']

        # Build a ProfileUpdater instance solely to reuse _get_negative_events()
        self._profile_updater = ProfileUpdater(controller, bus)

    @with_busy_cursor
    def run(self):
        from honeychrome.settings import INTERNAL_NEGATIVE_SENTINEL

        eligible_external = [
            c for c in self.spectral_model
            if c.get('control_type') == 'Single Stained Spectral Control'
            and c.get('particle_type') == 'Cells'
            and c.get('universal_negative_name')
            and c.get('universal_negative_name') != INTERNAL_NEGATIVE_SENTINEL
        ]

        eligible_internal = [
            c for c in self.spectral_model
            if c.get('control_type') == 'Single Stained Spectral Control'
            and (
                c.get('particle_type') == 'Beads'
                or c.get('universal_negative_name') == INTERNAL_NEGATIVE_SENTINEL
            )
        ]

        all_eligible = eligible_external + eligible_internal
        total = len(all_eligible)

        for n, control in enumerate(eligible_external):
            if self.bus:
                self.bus.progress.emit(n, total)
            if not self._is_cleaning_current(control):
                self._clean_one(control)
            else:
                logger.info(f'SpectralCleaner: skipping "{control["label"]}" — result already current.')

        for n, control in enumerate(eligible_internal):
            if self.bus:
                self.bus.progress.emit(len(eligible_external) + n, total)
            if not self._is_cleaning_current(control):
                self._clean_one(control)
            else:
                logger.info(f'SpectralCleaner: skipping "{control["label"]}" — result already current.')

        if self.bus:
            self.bus.progress.emit(total, total)

        logger.info(f'SpectralCleaner: cleaned {len(eligible_external)} cell controls '
                    f'and {len(eligible_internal)} internal/bead controls.')
        self.cleaningFinished.emit()

    def _cleaning_fingerprint(self, control: dict) -> dict:
        """Return a dict of all inputs that determine what _clean_one will produce.
        If this matches what is stored in cleaned_events, the result is still current."""
        return {
            'sample_name': control.get('sample_name'),
            'gate_label': control.get('gate_label'),
            'universal_negative_name': control.get('universal_negative_name'),
            'af_remove': bool(control.get('af_remove', False)),
            'particle_type': control.get('particle_type'),
            'fluor_ch_ids': list(self.fluor_ch_ids),
        }

    def _is_cleaning_current(self, control: dict) -> bool:
        """Return True if a valid cleaned result already exists for this control
        and its fingerprint matches the current control configuration."""
        label = control.get('label') or ''
        existing = self.cleaned_events.get(label)
        if not existing:
            return False
        stored_fp = existing.get('_fingerprint')
        if stored_fp is None:
            return False
        return stored_fp == self._cleaning_fingerprint(control)
    
    def _clean_one(self, control: dict):
        from honeychrome.controller_components.spectral_functions import get_raw_events
        from honeychrome.controller_components.spectral_cleaning import (
            clean_control, select_positive_events
        )
        from honeychrome.controller_components.functions import sample_from_fcs

        label = control['label']
        try:
            # --- load positive fluorescence + scatter events ---
            all_samples_rev = {v: k for k, v in self.samples['all_samples'].items()}
            rel_path = all_samples_rev.get(control['sample_name'])
            if rel_path is None:
                raise ValueError(f'Sample "{control["sample_name"]}" not found.')
            full_path = str(self.experiment_dir / rel_path)
            sample = sample_from_fcs(full_path)

            positive_gate_label = control.get('gate_label')
            scatter_ch_ids = self.controller.experiment.settings['raw']['scatter_channel_ids']
            scatter_ch_pnn = self.controller.experiment.settings['raw']['event_channels_pnn']

            pos_events, pos_scatter_all = get_raw_events(
                sample, self.fluor_ch_ids,
                gate_label=positive_gate_label,
                gating_strategy=self.raw_gating,
                extra_channel_ids=scatter_ch_ids,
            )

            # Reduce scatter to FSC-A and SSC-A columns only (scatter_match_negative
            # expects shape (n, 2); scatter_ch_ids may include -H and -W variants).
            def _fsc_ssc_cols(all_scatter: np.ndarray) -> np.ndarray:
                fsc_a = next((col for col, ch_id in enumerate(scatter_ch_ids)
                            if scatter_ch_pnn[ch_id] == 'FSC-A'), None)
                ssc_a = next((col for col, ch_id in enumerate(scatter_ch_ids)
                            if scatter_ch_pnn[ch_id] == 'SSC-A'), None)
                if fsc_a is None:
                    fsc_a = next((col for col, ch_id in enumerate(scatter_ch_ids)
                                if 'FSC' in scatter_ch_pnn[ch_id]), 0)
                if ssc_a is None:
                    ssc_a = next((col for col, ch_id in enumerate(scatter_ch_ids)
                                if 'SSC' in scatter_ch_pnn[ch_id]), 1)
                return all_scatter[:, [fsc_a, ssc_a]]
            
            pos_scatter = _fsc_ssc_cols(pos_scatter_all) if pos_scatter_all.shape[1] > 2 else pos_scatter_all

            # --- load negative events ---
            # Beads and [Internal Negative] controls: use the bottom of the positive
            # sample's own peak-channel distribution as the negative.
            # No external file, no scatter matching (empty scatter arrays cause
            # scatter_match_negative to be skipped inside clean_control).
            from honeychrome.settings import INTERNAL_NEGATIVE_SENTINEL
            use_internal = (
                control.get('particle_type') == 'Beads'
                or control.get('universal_negative_name') == INTERNAL_NEGATIVE_SENTINEL
            )

            logger.info(
                f'_clean_one: "{label}" particle_type={control.get("particle_type")!r} '
                f'universal_negative_name={control.get("universal_negative_name")!r} '
                f'use_internal={use_internal}'
            )

            if use_internal:
                # Load the negative gate from the same positive sample file.
                neg_gate_lbl = f'Neg {label}'
                try:
                    if (self.raw_gating and
                            self.raw_gating.find_matching_gate_paths(neg_gate_lbl)):
                        neg_events_internal, _ = get_raw_events(
                            sample, self.fluor_ch_ids,
                            gate_label=neg_gate_lbl,
                            gating_strategy=self.raw_gating,
                        )
                    else:
                        neg_events_internal = np.empty((0, pos_events.shape[1]))
                except Exception:
                    neg_events_internal = np.empty((0, pos_events.shape[1]))
                neg_events = neg_events_internal   # used by select_positive_events
                neg_scatter = np.empty((0, 2))     # no scatter matching for internal
            else:
                neg_events_internal = None
                tube_name = control.get('universal_negative_name') or ''
                if not tube_name:
                    logger.warning(f'SpectralCleaner: no negative assigned for "{label}" — skipping.')
                    return
                all_samples_rev2 = {v: k for k, v in self.samples['all_samples'].items()}
                neg_rel_path = all_samples_rev2.get(tube_name)
                if not neg_rel_path:
                    logger.warning(f'SpectralCleaner: negative tube "{tube_name}" not found — skipping.')
                    return
                neg_full_path = str(self.experiment_dir / neg_rel_path)
                neg_sample = sample_from_fcs(neg_full_path)
                neg_events, neg_scatter_all = get_raw_events(
                    neg_sample, self.fluor_ch_ids,
                    gate_label=None,
                    gating_strategy=self.raw_gating,
                    extra_channel_ids=scatter_ch_ids,
                )
                if len(neg_events) == 0:
                    logger.warning(f'SpectralCleaner: no negative events for "{label}" — skipping.')
                    return
                neg_scatter = _fsc_ssc_cols(neg_scatter_all) if neg_scatter_all.shape[1] > 2 else neg_scatter_all

            # --- determine peak channel index ---
            peak_ch_name = control.get('gate_channel', '')
            try:
                peak_ch_idx = self.fluor_ch_ids.index(
                    self.event_channels_pnn.index(peak_ch_name)
                )
            except (ValueError, IndexError):
                peak_ch_idx = int(np.argmax(pos_events.mean(axis=0)))

            # --- adaptive top-up loop ---
            quantile  = 0.995
            initial_n = INITIAL_N

            for attempt in range(10):
                pos_sel, sel_idx, threshold = select_positive_events(
                    pos_events, neg_events, peak_ch_idx,
                    initial_n=initial_n,
                    positivity_quantile=quantile,
                )
                # Keep pos_scatter aligned with the selected positive rows
                pos_scatter_sel = pos_scatter[sel_idx] if len(pos_scatter) == len(pos_events) else np.empty((0, 2))

                af_remove = bool(control.get('af_remove', False))
                result = clean_control(
                    pos_sel,
                    neg_events,
                    peak_ch_idx,
                    ceiling=self.ceiling,
                    positivity_quantile=quantile,
                    scatter_pos=pos_scatter_sel,
                    scatter_neg=neg_scatter,
                    opts={'af_remove': af_remove},
                )

                if len(result.positive) >= TARGET_N or quantile <= 0.95:
                    break

                # Too few survived — widen threshold and take more forward
                quantile  = max(0.95, quantile - 0.01)
                initial_n = min(500, int(initial_n * 1.5))

            if len(result.positive) < TARGET_N:
                    msg = (f'SpectralCleaner: only {len(result.positive)} events '
                        f'available for "{label}" after cleaning; '
                        f'profile may be unreliable.')
                    logger.warning(msg)
                    if self.bus:
                        self.bus.warningMessage.emit(msg)

            # For internal-negative controls, clear scatter arrays so the viewer
            # does not display them as if scatter matching against an external
            # negative had occurred.
            if use_internal:
                result.scatter_pos = np.empty((0, 2))
                result.scatter_neg = np.empty((0, 2))
                result.hull_vertices = None
                result.n_scatter_matched = 0    

            # --- store result (runtime only — not serialised) ---
            self.cleaned_events[label] = {
                'positive': result.positive,
                'negative': result.negative,
                'fluor_ch_ids': list(self.fluor_ch_ids),
                'scatter_pos': result.scatter_pos,
                'scatter_neg': result.scatter_neg,
                'hull_vertices': result.hull_vertices,
                'n_removed_saturation': result.n_removed_saturation,
                'n_removed_af': result.n_removed_af,
                'n_scatter_matched': result.n_scatter_matched,
                'n_surviving_positive': result.n_surviving_positive,
                'positivity_quantile_used': result.positivity_quantile_used,
                'af_boundary_neg': result.af_boundary_neg,
                'af_boundary_pos': result.af_boundary_pos,
                'af_ch_idx': result.af_ch_idx,
                'af_peak_ch_idx': result.af_peak_ch_idx,
                'warnings': result.warnings,
                '_fingerprint': self._cleaning_fingerprint(control),
            }

            logger.info(
                f'SpectralCleaner: "{label}" — '
                f'{result.n_surviving_positive} positive events selected, '
                f'{result.n_removed_saturation} removed for saturation, '
                f'{result.n_scatter_matched} scatter-matched negatives, '
                f'quantile={result.positivity_quantile_used:.3f}.'
            )

        except Exception as e:
            msg = f'SpectralCleaner: failed to clean "{label}": {e}'
            logger.error(msg)
            if self.bus:
                self.bus.warningMessage.emit(msg)