import os
from pathlib import Path

from honeychrome.settings import file_extension, experiments_folder
from honeychrome.view_components.configuration_dialogs import AppConfigDialog, ExperimentSettings, InstrumentConfigDialog
from honeychrome.view_components.help_toggle_widget import HelpToggleWidget
from honeychrome.view_components.import_fcs_files_widget import ImportFCSFilesWidget
from honeychrome.view_components.oscilloscope_widget import OscilloscopeWidget
from honeychrome.view_components.statistical_plotter import StatisticalComparisonWidget

os.environ["QT_LOGGING_RULES"] = "qt.core.qobject.connect=false" #suppress pyqtgraph graphicslayoutwidget warning

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow, QFileDialog, QWidget, QHBoxLayout, QSplitter, QTabWidget, QStatusBar, QVBoxLayout, QLabel, QProgressBar, QScrollArea, QPushButton
from PySide6.QtCore import Qt, QSettings, QByteArray, Slot, QTimer

from honeychrome.view_components.gating_hierarchy_widget import GatingHierarchyWidget
from honeychrome.view_components.heatmap_viewedit import HeatmapViewEditor
from honeychrome.view_components.nxn_grid import NxNGrid
from honeychrome.view_components.profiles_viewer import ProfilesViewer
from honeychrome.view_components.spectral_model_editor import SpectralControlsEditor
from honeychrome.view_components.cytometry_grid_widget import CytometryGridWidget
from honeychrome.view_components.cytometry_toolbar import CytometryToolbar
from honeychrome.view_components.acquisition_widget import AcquisitionWidget
from honeychrome.view_components.gains_widget import GainsWidget
from honeychrome.view_components.icon_loader import icon
from honeychrome.view_components.sample_widget import SampleWidget
from honeychrome.view_components.help_texts import process_help_text

base_directory = Path.home() / experiments_folder


def clear_layout(widget):
    """Safely clear all widgets from current layout"""
    if widget.layout():
        # Remove all widgets from the layout
        while widget.layout().count():
            child = widget.layout().takeAt(0)
            if child.widget():
                child.widget().deleteLater()  # The layout itself will be garbage collected when replaced


class MainWindow(QMainWindow):
    def __init__(self, bus=None, controller=None, parent=None, is_dark=False):
        super().__init__(parent)

        # connect all signals
        self.bus = bus
        # connect to data
        self.controller = controller
        # connect to QSettings
        self.settings = QSettings("honeychrome", "MainWindow")

        # autosave if window closed
        self.destroyed.connect(lambda: self.controller.save_experiment())

        ##### build menus/buttons/widgets
        # left splitter
        self.sample_tree = SampleWidget(bus, parent=self, controller=self.controller)
        self.acquisition_widget = AcquisitionWidget(bus, parent=self)
        self.gains_widget = GainsWidget(bus, parent=self)
        self.sample_tree.set_selection(self.controller.current_sample_path)

        # raw
        self.gating_tree_raw = GatingHierarchyWidget(bus, mode='raw')
        self.cytometry_grid_raw = CytometryGridWidget(bus, parent=self, mode='raw', gating_tree=self.gating_tree_raw)
        self.cytometry_toolbar_raw = CytometryToolbar(bus, parent=self.cytometry_grid_raw)
        self.cytometry_grid_raw.set_toolbar(self.cytometry_toolbar_raw)
        self.gating_tree_raw.set_toolbar(self.cytometry_toolbar_raw)

        # process
        self.help_spectral_process = HelpToggleWidget(text=process_help_text)
        self.spectral_controls_editor = SpectralControlsEditor(bus, self.controller)
        self.profiles_viewer = ProfilesViewer(bus, self.controller)
        self.similarity_viewer = HeatmapViewEditor(bus, self.controller, 'similarity_matrix', is_dark)
        self.unmixing_viewer = HeatmapViewEditor(bus, self.controller, 'unmixing_matrix', is_dark)
        self.compensation_editor = HeatmapViewEditor(bus, self.controller, 'spillover', is_dark)
        self.nxn_viewer = NxNGrid(bus, self.controller, is_dark=is_dark)

        # unmixed
        self.gating_tree_unmixed = GatingHierarchyWidget(bus, mode='unmixed')
        self.cytometry_grid_unmixed = CytometryGridWidget(bus, parent=self, mode='unmixed', gating_tree=self.gating_tree_unmixed)
        self.tip_unmixed = QWidget()
        container_layout = QVBoxLayout(self.tip_unmixed)
        container_layout.addWidget(QLabel('Unmixed data requires a spectral model.\nTo see unmixed data, first define the spectral controls (spectral process tab) and calculate the unmixing matrix.'))
        container_layout.addStretch(100)
        self.cytometry_toolbar_unmixed = CytometryToolbar(bus, parent=self.cytometry_grid_unmixed)
        self.cytometry_grid_unmixed.set_toolbar(self.cytometry_toolbar_unmixed)
        self.gating_tree_unmixed.set_toolbar(self.cytometry_toolbar_unmixed)

        # statistics
        self.tip_statistics = QWidget()
        container_layout = QVBoxLayout(self.tip_statistics)
        container_layout.addWidget(QLabel('Statistical comparison of samples requires unmixed data.\nTo make a statistical comparison, first define the spectral model (spectral process tab) and define at least one gate on the unmixed data (unmixed data tab).'))
        container_layout.addStretch(100)
        self.statistical_comparison_widget = StatisticalComparisonWidget(bus, self.controller)

        # --- Menu Bar ---
        menubar = self.menuBar()
        file_menu = menubar.addMenu("&File")
        edit_menu = menubar.addMenu("&Edit")
        view_menu = menubar.addMenu("&View")
        help_menu = menubar.addMenu("&Help")

        # file menu actions
        action_new = QAction(icon('file'), "New Experiment (default template)", self)
        action_new.triggered.connect(self.bus.newExpRequested)
        action_new_from_this_template = QAction(icon('file-plus'), "New Experiment (this experiment as template)", self)
        action_new_from_this_template.triggered.connect(self.bus.newExpRequestedFromThisTemplate)
        action_new_from_choose_template = QAction(icon("file-spark"), "New Experiment (choose template)", self)
        action_new_from_choose_template.triggered.connect(self.bus.newExpRequestedFromTemplate)
        action_open = QAction(icon('file-upload'), "Open Experiment", self)
        action_open.triggered.connect(self.bus.openExpRequested)
        action_save = QAction(icon('file-download'), "Save Experiment As Template", self)
        action_save.triggered.connect(self.bus.saveAsTemplateRequested)
        action_new_sample = QAction(icon('square-plus'), "New Sample", self)
        action_new_sample.triggered.connect(self.bus.showNewSampleWidget)
        action_batch_add_samples = QAction(icon('files'), "Batch add samples from CSV", self)
        action_batch_add_samples.triggered.connect(self.bus.batchAddSamples)
        action_import_fcs_files = QAction(icon('files'), "Import FCS files", self)
        action_import_fcs_files.triggered.connect(self.open_import_fcs_files_widget)
        action_export_all = QAction(icon('files'), "Batch export FCS files", self)
        action_export_all.triggered.connect(self.bus.showExportModal)
        action_generate_report = QAction(icon('file-type-docx'), "Generate sample report", self)
        action_generate_report.triggered.connect(self.bus.generateSampleReport)
        action_quit = QAction(icon('logout'), "Quit", self)
        action_quit.triggered.connect(self.close)

        file_menu.addAction(action_new)
        file_menu.addAction(action_new_from_this_template)
        file_menu.addAction(action_new_from_choose_template)
        file_menu.addAction(action_open)
        file_menu.addAction(action_save)
        file_menu.addAction(action_new_sample)
        file_menu.addAction(action_batch_add_samples)
        file_menu.addAction(action_import_fcs_files)
        file_menu.addAction(action_export_all)
        file_menu.addAction(action_generate_report)
        file_menu.addAction(action_quit)

        # edit menu
        action_app_config = QAction(icon('adjustments'), "App Configuration", self)
        action_app_config.triggered.connect(self.app_config)
        action_instrument_config = QAction(icon('tool'), "Instrument Configuration", self)
        action_instrument_config.triggered.connect(self.instrument_config)
        action_experiment_settings = QAction(icon('settings'), "Experiment Settings", self)
        action_experiment_settings.triggered.connect(self.expt_settings)
        edit_menu.addAction(action_app_config)
        edit_menu.addAction(action_instrument_config)
        edit_menu.addAction(action_experiment_settings)

        # view menu
        # action_acquire = QAction(icon('player-play'), "Acquisition Panel", self)
        action_acquire = QAction("Acquisition Panel", self)
        action_acquire.setCheckable(True)
        action_acquire.setChecked(self.settings.value("acquisition_visible", True, type=bool))
        action_acquire.triggered.connect(lambda : self.acquisition_widget.setVisible(action_acquire.isChecked()))
        action_acquire.triggered.connect(lambda : self._save_visibility_state())
        view_menu.addAction(action_acquire)

        # action_gains = QAction(icon('adjustments'), "Gains Panel", self)
        action_gains = QAction("Gains Panel", self)
        action_gains.setCheckable(True)
        action_gains.setChecked(self.settings.value("gains_visible", True, type=bool))
        action_gains.triggered.connect(lambda : self.gains_widget.setVisible(action_gains.isChecked()))
        action_gains.triggered.connect(lambda : self._save_visibility_state())
        view_menu.addAction(action_gains)

        action_oscilloscope = QAction(icon('wave-sine'), "Oscilloscope Viewer", self)
        action_oscilloscope.triggered.connect(self.open_oscilloscope_widget)
        view_menu.addAction(action_acquire)
        view_menu.addAction(action_gains)
        view_menu.addAction(action_oscilloscope)

        # help menu
        action_forum = QAction(icon('bubble-text'), "Users Forum", self)
        action_forum.triggered.connect(lambda: self.bus.popupMessage.emit('Users forum coming soon! For now, please email <a href="mailto:hello@cytkit.com">hello@cytkit.com</a> with your bugs, ideas and requests.'))
        # todo user forum
        action_about = QAction(icon('carambola'), "About Honeychrome", self)
        action_about.triggered.connect(self.bus.aboutHoneychrome.emit)
        help_menu.addAction(action_forum)
        help_menu.addAction(action_about)


        # --- Central Widget Layout ---
        central_widget = QWidget()
        main_layout = QHBoxLayout()

        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel (samples list, acquisition panel, gains, dock)
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)

        left_layout.addWidget(self.sample_tree)
        left_layout.addWidget(self.acquisition_widget)
        left_layout.addWidget(self.gains_widget)

        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self.splitter.addWidget(left_container)

        # Right panel (tab widget)
        self.tabs = QTabWidget()

        # --- Raw ---
        self.raw_tab = QWidget()
        self.raw_layout = QVBoxLayout()
        self.raw_tab.setLayout(self.raw_layout)
        self.raw_layout.addWidget(self.cytometry_toolbar_raw)
        self.raw_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.raw_splitter.addWidget(self.cytometry_grid_raw)
        self.raw_splitter.addWidget(self.gating_tree_raw)
        self.gating_tree_raw.setParent(self.raw_splitter)
        self.raw_splitter.setStretchFactor(0, 1)
        self.raw_splitter.setStretchFactor(1, 0)
        self.raw_layout.addWidget(self.raw_splitter)
        self.tabs.addTab(self.raw_tab, "Raw Data")

        # --- Process ---
        self.process_tab = QWidget()
        scroll_area = QScrollArea()
        scroll_area.setWidget(self.process_tab)
        scroll_area.setWidgetResizable(True)
        self.process_layout = QVBoxLayout()
        self.process_layout.addWidget(self.help_spectral_process)
        self.process_layout.addWidget(self.spectral_controls_editor)
        self.process_layout.addWidget(self.profiles_viewer)
        self.process_layout.addWidget(self.similarity_viewer)
        self.process_layout.addWidget(self.unmixing_viewer)
        self.process_layout.addWidget(self.compensation_editor)
        self.process_layout.addWidget(self.nxn_viewer)
        self.process_layout.addStretch()
        self.process_tab.setLayout(self.process_layout)
        self.tabs.addTab(scroll_area, "Spectral Process")

        # --- Unmixed ---
        self.unmixed_tab = QWidget()
        self.unmixed_layout = QVBoxLayout()
        self.unmixed_tab.setLayout(self.unmixed_layout)
        self.unmixed_layout.addWidget(self.tip_unmixed)
        self.unmixed_layout.addWidget(self.cytometry_toolbar_unmixed)
        self.unmixed_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.unmixed_splitter.addWidget(self.cytometry_grid_unmixed)
        self.unmixed_splitter.addWidget(self.gating_tree_unmixed)
        self.gating_tree_unmixed.setParent(self.unmixed_splitter)
        self.unmixed_splitter.setStretchFactor(0, 1)
        self.unmixed_splitter.setStretchFactor(1, 0)
        self.unmixed_layout.addWidget(self.unmixed_splitter)
        self.tabs.addTab(self.unmixed_tab, "Unmixed Data")

        # --- Statistics ---
        self.statistics_tab = QWidget()
        self.statistics_layout = QVBoxLayout()
        self.statistics_tab.setLayout(self.statistics_layout)
        self.statistics_layout.addWidget(self.tip_statistics)
        self.statistics_layout.addWidget(self.statistical_comparison_widget)
        self.tabs.addTab(self.statistics_tab, "Statistics")

        # Connect to tab change
        self.tabs.currentChanged.connect(self.on_tab_changed)

        # add to splitter
        self.splitter.addWidget(self.tabs)

        main_layout.addWidget(self.splitter)
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        # --- Status Bar ---
        status = QStatusBar()
        self.setStatusBar(status)
        self.statusBar().showMessage("Ready")
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximumWidth(250)
        status.addPermanentWidget(self.progress_bar)
        self.progress_bar.setVisible(False)  # Hide initially
        self.bus.progress.connect(self.update_progress)
        self.bus.statusMessage.connect(self.status_message)

        # widgets visibility state
        self._restore_visibility_state()

        if not self.controller.experiment_compatible_with_acquisition:
            action_new_sample.setEnabled(False)
            action_batch_add_samples.setEnabled(False)
            action_acquire.setEnabled(False)
            action_gains.setEnabled(False)
            action_oscilloscope.setEnabled(False)
            self.acquisition_widget.setVisible(False)
            self.gains_widget.setVisible(False)

        self.bus.openImportFCSWidget.connect(self.open_import_fcs_files_widget)


    @Slot(int, int)
    def update_progress(self, n, m):
        self.progress_bar.setMaximum(m)
        self.progress_bar.setValue(n)
        if n != m:
            self.progress_bar.setVisible(True)
            self.statusBar().showMessage(f"Processing {n}/{m}")
        else:
            self.statusBar().showMessage("Ready")
            QTimer.singleShot(100, lambda: self.progress_bar.setVisible(False))

    @Slot(str)
    def status_message(self, message):
        self.statusBar().showMessage(message)

    def on_tab_changed(self, index):
        tab_name = self.tabs.tabText(index)
        print(f'View: tab changed {tab_name}')
        self.bus.modeChangeRequested.emit(tab_name)

    def closeEvent(self, event):
        self.save_state()
        super().closeEvent(event)

    def app_config(self):
        dialog = AppConfigDialog(self, self.bus)
        dialog.exec()

    def instrument_config(self):
        dialog = InstrumentConfigDialog(self)
        dialog.exec()

    def expt_settings(self):
        dialog = ExperimentSettings(self.controller.experiment, self.bus, self)
        dialog.exec()

    def open_oscilloscope_widget(self):
        widget = OscilloscopeWidget(self.controller, self.bus)
        if widget.isHidden():
            widget.show()
        else:
            widget.raise_()  # Bring to top
            widget.activateWindow()  # Give focus

    @Slot(bool)
    def open_import_fcs_files_widget(self, failed_to_load_sample_warning=False):
        dialog = ImportFCSFilesWidget(self.bus, self.controller, failed_to_load_sample_warning)
        dialog.exec()

    def save_state(self):
        # QByteArray returned by saveState() — stored directly in QSettings
        self.settings.setValue("main_splitter_state", self.splitter.saveState())
        self.settings.setValue("raw_splitter_state", self.raw_splitter.saveState())
        self.settings.setValue("unmixed_splitter_state", self.unmixed_splitter.saveState())
        """Save window geometry and maximized state to QSettings."""
        if self.isMaximized():
            self.settings.setValue("window/maximized", True)
        else:
            self.settings.setValue("window/maximized", False)
            self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.sync()

    def restore_state(self):
        state = self.settings.value("main_splitter_state")
        raw_state = self.settings.value("raw_splitter_state")
        unmixed_state = self.settings.value("unmixed_splitter_state")
        if state is not None:
            self.splitter.restoreState(state)
        if raw_state is not None:
            self.raw_splitter.restoreState(raw_state)
        if unmixed_state is not None:
            self.unmixed_splitter.restoreState(unmixed_state)
        """Restore window geometry and maximized state from QSettings."""
        maximized = self.settings.value("window/maximized", False, type=bool)
        geometry = self.settings.value("window/geometry")

        if geometry is not None:
            self.restoreGeometry(QByteArray(geometry))
        else:
            self.resize(1000, 600)

        if maximized:
            self.showMaximized()
        else:
            self.showNormal()

    def _save_visibility_state(self):
        for name, widget in {"gains": self.gains_widget, "acquisition": self.acquisition_widget}.items():
            self.settings.setValue(f"{name}_visible", widget.isVisible())

    def _restore_visibility_state(self):
        for name, widget in {"gains": self.gains_widget, "acquisition": self.acquisition_widget}.items():
            visible = self.settings.value(f"{name}_visible", True, type=bool)
            widget.setVisible(visible)

if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication
    from honeychrome.controller import Controller
    from pathlib import Path
    from honeychrome.view_components.event_bus import EventBus

    app =  QApplication(sys.argv)

    kc = Controller()
    base_directory = Path.home() / 'spectral_cytometry'
    experiment_name = base_directory / '20240620 Spectral Symposium-poor cell unmixed'
    experiment_path = experiment_name.with_suffix('.kit')
    kc.load_experiment(experiment_path) # note this loads first sample too and runs calculate all histograms and statistics

    main_window = MainWindow(bus=EventBus(), controller=kc)
    main_window.restore_state()
    # main_window.show()

    main_window.gating_tree_raw.init_data(kc.data_for_cytometry_plots)

    exit_code = app.exec()
    sys.exit(exit_code)
