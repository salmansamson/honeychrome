import json
import warnings
from pathlib import Path
# from unicodedata import category

import numpy as np
from PySide6.QtCore import QObject, Signal, QTimer

from honeychrome.controller_components.functions import timer, apply_gates_in_place, apply_transfer_matrix, calc_stats, sample_from_fcs
from honeychrome.view_components.busy_cursor import with_busy_cursor


class StatisticsCalculator(QObject):
    finished = Signal()

    def __init__(self, bus, controller):
        super().__init__()

        # connect
        self.controller = controller
        self.bus = bus

    @with_busy_cursor
    def run(self):
        all_samples = self.controller.experiment.samples['all_samples']
        experiment_statistics = self.controller.experiment.statistics
        sample_sets = [statistics_comparison['sample_set'] for statistics_comparison in experiment_statistics]
        samples_to_calculate = [sample for sample in all_samples if any([sample.startswith(folder.rstrip('/') + '/') for folder in sample_sets])]
        samples_by_set = {sample_set:[sample for sample in samples_to_calculate if sample.startswith(sample_set)] for sample_set in sample_sets}

        if self.controller.experiment.process['unmixing_matrix'] is not None:
            data_for_statistics_comparison = self.controller.data_for_cytometry_plots_unmixed.copy()
            # set up data first by sample
            data_by_sample = {}
            for n in range(len(samples_to_calculate)):
                print(f'StatisticsCalculator: sample {n+1}/{len(samples_to_calculate)}')
                if self.bus:
                    self.bus.progress.emit(n, len(samples_to_calculate))

                sample_name = all_samples[samples_to_calculate[n]]
                path_components = str(Path(samples_to_calculate[n])).split('/')
                depth = len(path_components)

                if depth > 2:
                    group_name = path_components[-2]
                else:
                    group_name = None

                if depth > 3:
                    category_name = '/'.join(path_components[1:-2])
                else:
                    category_name = None

                full_sample_path = str(self.controller.experiment_dir / samples_to_calculate[n])
                sample = sample_from_fcs(full_sample_path)
                raw_event_data = sample.get_events(source='raw')
                n_events = sample.event_count

                if n_events > 0:
                    data_by_sample[samples_to_calculate[n]] = {'Sample':sample_name, 'Group':group_name, 'Category':category_name, 'Statistics':{}}

                    unmixed_event_data = apply_transfer_matrix(self.controller.transfer_matrix, raw_event_data)
                    data_for_statistics_comparison.update({'event_data': unmixed_event_data})

                    gate_membership = {'root': np.ones(len(data_for_statistics_comparison['event_data']), dtype=np.bool_)}
                    data_for_statistics_comparison.update({'gate_membership': gate_membership})
                    gates_to_calculate = [g[0] for g in data_for_statistics_comparison['gating'].get_gate_ids()]
                    # gates_to_calculate = list(set([statistics_comparison['gate'] for statistics_comparison in experiment_statistics]))
                    apply_gates_in_place(data_for_statistics_comparison, gates_to_calculate=gates_to_calculate)
                    sample_statistics = calc_stats(data_for_statistics_comparison)
                    for statistics_comparison in experiment_statistics:
                        gate_name = statistics_comparison['gate']
                        statistic = statistics_comparison['statistic']
                        if gate_name in sample_statistics:
                            if statistic == "% Total Events":
                                value = sample_statistics[gate_name]['p_gate_total'] * 100
                            elif statistic == "% Parent":
                                value = sample_statistics[gate_name]['p_gate_parent'] * 100
                            elif statistic == "Event Concentration":
                                value = sample_statistics[gate_name]['n_events_gate'] / 60
                            elif statistic == "Number of Events":
                                value = sample_statistics[gate_name]['n_events_gate']
                            else: #if statistic == "Mean Intensity...":
                                channel_index = data_for_statistics_comparison['pnn'].index(statistics_comparison['channel'])
                                gate_membership = data_for_statistics_comparison['gate_membership'][gate_name]
                                value = data_for_statistics_comparison['event_data'][gate_membership,channel_index].mean()

                            data_by_sample[samples_to_calculate[n]]['Statistics'][(gate_name, statistic)] = value

                        else:
                            text = (f'Cannot calculate statistics: gate "{gate_name}" no longer exists.  '
                                    f'Please either create the gate again or delete any statistics plots below that reference {gate_name}.')
                            warnings.warn(text)
                            if self.bus:
                                self.bus.warningMessage.emit(text)
                                self.bus.progress.emit(0,0)
                                self.bus.statusMessage.emit(text)
                            self.finished.emit()
                            return

            # assemble the data into experiment statistics data table
            for m, statistics_comparison in enumerate(experiment_statistics):
                data_list = []
                for sample in samples_by_set[sample_sets[m]]:
                    data_list.append({
                        'Sample': data_by_sample[sample]['Sample'],
                        'Group': data_by_sample[sample]['Group'],
                        'Category': data_by_sample[sample]['Category'],
                        statistics_comparison['statistic']: data_by_sample[sample]['Statistics'][(statistics_comparison['gate'],statistics_comparison['statistic'])]
                    })

                data_dict_of_lists = {}
                for d in data_list:
                    for key, value in d.items():
                        data_dict_of_lists.setdefault(key, []).append(value)

                statistics_comparison['data'] = data_dict_of_lists

                depth = 3
                if None in statistics_comparison['data']['Category'] or len(set(statistics_comparison['data']['Category']))==1:
                    statistics_comparison['data'].pop('Category')
                    depth = 2
                if None in statistics_comparison['data']['Group'] or len(set(statistics_comparison['data']['Group']))==1:
                    statistics_comparison['data'].pop('Group')
                    depth = 1
                statistics_comparison['depth'] = depth

            print(f'StatisticsCalculator: calculated statistics {json.dumps(experiment_statistics, indent=2)}')

            if self.bus:
                self.bus.progress.emit(len(samples_to_calculate), len(samples_to_calculate))

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
    kc.set_mode('Unmixed Data')
    kc.initialise_data_for_cytometry_plots()
    kc.set_mode('Statistics')

    kc.experiment.statistics = [{'sample_set': 'Raw/Samples', 'plot_type': 'Box and Whisker Chart', 'gate': 'Singlets', 'statistic': 'Mean Intensity', 'channel': 'A2 Spark UV 387', 'data':None}]

    statistics_calculator = StatisticsCalculator(None, kc)
    statistics_calculator.run()

