# import json
from pathlib import Path
# from unicodedata import category

import numpy as np
from PySide6.QtCore import QObject, Signal, QTimer, QSettings
# from PySide6.QtWidgets import QApplication
from flowkit import Sample

from honeychrome.controller_components.functions import apply_transfer_matrix, export_unmixed_sample
import honeychrome.settings as settings
from honeychrome.view_components.busy_cursor import with_busy_cursor

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
            pnn_unmixed = self.controller.experiment.settings['unmixed']['event_channels_pnn']

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
                print(f'UnmixedExporter: sample {n+1}/{len(samples_to_calculate)}')
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
                    unmixed_event_data_without_fine_tuning = apply_transfer_matrix(transfer_matrix, raw_event_data)
                    export_unmixed_sample(sample_name, full_unmixed_sample_path.parent, unmixed_event_data_without_fine_tuning, pnn_unmixed, spillover, subsample=self.subsample)

            print(f'UnmixedExporter: finished')

            if self.bus:
                self.bus.progress.emit(len(samples_to_calculate), len(samples_to_calculate))
                self.bus.popupMessage.emit(f'Exported {len(samples_to_calculate)} unmixed samples as FCS files. \n\n'
                                           f'Open <a href="file:///{self.controller.experiment_dir / self.controller.experiment.settings['unmixed']['unmixed_samples_subdirectory']}">'
                                           f'{self.controller.experiment.settings['unmixed']['unmixed_samples_subdirectory']}</a> folder.')
        self.finished.emit()


if __name__ == "__main__":
    from pathlib import Path
    from honeychrome.controller import Controller
    # from honeychrome.view_components.event_bus import EventBus

    kc = Controller()
    base_directory = Path.home() / 'spectral_cytometry'
    experiment_name = base_directory / '20240620 Spectral Symposium-poor cell unmixed'
    experiment_path = experiment_name.with_suffix('.kit')
    kc.load_experiment(experiment_path) # note this loads first sample too and runs calculate all histograms and statistics

    unmixed_exporter = UnmixedExporter('Raw/Samples/Spleen', True, None, kc)
    unmixed_exporter.run()

