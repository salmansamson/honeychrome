"""
Honeychrome Plugin Template
---------------------------
This module defines the interface for a Honeychrome tabbed plugin.

Required Attributes:
    plugin_name (str): The display name used for the tab in the main window.
    plugin_enabled (bool): Toggle to True to load the plugin into the UI.
    PluginWidget (class): the widget to be displayed in the tab

Technical Requirements:
    - Framework: PySide6 (Qt for Python)
"""
from datetime import datetime
from pathlib import Path
import colorcet as cc
import numpy as np

from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QPushButton, QLabel, QComboBox
from PySide6.QtCore import Qt
from honeychrome.controller_components.functions import sample_from_fcs, apply_transfer_matrix, apply_gates_in_place
from honeychrome.view_components.busy_cursor import with_busy_cursor
from honeychrome.view_components.clear_layout import clear_layout
from honeychrome.view_components.exportable_plot_widget import ExportablePlotWidget
from honeychrome.view_components.ordered_multi_sample_picker import OrderedMultiSamplePicker
from honeychrome.view_components.copyable_table_widget import CopyableTableWidget

plugin_name = 'Data Processing Example Plugin'
plugin_enabled = True
table_headers = ['Index', 'Colour', 'Count']


class PluginWidget(QWidget):
    """
    The main UI container for the plugin.

    Required arguments:
        bus: the signals to communicate with the rest of the honeychrome app
        controller: the honeychrome controller including all ephemeral data and the experiment model
    """
    def __init__(self, bus=None, controller=None, parent=None):
        super().__init__(parent)
        self.bus = bus
        self.controller = controller

        # --- Create widget, scroll area and layouts to hold the plugin content ---
        self.label = QLabel('Data Processing Example')
        self.label_disabled = QLabel('Data Processing Example: unmixed data not available. Set up the spectral model first.')

        # the content widget goes in a scroll widget, which goes in the PluginWidget
        self.content_widget = QWidget()
        main_layout = QVBoxLayout(self.content_widget)

        # make this widget scrollable and resizeable
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(self.content_widget)

        overall_layout = QVBoxLayout(self)
        overall_layout.addWidget(self.label_disabled)
        overall_layout.addWidget(scroll)

        # --- Add gui objects for a data processing workflow ---

        # Add sample picker
        self.picker = OrderedMultiSamplePicker(title="Choose Source Samples for Processing")
        # Add gate selection combobox
        self.gate_combo = QComboBox()
        self.gate_combo.addItem("Select Gate:")  # placeholder for "no selection"
        output_widget = QWidget()
        self.output_layout = QVBoxLayout(output_widget)

        # --- Add gui elements ---
        self.build_button = QPushButton('Build model')
        self.build_button.setToolTip('Runs the process on selected samples')
        self.build_button.clicked.connect(self.build_model)

        training_widget = QWidget()
        self.training_layout = QVBoxLayout(training_widget)

        prediction_widget = QWidget()
        self.prediction_layout = QVBoxLayout(prediction_widget)

        main_layout.addWidget(self.label)
        main_layout.addWidget(self.gate_combo)
        main_layout.addWidget(self.picker)
        main_layout.addWidget(self.build_button)
        main_layout.addWidget(training_widget)
        main_layout.addWidget(prediction_widget)
        main_layout.addWidget(output_widget)
        main_layout.addStretch()

        self.bus.modeChangeRequested.connect(self.initialise_gui)
        self.bus.loadSampleRequested.connect(self.predict_sample)

        self.reducer = None
        self.clusterer = None
        self.label_to_color = None

    def initialise_gui(self, mode):
        # re-iniitialise if user selects this tab
        if mode == plugin_name:
            # only if unmixing already done
            if self.controller.experiment.process['unmixing_matrix'] is not None:
                self.label_disabled.setVisible(False)
                self.content_widget.setVisible(True)

                selection = self.picker.get_ordered_list()
                if not selection:
                    # populate sample picker if selection wasn't already made
                    all_samples = self.controller.experiment.samples['all_samples']
                    source_samples_relative_to_raw = [str(Path(sample).relative_to(self.controller.experiment.settings['raw']['raw_samples_subdirectory']))
                                                      for sample in all_samples]
                    self.picker.set_items(source_samples_relative_to_raw)

                if self.gate_combo.currentText() == "Select Gate:":
                    # populate gate selection if selection wasn't already made
                    self.gate_combo.clear()
                    self.gate_combo.addItem("Select Gate:")  # placeholder for "no selection"
                    unmixed_gate_names = ['root'] + [g[0] for g in self.controller.unmixed_gating.get_gate_ids()]
                    self.gate_combo.addItems(unmixed_gate_names)

            else:
                self.label_disabled.setVisible(True)
                self.content_widget.setVisible(False)

    def progress_message(self, text):
        # output to stdout
        print(text)

        # output to status bar
        self.bus.statusMessage.emit(text)

        # output within tabbed window
        label = QLabel(text)
        label.setTextFormat(Qt.RichText)
        label.setWordWrap(True)
        self.output_layout.addWidget(label)

    @with_busy_cursor
    def umap_fit_transform(self, data):
        import umap
        self.reducer = umap.UMAP(n_neighbors=15, min_dist=0.1, transform_queue_size=1.0, n_components=2).fit(data)
        embedding = self.reducer.transform(data)
        return embedding

    @with_busy_cursor
    def generate_clusterer(self, embedding):
        # Cluster the UMAP output with HDBSCAN
        import hdbscan
        self.clusterer = hdbscan.HDBSCAN(min_cluster_size=50, prediction_data=True).fit(embedding)

    def predict_new_data(self, data):
        import hdbscan
        new_embedding = self.reducer.transform(data)
        new_labels, strengths = hdbscan.approximate_predict(self.clusterer, new_embedding)
        return new_embedding, new_labels, strengths

    def build_model(self):
        clear_layout(self.training_layout)

        self.progress_message(f'{datetime.now():%H:%M:%S} Started model building...')

        gate_name = self.gate_combo.currentText()
        if gate_name == "Select Gate:":
            self.progress_message('Please select a gate.')
            return
        else:
            self.progress_message(f'{datetime.now():%H:%M:%S} Using {gate_name} gate')

        source_samples = self.picker.get_ordered_list()
        if source_samples:
            self.progress_message(f'{datetime.now():%H:%M:%S} Loading samples from FCS files: {source_samples}')
        else:
            self.progress_message(f'Please select at least one source file.')
            return

        cytometry_data = self.controller.data_for_cytometry_plots_unmixed.copy()
        gated_sample_data_all = []
        for sample_name in source_samples:
            full_sample_path = str(self.controller.experiment_dir / self.controller.experiment.settings['raw']['raw_samples_subdirectory'] / sample_name)
            sample = sample_from_fcs(full_sample_path)
            raw_event_data = sample.get_events(source='raw')
            n_events = sample.event_count

            if n_events > 0:
                unmixed_event_data = apply_transfer_matrix(self.controller.transfer_matrix, raw_event_data)
                cytometry_data.update({'event_data': unmixed_event_data})

                gate_membership = {'root': np.ones(len(cytometry_data['event_data']), dtype=np.bool_)}
                cytometry_data.update({'gate_membership': gate_membership})
                gates_to_calculate = [g[0] for g in cytometry_data['gating'].get_gate_ids()]
                apply_gates_in_place(cytometry_data, gates_to_calculate=gates_to_calculate)
                gate_membership = cytometry_data['gate_membership'][gate_name]
                gated_sample_data = cytometry_data['event_data'][gate_membership]
                gated_sample_data_all.append(gated_sample_data)
                self.progress_message(f'{datetime.now():%H:%M:%S} Loaded {sample_name}: {len(gated_sample_data)}/{n_events} events within {gate_name}')
            else:
                self.progress_message(f'Warning: 0 events in {sample_name}.')

        gated_sample_data_all = np.concatenate(gated_sample_data_all)
        self.progress_message(f'{datetime.now():%H:%M:%S} Concatenated source data {len(gated_sample_data_all)} events')

        try:
            # Initialize and fit UMAP
            # n_neighbors: controls local vs global structure (5 to 50 is typical)
            # min_dist: controls how tightly points are packed (0.1 is default)

            data = gated_sample_data_all
            # data = gated_sample_data_all[np.random.choice(np.arange(len(gated_sample_data_all)), 5000)]
            self.progress_message(f'{datetime.now():%H:%M:%S} Calculating UMAP reducer and embedding')
            embedding = self.umap_fit_transform(data)
            self.generate_clusterer(embedding)
            self.progress_message(f'{datetime.now():%H:%M:%S} Clustering with HDBSCAN')
            labels = self.clusterer.labels_

            # ---- prepare plot and table output-----
            self.progress_message(f'{datetime.now():%H:%M:%S} Preparing UMAP plot')
            # unique_labels = np.unique(labels).astype(int)
            unique_labels = np.arange(-1, max(labels)+1)
            palette = cc.glasbey

            self.label_to_color = {}
            table_data = []
            for i, unique_label in enumerate(unique_labels):
                l = int(unique_label)
                if l == -1:
                    self.label_to_color[l] = "#7f7f7f"  # Standard Gray for noise
                else:
                    # Use modulo to wrap around if there are > 256 clusters
                    self.label_to_color[l] = palette[i % len(palette)]

                table_data.append({'Index': l, 'Colour': self.label_to_color[l], 'Count': int(np.sum(labels == l))})

            plot_colors = [self.label_to_color[l] for l in labels]
            from matplotlib import pyplot as plt
            figure, ax = plt.subplots(1)
            ax.axis('equal')
            ax.scatter(embedding[:, 0], embedding[:, 1], c=plot_colors, s=5)

            # put plot in a widget and add to the layout
            self.training_layout.addWidget(QLabel("Training UMAP and clusters"))

            plot_widget = ExportablePlotWidget(figure, title="UMAP training data and clustering", experiment_dir=self.controller.experiment_dir)
            self.training_layout.addWidget(plot_widget)

            # generate and add table widget
            table_widget = CopyableTableWidget(table_data, table_headers)
            self.training_layout.addWidget(table_widget)

            self.progress_message(f'{datetime.now():%H:%M:%S} Finished model building.')
            self.progress_message('Click on a sample (in the sample browser) to view it in the same UMAP embedding and clusters.')

        except Exception as e:
            self.progress_message(f'Exception: {e}')


    def predict_sample(self, sample_path):
        if self.controller.current_mode == plugin_name:
            if self.reducer and self.clusterer:
                clear_layout(self.prediction_layout)

                gate_name = self.gate_combo.currentText()
                if gate_name == "Select Gate:":
                    self.progress_message('Please select a gate.')
                    return

                cytometry_data = self.controller.data_for_cytometry_plots_unmixed.copy()

                full_sample_path = str(self.controller.experiment_dir / sample_path)
                sample = sample_from_fcs(full_sample_path)
                raw_event_data = sample.get_events(source='raw')
                n_events = sample.event_count

                if n_events > 0:
                    unmixed_event_data = apply_transfer_matrix(self.controller.transfer_matrix, raw_event_data)
                    cytometry_data.update({'event_data': unmixed_event_data})

                    gate_membership = {'root': np.ones(len(cytometry_data['event_data']), dtype=np.bool_)}
                    cytometry_data.update({'gate_membership': gate_membership})
                    gates_to_calculate = [g[0] for g in cytometry_data['gating'].get_gate_ids()]
                    apply_gates_in_place(cytometry_data, gates_to_calculate=gates_to_calculate)
                    gate_membership = cytometry_data['gate_membership'][gate_name]
                    gated_sample_data = cytometry_data['event_data'][gate_membership]
                    self.progress_message(f'{datetime.now():%H:%M:%S} Loaded {sample_path}: {len(gated_sample_data)}/{n_events} events within {gate_name}')
                else:
                    self.progress_message(f'Cannot process sample: 0 events in {sample_path}.')
                    return

            try:
                self.progress_message(f'{datetime.now():%H:%M:%S} Calculating UMAP embedding for {sample_path}')
                embedding, labels, strengths = self.predict_new_data(gated_sample_data)

                # ---- prepare plot and table output-----
                self.progress_message(f'{datetime.now():%H:%M:%S} Preparing UMAP plot')
                table_data = []
                unique_labels = self.label_to_color.keys()
                for i, l in enumerate(unique_labels):
                    table_data.append({'Index': l, 'Colour': self.label_to_color[l], 'Count': int(np.sum(labels == l))})

                plot_colors = [self.label_to_color[l] for l in labels]
                from matplotlib import pyplot as plt
                figure, ax = plt.subplots(1)
                ax.axis('equal')
                ax.scatter(embedding[:, 0], embedding[:, 1], c=plot_colors, s=5)

                # put plot in a widget and add to the layout
                self.prediction_layout.addWidget(QLabel("Prediction UMAP and clusters"))
                plot_widget = ExportablePlotWidget(figure, title=f"{str(Path(sample_path).stem)} UMAP prediction data and clustering", experiment_dir=self.controller.experiment_dir)
                self.prediction_layout.addWidget(plot_widget)

                # generate and add table widget
                table_widget = CopyableTableWidget(table_data, table_headers)
                self.prediction_layout.addWidget(table_widget)

                self.progress_message(f'{datetime.now():%H:%M:%S} Finished prediction of {sample_path}.')

            except Exception as e:
                self.progress_message(f'Exception: {e}')




