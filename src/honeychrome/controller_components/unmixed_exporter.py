# import json
from pathlib import Path
# from unicodedata import category

import numpy as np
from PySide6.QtCore import QObject, Signal, QTimer, QSettings
# from PySide6.QtWidgets import QApplication
from flowkit import Sample

from honeychrome.controller_components.functions import apply_transfer_matrix, export_unmixed_sample
from honeychrome.controller_components.autospectral_functions import precompute_af_matrices, combine_af_precomputed, apply_af_transfer
import honeychrome.settings as settings
from honeychrome.view_components.busy_cursor import with_busy_cursor

import logging
logger = logging.getLogger(__name__)

class UnmixedExporter(QObject):
    finished = Signal()

    def __init__(self, folder, subsample_bool, bus, controller):
        super().__init__()

        # connect
        self.folder = folder
        if subsample_bool:
            self.subsample = settings.subsample_retrieved
        else:
            self.subsample = None

        self.controller = controller
        self.bus = bus

    @with_busy_cursor
    def run(self):
        all_samples = self.controller.experiment.samples['all_samples']
        samples_to_calculate = [sample for sample in all_samples if sample.startswith(self.folder)]

        if self.controller.experiment.process['unmixing_matrix'] is not None:
            unmixing_matrix = np.array(self.controller.experiment.process['unmixing_matrix'])
            spillover = np.array(self.controller.experiment.process['spillover'])
            pnn_raw = self.controller.experiment.settings['raw']['event_channels_pnn']
            pnn_unmixed = self.controller.experiment.settings['unmixed']['event_channels_pnn'] # ssr review: consider setting this to antigen fluorophore self.controller.data_for_cytometry_plots['pnn_unmixed']?

            fl_channel_ids_raw = np.array(self.controller.filtered_raw_fluorescence_channel_ids)
            sc_channel_ids_raw = np.array(self.controller.experiment.settings['raw']['scatter_channel_ids'])
            fl_channel_ids_unmixed = np.array(self.controller.experiment.settings['unmixed']['fluorescence_channel_ids'])
            sc_channel_ids_unmixed = np.array(self.controller.experiment.settings['unmixed']['scatter_channel_ids'])
            n_scatter_channels = self.controller.experiment.settings['unmixed']['n_scatter_channels']

            transfer_matrix = np.zeros((len(pnn_unmixed), len(pnn_raw)))
            transfer_matrix[np.ix_(fl_channel_ids_unmixed, fl_channel_ids_raw)] = unmixing_matrix
            transfer_matrix[np.ix_(sc_channel_ids_unmixed, sc_channel_ids_raw)] = np.eye(n_scatter_channels)
            transfer_matrix[self.controller.experiment.settings['unmixed']['time_channel_id'], self.controller.experiment.settings['raw']['time_channel_id']] = 1

            if self.controller.experiment.settings['raw']['event_id_channel_id'] is not None:
                transfer_matrix[self.controller.experiment.settings['unmixed']['event_id_channel_id'], self.controller.experiment.settings['raw']['event_id_channel_id']] = 1
            # note transfer_matrix is transposed - multiply raw event data @ transfer_matrix to get unmixed event data in same form as raw
            transfer_matrix = transfer_matrix.T


            for n, sample_path in enumerate(samples_to_calculate):
                logger.info(f'UnmixedExporter: sample {n+1}/{len(samples_to_calculate)}')
                if self.bus:
                    self.bus.progress.emit(n, len(samples_to_calculate))

                sample_name = all_samples[sample_path]
                unmixed_rel_path = (Path(self.controller.experiment.settings['unmixed']['unmixed_samples_subdirectory']) /
                                    Path(sample_path).relative_to(self.controller.experiment.settings['raw']['raw_samples_subdirectory']))

                full_sample_path = self.controller.experiment_dir / sample_path
                full_unmixed_sample_path = self.controller.experiment_dir / unmixed_rel_path
                full_unmixed_sample_path.parent.mkdir(parents=True, exist_ok=True)
                sample = Sample(full_sample_path)
                raw_event_data = sample.get_events(source='raw')
                n_events = sample.event_count

                if n_events > 0:
                    # Check whether this sample has AutoSpectral AF profiles assigned
                    sample_af_profiles = self.controller.experiment.samples.get('sample_af_profiles', {})
                    assigned_profile_names = sample_af_profiles.get(sample_path, [])
                    all_af_profiles = self.controller.experiment.process.get('af_profiles', {})
                    active_profiles = [all_af_profiles[name] for name in assigned_profile_names if name in all_af_profiles]

                    if active_profiles:
                        # Build combined AF precomputed matrices for this sample's assigned profiles
                        fluor_spectra = self.controller._build_fluor_spectra()
                        precomputed_list = [
                            precompute_af_matrices(
                                fluor_spectra,
                                np.array(p['spectra'])
                            )
                            for p in active_profiles
                        ]
                        af_precomputed = combine_af_precomputed(precomputed_list)
                        # Stack all AF spectra row-wise across assigned profiles
                        af_spectra = np.vstack([np.array(p['spectra']) for p in active_profiles])

                        af_result = apply_af_transfer(
                            raw_event_data,
                            transfer_matrix,
                            af_precomputed,
                            af_spectra,
                            self.controller.experiment.settings,
                            filtered_fl_ids_raw=self.controller.filtered_raw_fluorescence_channel_ids,
                            spillover=None, # managed by flowkit at read-time
                        )
                        unmixed_event_data_without_fine_tuning = af_result['unmixed']
                        af_cols = np.column_stack([
                            af_result['af_scale'],
                            af_result['af_idx'].astype(np.float64),
                        ])
                        export_event_data = np.hstack([unmixed_event_data_without_fine_tuning, af_cols])
                        export_pnn = pnn_unmixed + ['AF Abundance', 'AF Index']
                        logger.info(f'UnmixedExporter: using AF unmixing for {sample_path} ({len(active_profiles)} profile(s))')
                    else:
                        export_event_data = apply_transfer_matrix(transfer_matrix, raw_event_data)
                        export_pnn = pnn_unmixed

                    extra_null = ['AF Abundance', 'AF Index'] if active_profiles else None
                    export_unmixed_sample(sample_name, full_unmixed_sample_path.parent, export_event_data, export_pnn, spillover, subsample=self.subsample, extra_null_channels=extra_null)

            logger.info(f'UnmixedExporter: finished')

            if self.bus:
                self.bus.progress.emit(len(samples_to_calculate), len(samples_to_calculate))
                # self.bus.popupMessage.emit(f'Exported {len(samples_to_calculate)} unmixed samples as FCS files. \n\n'
                #                            f'Open <a href="file:///{self.controller.experiment_dir / self.controller.experiment.settings['unmixed']['unmixed_samples_subdirectory']}">'
                #                            f'{self.controller.experiment.settings['unmixed']['unmixed_samples_subdirectory']}</a> folder.')
                self.bus.popupMessage.emit(f'Exported {len(samples_to_calculate)} unmixed samples as FCS files, to \n'
                                           f'"{self.controller.experiment.settings['unmixed']['unmixed_samples_subdirectory']}" folder in experiment folder')
        self.finished.emit()


if __name__ == "__main__":
    from pathlib import Path
    from honeychrome.controller import Controller
    # from honeychrome.view_components.event_bus import EventBus

    kc = Controller()
    base_directory = Path.home() / 'spectral_cytometry'
    # is this a test set-up?
    experiment_name = base_directory / '20240620 Spectral Symposium-poor cell unmixed'
    experiment_path = experiment_name.with_suffix('.kit')
    kc.load_experiment(experiment_path) # note this loads first sample too and runs calculate all histograms and statistics

    unmixed_exporter = UnmixedExporter('Raw/Samples/Spleen', True, None, kc)
    unmixed_exporter.run()

