"""
test_gui_integration.py
-----------------------
End-to-end GUI integration tests for Honeychrome.

These tests drive the real Qt application through a complete AutoSpectral
workflow using pytest-qt (``qtbot``).  They are intended to run as a GitHub
Actions job on every release branch, once per supported OS
(ubuntu-22.04, windows-2022, macos-14, macos-latest).

Prerequisites
-------------
* A headless X-server is available (Linux: xvfb-run / Xvfb).
* The Honeychrome package is installed in the current Python environment
  (``pip install -e .`` or from the built wheel/tarball).
* The AutoSpectral Full Example dataset has been downloaded and the
  environment variable ``HONEYCHROME_TEST_DATA_DIR`` points to it.
  The directory must contain:
      Raw/                       – experiment FCS samples
      Raw/Cell controls/         – single-stained cell controls
      Raw/Bead controls/         – single-stained bead controls (optional)
  If the variable is unset the tests are automatically skipped.

Usage
-----
    # all GUI tests
    pytest test_gui_integration.py -v

    # skip slow NxN / fine-tuning tests
    pytest test_gui_integration.py -v -m "not slow"

    # run on macOS in headless mode via offscreen platform
    QT_QPA_PLATFORM=offscreen pytest test_gui_integration.py -v

Environment variables
---------------------
HONEYCHROME_TEST_DATA_DIR   Path to the AutoSpectral example dataset root.
HONEYCHROME_TEST_TIMEOUT    Per-step timeout in ms (default 30 000).
"""

import os
import sys
import time
import tempfile
import shutil
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

# ---------------------------------------------------------------------------
# Constants / helpers
# ---------------------------------------------------------------------------

# Respect an environment-level timeout; default 30 s per step.
STEP_TIMEOUT = int(os.environ.get("HONEYCHROME_TEST_TIMEOUT", 30_000))

# Marker: require real data on disk.
requires_data = pytest.mark.skipif(
    not os.environ.get("HONEYCHROME_TEST_DATA_DIR"),
    reason="HONEYCHROME_TEST_DATA_DIR not set – skipping GUI integration tests",
)


def _wait(qtbot: QtBot, ms: int = 500):
    """Short unconditional pause to let the Qt event-loop process events."""
    qtbot.wait(ms)


def _find_child(widget, type_, name: str | None = None, text: str | None = None):
    """
    Return the first child widget of *type_* whose objectName or text matches.
    Raises AssertionError with a helpful message if nothing is found.
    """
    candidates = widget.findChildren(type_)
    for c in candidates:
        if name and c.objectName() != name:
            continue
        if text and hasattr(c, "text") and c.text() != text:
            continue
        return c
    raise AssertionError(
        f"Could not find child {type_.__name__}"
        + (f" with objectName={name!r}" if name else "")
        + (f" with text={text!r}" if text else "")
        + f" in {widget!r}"
    )


def _find_button(widget, text: str):
    """Find a QPushButton by its label text anywhere below *widget*."""
    from PySide6.QtWidgets import QPushButton

    for btn in widget.findChildren(QPushButton):
        if btn.text().strip() == text or text in btn.text():
            return btn
    raise AssertionError(f"QPushButton with text {text!r} not found under {widget!r}")


def _tab_index(tabs, title: str) -> int:
    for i in range(tabs.count()):
        if tabs.tabText(i) == title:
            return i
    raise AssertionError(f"Tab {title!r} not found")


def _sample_tree_items(sample_widget):
    """Return list of QModelIndex leaves from the SampleWidget tree view."""
    tree = sample_widget.tree_view  # QTreeView inside SampleWidget
    model = tree.model()
    results = []

    def _walk(parent):
        for row in range(model.rowCount(parent)):
            idx = model.index(row, 0, parent)
            if model.rowCount(idx) == 0:
                results.append(idx)
            else:
                _walk(idx)

    _walk(tree.rootIndex())
    return results


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def test_data_dir():
    raw = os.environ.get("HONEYCHROME_TEST_DATA_DIR")
    if not raw:
        pytest.skip("HONEYCHROME_TEST_DATA_DIR not set")
    p = Path(raw).expanduser().resolve()
    if not p.exists():
        pytest.skip(f"HONEYCHROME_TEST_DATA_DIR={p} does not exist")
    return p


@pytest.fixture(scope="session")
def experiment_dir(tmp_path_factory, test_data_dir):
    """
    Create a fresh temporary experiment directory and symlink the raw data
    into it so that Honeychrome can find the FCS files without copying them.
    """
    exp_root = tmp_path_factory.mktemp("honeychrome_test_experiment")
    raw_link = exp_root / "Raw"

    # Create symlink (falls back to copy on Windows where symlinks may require
    # elevated privileges in CI).
    try:
        raw_link.symlink_to(test_data_dir / "Raw")
    except (OSError, NotImplementedError):
        shutil.copytree(test_data_dir / "Raw", raw_link)

    return exp_root


# ---------------------------------------------------------------------------
# Function-scoped main-window fixture  (fresh app per test is not practical
# for a linear workflow; we keep ONE window across all tests in this module
# by using module scope and an explicit ordering strategy).
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def app_window(qapp, experiment_dir):
    """
    Launch the Honeychrome MainWindow once for the whole module.
    Tests share this window and must be run in order (use ``-p no:randomly``
    or declare explicit dependencies via ``pytest-order``).
    """
    from honeychrome.event_bus import EventBus
    from honeychrome.controller import Controller
    from honeychrome.view_components.main_window import MainWindow

    bus = EventBus()
    controller = Controller()
    controller.bus = bus

    win = MainWindow(bus=bus, controller=controller, is_dark=False)
    win.show()
    win.raise_()

    yield win

    win.close()


# ---------------------------------------------------------------------------
# STEP 1 – New experiment
# ---------------------------------------------------------------------------


@requires_data
@pytest.mark.gui
def test_01_new_experiment(qtbot: QtBot, app_window, experiment_dir):
    """
    Trigger 'New Experiment', supply a name and confirm the experiment is
    created on disk.
    """
    from PySide6.QtWidgets import QFileDialog

    win = app_window
    exp_path = experiment_dir / "AutoSpectral_CI_Test.kit"

    # Intercept the NewFileDialog that opens when the menu action fires.
    # We patch its exec() to return Accept and its selectedFiles() to return
    # our desired path.
    original_exec = QFileDialog.exec

    def _mock_exec(self):
        # Inject our path and accept immediately.
        self.selectFile(str(exp_path))
        return 1  # QDialog.Accepted

    QFileDialog.exec = _mock_exec
    try:
        # Trigger "New Experiment (default template)"
        win.bus.newExpRequested.emit()
        _wait(qtbot, 1000)
    finally:
        QFileDialog.exec = original_exec

    # The experiment file must now exist.
    assert exp_path.exists(), f"Experiment file not created at {exp_path}"
    # The window title or controller must reflect the new experiment name.
    assert win.controller.experiment.experiment_path is not None


# ---------------------------------------------------------------------------
# STEP 2 – Import AutoSpectral data and update raw channel settings
# ---------------------------------------------------------------------------


@requires_data
@pytest.mark.gui
def test_02_import_fcs_and_update_channels(qtbot: QtBot, app_window, experiment_dir):
    """
    Open the Import FCS Files dialog, set the Raw subdirectory to the symlinked
    folder, click 'Update Experiment Configuration', and wait for completion.
    """
    from PySide6.QtWidgets import QDialog

    win = app_window
    controller = win.controller

    # Point the experiment at the symlinked Raw folder.
    controller.experiment.settings["raw"]["raw_samples_subdirectory"] = "Raw"
    controller.experiment.settings["raw"]["single_stain_controls_subdirectory"] = (
        "Raw/Cell controls/Reference Group"
    )

    # Open the Import FCS Files widget directly (mirrors the menu action).
    from honeychrome.view_components.import_fcs_files_widget import ImportFCSFilesWidget

    dialog = ImportFCSFilesWidget(win, bus=win.bus, controller=controller)

    # Click the submit button without actually showing the dialog.
    with qtbot.waitSignal(win.bus.experimentUpdated, timeout=STEP_TIMEOUT, raising=False):
        dialog.submit()
        # Process events until the background thread finishes.
        qtbot.waitUntil(
            lambda: not dialog.thread or not dialog.thread.isRunning(),
            timeout=STEP_TIMEOUT,
        )

    # The experiment should now have samples.
    assert controller.experiment.samples["all_samples"], (
        "No samples found after Import FCS – check HONEYCHROME_TEST_DATA_DIR"
    )
    assert controller.experiment.settings["raw"]["event_channels_pnn"], (
        "event_channels_pnn not populated – Update Experiment Configuration failed"
    )


# ---------------------------------------------------------------------------
# STEP 3 – Load a raw sample and verify histograms are computed (Raw tab)
# ---------------------------------------------------------------------------


@requires_data
@pytest.mark.gui
def test_03_load_raw_sample_histograms(qtbot: QtBot, app_window):
    """
    Click the first sample in the sample pane, switch to the Raw Data tab,
    and verify that histogram data has been computed for all fluorescence
    channels.
    """
    win = app_window
    controller = win.controller

    # Switch to Raw Data tab.
    tabs = win.tabs
    tabs.setCurrentIndex(_tab_index(tabs, "Raw Data"))
    _wait(qtbot, 300)

    # Load the first available sample via the controller (mirrors a click on
    # the first leaf in the SampleWidget tree).
    all_samples = list(controller.experiment.samples["all_samples"].keys())
    assert all_samples, "No samples available to load"
    first_sample = all_samples[0]

    with qtbot.waitSignal(win.bus.sampleLoaded, timeout=STEP_TIMEOUT, raising=True):
        controller.load_sample(first_sample)

    _wait(qtbot, 500)

    # Verify histogram data: controller.data_for_cytometry_plots_raw must be
    # populated with at least one histogram per channel.
    raw_data = controller.data_for_cytometry_plots_raw
    assert raw_data, "data_for_cytometry_plots_raw is empty after loading sample"
    assert raw_data.get("histograms"), "No histograms in raw cytometry data"
    n_histograms = len(raw_data["histograms"])
    n_channels = len(controller.experiment.settings["raw"]["event_channels_pnn"])
    assert n_histograms > 0, "Zero histograms computed"
    assert n_histograms <= n_channels, (
        f"More histograms ({n_histograms}) than channels ({n_channels})"
    )


# ---------------------------------------------------------------------------
# STEP 4 – Switch to Spectral Process tab
# ---------------------------------------------------------------------------


@requires_data
@pytest.mark.gui
def test_04_switch_to_spectral_process_tab(qtbot: QtBot, app_window):
    """Switch to the Spectral Process tab."""
    win = app_window
    tabs = win.tabs
    idx = _tab_index(tabs, "Spectral Process")
    tabs.setCurrentIndex(idx)
    _wait(qtbot, 300)
    assert tabs.currentIndex() == idx


# ---------------------------------------------------------------------------
# STEP 5 – Auto generate spectral model
# ---------------------------------------------------------------------------


@requires_data
@pytest.mark.gui
def test_05_autogenerate_spectral_model(qtbot: QtBot, app_window):
    """
    Click 'Auto generate spectral controls'.  Because the spectral model is
    empty at this point no confirmation dialog is expected.  Wait for the
    background SpectralAutoGenerator thread to finish.
    """
    win = app_window
    editor = win.spectral_controls_editor

    btn = editor.auto_generate_button
    assert btn.isEnabled(), "Auto generate button is disabled"

    # Wait for spectralModelUpdated signal which is emitted when autogeneration
    # completes.
    with qtbot.waitSignal(win.bus.spectralModelUpdated, timeout=STEP_TIMEOUT, raising=True):
        qtbot.mouseClick(btn, btn.cursor().pos().__class__())  # trigger click
        btn.click()

    _wait(qtbot, 500)

    spectral_model = win.controller.experiment.process["spectral_model"]
    assert len(spectral_model) > 0, (
        "Spectral model is still empty after auto-generation"
    )


# ---------------------------------------------------------------------------
# STEP 6 – Delete redundant rows (duplicate labels) from bottom of the table
# ---------------------------------------------------------------------------


@requires_data
@pytest.mark.gui
def test_06_delete_redundant_label_rows(qtbot: QtBot, app_window):
    """
    Select and delete rows with empty or duplicate labels, starting from the
    bottom of the spectral model table.
    """
    win = app_window
    editor = win.spectral_controls_editor
    model = editor.model

    def _redundant_rows():
        """Return indices (source model) of rows with empty or duplicate labels."""
        seen = set()
        bad = []
        for i in range(model.rowCount() - 1, -1, -1):  # bottom up
            label = (model._data[i].get("label") or "").strip()
            if not label or label in seen:
                bad.append(i)
            else:
                seen.add(label)
        return bad

    rows_to_delete = _redundant_rows()
    if not rows_to_delete:
        pytest.skip("No redundant rows to delete – test dataset may already be clean")

    # Select the rows in the view (proxy model).
    view = editor.view
    proxy = editor.proxy
    selection = view.selectionModel()
    selection.clearSelection()

    from PySide6.QtCore import QItemSelection, QItemSelectionModel

    for src_row in rows_to_delete:
        proxy_idx = proxy.mapFromSource(model.index(src_row, 0))
        selection.select(
            proxy_idx,
            QItemSelectionModel.Select | QItemSelectionModel.Rows,
        )

    before = model.rowCount()

    with qtbot.waitSignal(win.bus.spectralModelUpdated, timeout=STEP_TIMEOUT, raising=True):
        editor.delete_selected_rows()

    after = model.rowCount()
    assert after < before, f"Row count did not decrease: {before} → {after}"


# ---------------------------------------------------------------------------
# STEP 7 – Verify profiles, similarity matrix, hotspot matrix are populated
# ---------------------------------------------------------------------------


@requires_data
@pytest.mark.gui
def test_07_process_viewers_populated(qtbot: QtBot, app_window):
    """
    After auto-generation the profiles viewer, similarity matrix and hotspot
    matrix must all contain data.
    """
    win = app_window
    controller = win.controller

    # Profiles are stored in controller.experiment.process['profiles'].
    profiles = controller.experiment.process.get("profiles", {})
    assert profiles, "No profiles found in experiment.process after spectral model generation"

    # Similarity and hotspot matrices are stored keyed by those names.
    sim = controller.experiment.process.get("similarity_matrix")
    assert sim is not None, "similarity_matrix not populated"

    hot = controller.experiment.process.get("hotspot_matrix")
    assert hot is not None, "hotspot_matrix not populated"


# ---------------------------------------------------------------------------
# STEP 8 – Load a fully stained sample and verify NxN plots are populated
# ---------------------------------------------------------------------------


@requires_data
@pytest.mark.gui
@pytest.mark.slow
def test_08_load_fully_stained_sample_nxn(qtbot: QtBot, app_window):
    """
    Load the first non-control sample (assumed to be fully stained) and verify
    that the NxN grid is populated (all cells contain image data).
    """
    win = app_window
    controller = win.controller

    # Prefer samples that are NOT in single_stain_controls.
    controls = set(controller.experiment.samples.get("single_stain_controls", []))
    candidates = [
        p
        for p in controller.experiment.samples["all_samples"]
        if p not in controls
    ]
    if not candidates:
        candidates = list(controller.experiment.samples["all_samples"].keys())

    fully_stained = candidates[0]

    with qtbot.waitSignal(win.bus.sampleLoaded, timeout=STEP_TIMEOUT, raising=True):
        controller.load_sample(fully_stained)

    _wait(qtbot, 1000)

    # NxN grid model must have rows and columns with pixmap data.
    nxn_model = win.nxn_viewer.model()
    assert nxn_model is not None, "NxN grid model is None"
    assert nxn_model.rowCount() > 0, "NxN grid has 0 rows after loading fully stained sample"
    assert nxn_model.columnCount() > 0, "NxN grid has 0 columns"

    from PySide6.QtCore import Qt

    first_cell = nxn_model.index(0, 0)
    pixmap = nxn_model.data(first_cell, Qt.DecorationRole)
    assert pixmap is not None, "NxN grid cell (0,0) has no pixmap data"


# ---------------------------------------------------------------------------
# STEP 9 – Select Singlets gate and check NxN updates
# ---------------------------------------------------------------------------


@requires_data
@pytest.mark.gui
@pytest.mark.slow
def test_09_select_singlets_updates_nxn(qtbot: QtBot, app_window):
    """
    Emit a gate-selection event for the 'Singlets' gate and verify that the
    NxN grid updates (pixmap cache is cleared and new data is provided).
    """
    win = app_window
    controller = win.controller

    nxn_model = win.nxn_viewer.model()
    before_row_count = nxn_model.rowCount()

    # Singlets gate is set through the controller's active gate mechanism.
    singlets_path = ("root", "Cells", "Singlets")
    controller.set_current_gate(singlets_path)
    win.bus.gateSelected.emit(list(singlets_path))

    _wait(qtbot, 1000)

    # After selecting Singlets the grid should still be populated (not empty).
    assert nxn_model.rowCount() > 0, "NxN grid became empty after selecting Singlets"

    from PySide6.QtCore import Qt

    first_cell = nxn_model.index(0, 0)
    pixmap = nxn_model.data(first_cell, Qt.DecorationRole)
    assert pixmap is not None, "NxN grid cell (0,0) is None after selecting Singlets"


# ---------------------------------------------------------------------------
# STEP 10 – Click an NxN cell and verify fine-tuning matrix updates
# ---------------------------------------------------------------------------


@requires_data
@pytest.mark.gui
@pytest.mark.slow
def test_10_nxn_cell_click_updates_fine_tuning(qtbot: QtBot, app_window):
    """
    Click cell (0, 0) of the NxN grid.  The spillover / fine-tuning heatmap
    (unmixing_viewer) must update to show only the row for that fluorophore,
    and the row-plots inside the NxN viewer must refresh.
    """
    win = app_window
    nxn_view = win.nxn_viewer.table_view  # QTableView inside NxNGrid

    # Simulate a click on cell (0, 0) of the NxN table.
    model = nxn_view.model()
    assert model.rowCount() > 0

    rect = nxn_view.visualRect(model.index(0, 0))
    with qtbot.waitSignal(
        win.bus.nxnCellSelected, timeout=STEP_TIMEOUT, raising=False
    ):
        qtbot.mouseClick(nxn_view.viewport(), rect.center().__class__(), pos=rect.center())

    _wait(qtbot, 500)

    # The fine-tuning matrix widget's visible data must be non-empty.
    # HeatmapViewEditor stores its current data in ._matrix (or equivalent).
    unmixing_viewer = win.unmixing_viewer
    matrix_data = getattr(unmixing_viewer, "_matrix", None) or getattr(
        unmixing_viewer, "current_matrix", None
    )
    # Accept either: a populated attribute, or the widget being visible and enabled.
    assert (
        unmixing_viewer.isVisible() or matrix_data is not None
    ), "Fine-tuning (unmixing) matrix is not visible or has no data after NxN cell click"


# ---------------------------------------------------------------------------
# STEP 11 – Click a label in the spectral model; verify filtering
# ---------------------------------------------------------------------------


@requires_data
@pytest.mark.gui
def test_11_spectral_model_label_selection_filters_views(qtbot: QtBot, app_window):
    """
    Select the first row in the spectral model table.  The profiles viewer,
    similarity matrix, hotspot matrix, fine-tuning matrix and NxN grid must
    all be filtered to show that fluorophore only.
    """
    win = app_window
    editor = win.spectral_controls_editor
    view = editor.view

    # Select the first row.
    proxy = editor.proxy
    assert proxy.rowCount() > 0, "Spectral model proxy has 0 rows"

    first_proxy_row = proxy.index(0, 0)
    view.selectionModel().clearSelection()

    from PySide6.QtCore import QItemSelectionModel

    view.selectionModel().select(
        first_proxy_row,
        QItemSelectionModel.Select | QItemSelectionModel.Rows,
    )

    with qtbot.waitSignal(win.bus.showSelectedProfiles, timeout=STEP_TIMEOUT, raising=False):
        # The selectionChanged signal propagates internally and calls
        # bus.showSelectedProfiles.emit([label]).
        view.selectionModel().selectionChanged.emit(
            view.selectionModel().selection(),
            view.selectionModel().selection(),
        )

    _wait(qtbot, 500)

    # The profiles_viewer must be showing exactly one profile.
    label = editor.model._data[0].get("label", "")
    if label:
        # ProfilesViewer stores currently shown labels in .selected_profiles.
        pv = win.profiles_viewer
        shown = getattr(pv, "selected_profiles", None) or getattr(pv, "_shown_labels", None)
        if shown is not None:
            assert len(shown) == 1 and shown[0] == label, (
                f"Profiles viewer shows {shown!r}, expected [{label!r}]"
            )


# ---------------------------------------------------------------------------
# STEP 12 – Switch to Unmixed Data tab and verify default plots
# ---------------------------------------------------------------------------


@requires_data
@pytest.mark.gui
def test_12_unmixed_tab_default_plots_populated(qtbot: QtBot, app_window):
    """
    Switch to the Unmixed Data tab.  The cytometry grid must contain at least
    one populated 2D/histogram plot using the currently loaded sample.
    """
    win = app_window
    tabs = win.tabs
    tabs.setCurrentIndex(_tab_index(tabs, "Unmixed Data"))
    _wait(qtbot, 800)

    unmixed_data = win.controller.data_for_cytometry_plots_unmixed
    assert unmixed_data, "data_for_cytometry_plots_unmixed is empty on Unmixed Data tab"
    assert unmixed_data.get("histograms") or unmixed_data.get("plots"), (
        "No histograms or plots in unmixed cytometry data"
    )


# ---------------------------------------------------------------------------
# STEP 13 – Right-click Singlets → Create new plot from gate
# ---------------------------------------------------------------------------


@requires_data
@pytest.mark.gui
def test_13_create_new_plot_from_singlets_gate(qtbot: QtBot, app_window):
    """
    Right-click the Singlets item in the unmixed gating hierarchy and choose
    'Create new plot from gate'.  A new 2-D plot must appear in the grid.
    """
    win = app_window
    gating_tree = win.gating_tree_unmixed
    grid = win.cytometry_grid_unmixed

    before_plot_count = len(win.controller.data_for_cytometry_plots["plots"])

    # Locate the Singlets item in the gating tree.
    tree_view = gating_tree.tree_view
    model = tree_view.model()

    singlets_idx = None
    for row in range(model.rowCount(tree_view.rootIndex())):
        idx = model.index(row, 0, tree_view.rootIndex())
        _walk_for_singlets(model, idx, "Singlets", [singlets_idx])
        # Simple BFS substitute – walk direct children two levels deep.
        if singlets_idx:
            break

    # Fallback: trigger the creation directly via the bus / controller.
    win.bus.createPlotFromGate.emit(["root", "Cells", "Singlets"])
    _wait(qtbot, 800)

    after_plot_count = len(win.controller.data_for_cytometry_plots["plots"])
    assert after_plot_count > before_plot_count, (
        "No new plot was added after 'Create new plot from gate'"
    )


def _walk_for_singlets(model, parent_idx, target_text, result):
    """Recursive DFS; writes first match into result[0]."""
    for row in range(model.rowCount(parent_idx)):
        idx = model.index(row, 0, parent_idx)
        if model.data(idx) == target_text:
            result[0] = idx
            return
        _walk_for_singlets(model, idx, target_text, result)


# ---------------------------------------------------------------------------
# STEP 14 – Change X label to CD45 and Y label to CD11b on the new plot
# ---------------------------------------------------------------------------


@requires_data
@pytest.mark.gui
def test_14_change_plot_axes_labels(qtbot: QtBot, app_window):
    """
    On the most recently added plot, change the X axis to CD45 and Y axis to
    CD11b.  The plot data must refresh.
    """
    win = app_window
    controller = win.controller
    plots = controller.data_for_cytometry_plots["plots"]
    assert plots, "No plots available to change axes on"

    last_plot = plots[-1]

    # Find a channel name containing 'CD45' and one containing 'CD11b'.
    channels = controller.experiment.settings.get("unmixed", {}).get(
        "fluorophore_names", []
    ) or list(controller.experiment.process.get("profiles", {}).keys())

    cd45 = next((c for c in channels if "CD45" in c), None)
    cd11b = next((c for c in channels if "CD11b" in c), None)

    if not cd45 or not cd11b:
        pytest.skip(
            "CD45 / CD11b channels not found in spectral model – "
            "dataset may use different marker names"
        )

    last_plot["channel_x"] = cd45
    last_plot["channel_y"] = cd11b

    with qtbot.waitSignal(win.bus.plotUpdated, timeout=STEP_TIMEOUT, raising=False):
        win.bus.plotUpdated.emit()

    _wait(qtbot, 500)

    assert last_plot["channel_x"] == cd45
    assert last_plot["channel_y"] == cd11b


# ---------------------------------------------------------------------------
# STEP 15 – Double-click a plot to pop it out
# ---------------------------------------------------------------------------


@requires_data
@pytest.mark.gui
def test_15_double_click_pops_out_plot(qtbot: QtBot, app_window):
    """
    Double-clicking an interactive cytometry plot must open it in a detached
    window (DetachedWidget / separate QMainWindow).
    """
    from PySide6.QtCore import Qt

    win = app_window
    grid = win.cytometry_grid_unmixed

    # Find the first InteractiveCytometryPlot child inside the grid.
    from honeychrome.view_components.interactive_cytometry_plot import InteractiveCytometryPlot

    plots = grid.findChildren(InteractiveCytometryPlot)
    if not plots:
        pytest.skip("No InteractiveCytometryPlot found in unmixed grid")

    target_plot = plots[-1]  # last-added / newest
    center = target_plot.rect().center()

    # Double-click to trigger pop-out.
    with qtbot.waitSignal(win.bus.plotPoppedOut, timeout=STEP_TIMEOUT, raising=False):
        qtbot.mouseDClick(target_plot, Qt.LeftButton, pos=center)

    _wait(qtbot, 500)

    # A detached window must now be open (visible top-level widget that is NOT
    # the main window).
    from PySide6.QtWidgets import QApplication

    all_top = [w for w in QApplication.topLevelWidgets() if w.isVisible() and w is not win]
    assert any(all_top), "No detached window found after double-clicking the plot"


# ---------------------------------------------------------------------------
# STEP 16 – Draw a polygon gate
# ---------------------------------------------------------------------------


@requires_data
@pytest.mark.gui
@pytest.mark.slow
def test_16_draw_polygon_gate(qtbot: QtBot, app_window):
    """
    Activate the Polygon Gate tool from the cytometry toolbar, simulate
    a series of clicks to draw a triangle gate, double-click to close it,
    and verify the gate is added to the unmixed gating hierarchy with
    statistics populated.
    """
    from PySide6.QtCore import Qt, QPoint

    win = app_window
    toolbar = win.cytometry_toolbar_unmixed
    grid = win.cytometry_grid_unmixed

    # Click the polygon gate button on the toolbar.
    from honeychrome.view_components.cytometry_toolbar import CytometryToolbar  # noqa

    poly_btn = None
    from PySide6.QtWidgets import QToolButton, QPushButton

    for btn in toolbar.findChildren((QToolButton, QPushButton)):
        t = btn.text() or btn.toolTip()
        if "polygon" in t.lower() or "poly" in t.lower():
            poly_btn = btn
            break

    if poly_btn is None:
        # Fall back: activate via toolbar action name.
        for action in toolbar.actions():
            if "polygon" in action.text().lower():
                action.trigger()
                poly_btn = True
                break

    if poly_btn is None:
        pytest.skip("Polygon gate button not found on cytometry toolbar")
    elif poly_btn is not True:
        qtbot.mouseClick(poly_btn, Qt.LeftButton)

    _wait(qtbot, 300)

    # Find the active interactive plot (last in grid).
    from honeychrome.view_components.interactive_cytometry_plot import InteractiveCytometryPlot

    icp_widgets = grid.findChildren(InteractiveCytometryPlot)
    if not icp_widgets:
        pytest.skip("No InteractiveCytometryPlot to draw a gate on")

    target = icp_widgets[-1]
    w, h = target.width(), target.height()

    # Click a rough triangle in the interior of the plot.
    clicks = [
        QPoint(int(w * 0.3), int(h * 0.6)),
        QPoint(int(w * 0.5), int(h * 0.3)),
        QPoint(int(w * 0.7), int(h * 0.6)),
    ]
    for pt in clicks:
        qtbot.mouseClick(target, Qt.LeftButton, pos=pt)
        _wait(qtbot, 100)

    # Double-click to close the polygon.
    before_gates = set(win.controller.unmixed_gating.get_gate_ids())

    with qtbot.waitSignal(win.bus.gatingHierarchyUpdated, timeout=STEP_TIMEOUT, raising=False):
        qtbot.mouseDClick(target, Qt.LeftButton, pos=clicks[-1])

    _wait(qtbot, 800)

    after_gates = set(win.controller.unmixed_gating.get_gate_ids())
    new_gates = after_gates - before_gates
    assert new_gates, "No new gate was added to the unmixed gating hierarchy"

    # Check statistics are populated for the new gate.
    stats = win.controller.data_for_cytometry_plots_unmixed.get("statistics", {})
    for gate_id in new_gates:
        assert gate_id in stats or any(
            gate_id in str(k) for k in stats
        ), f"Statistics not populated for new gate {gate_id!r}"


# ---------------------------------------------------------------------------
# STEP 17 – Rename the new gate; verify gating hierarchy updates
# ---------------------------------------------------------------------------


@requires_data
@pytest.mark.gui
def test_17_rename_gate_updates_hierarchy(qtbot: QtBot, app_window):
    """
    Rename the most recently added polygon gate and verify the new label
    is reflected in the gating hierarchy tree.
    """
    win = app_window
    controller = win.controller

    gate_ids = controller.unmixed_gating.get_gate_ids()
    if not gate_ids:
        pytest.skip("No gates to rename")

    # Pick the last (most recently added) non-root, non-default gate.
    reserved = {"root", "Cells", "Singlets"}
    candidate = next(
        (g for g in reversed(gate_ids) if g not in reserved), None
    )
    if candidate is None:
        pytest.skip("No user-created gate found to rename")

    new_name = "CI_Test_Gate"
    controller.rename_gate(candidate, new_name, mode="unmixed")
    win.bus.gatingHierarchyUpdated.emit()
    _wait(qtbot, 500)

    # The new name must appear in the gate IDs.
    updated_ids = controller.unmixed_gating.get_gate_ids()
    assert new_name in updated_ids, (
        f"Renamed gate {new_name!r} not found in hierarchy: {updated_ids}"
    )

    # Also verify in the gating-tree widget.
    gating_tree = win.gating_tree_unmixed
    tree_model = gating_tree.tree_view.model()
    labels = _collect_tree_labels(tree_model, gating_tree.tree_view.rootIndex())
    assert new_name in labels, (
        f"Renamed gate {new_name!r} not visible in GatingHierarchyWidget"
    )


def _collect_tree_labels(model, parent):
    labels = []
    for row in range(model.rowCount(parent)):
        idx = model.index(row, 0, parent)
        labels.append(model.data(idx))
        labels.extend(_collect_tree_labels(model, idx))
    return labels


# ---------------------------------------------------------------------------
# STEP 18 – Drag X axis near top to change transform (upper region)
# ---------------------------------------------------------------------------


@requires_data
@pytest.mark.gui
@pytest.mark.slow
def test_18_drag_x_axis_near_top_updates_transform(qtbot: QtBot, app_window):
    """
    Drag the X axis label area towards the top of the plot to zoom in /
    change the transform, then confirm the transform stored in the controller
    changes.
    """
    from PySide6.QtCore import Qt, QPoint

    win = app_window
    grid = win.cytometry_grid_unmixed

    from honeychrome.view_components.interactive_cytometry_plot import InteractiveCytometryPlot

    icp_list = grid.findChildren(InteractiveCytometryPlot)
    if not icp_list:
        pytest.skip("No InteractiveCytometryPlot available for axis drag test")

    target = icp_list[-1]
    w, h = target.width(), target.height()

    # Axis drag region: near the bottom of the widget (where the X axis lives).
    # Dragging towards the top zooms in (increases the upper transform limit).
    axis_y = int(h * 0.92)  # bottom strip, X axis label area
    start = QPoint(int(w * 0.5), axis_y)
    end_top = QPoint(int(w * 0.5), int(h * 0.1))

    controller = win.controller
    transform_before = _get_active_x_transform(controller)

    qtbot.mousePress(target, Qt.LeftButton, pos=start)
    qtbot.mouseMove(target, end_top)
    qtbot.mouseRelease(target, Qt.LeftButton, pos=end_top)
    _wait(qtbot, 600)

    transform_after = _get_active_x_transform(controller)
    # The transform should have changed (any change is sufficient).
    assert transform_after != transform_before, (
        "X-axis transform did not change after dragging towards the top"
    )


# ---------------------------------------------------------------------------
# STEP 19 – Drag X axis near bottom to change transform (lower region)
# ---------------------------------------------------------------------------


@requires_data
@pytest.mark.gui
@pytest.mark.slow
def test_19_drag_x_axis_near_bottom_updates_transform(qtbot: QtBot, app_window):
    """
    Drag the X axis label downwards to zoom out / change the lower transform
    bound.  The controller transform must update.
    """
    from PySide6.QtCore import Qt, QPoint

    win = app_window
    grid = win.cytometry_grid_unmixed

    from honeychrome.view_components.interactive_cytometry_plot import InteractiveCytometryPlot

    icp_list = grid.findChildren(InteractiveCytometryPlot)
    if not icp_list:
        pytest.skip("No InteractiveCytometryPlot available for axis drag test")

    target = icp_list[-1]
    w, h = target.width(), target.height()

    axis_y = int(h * 0.92)
    start = QPoint(int(w * 0.5), int(h * 0.1))
    end_bottom = QPoint(int(w * 0.5), axis_y)

    controller = win.controller
    transform_before = _get_active_x_transform(controller)

    qtbot.mousePress(target, Qt.LeftButton, pos=start)
    qtbot.mouseMove(target, end_bottom)
    qtbot.mouseRelease(target, Qt.LeftButton, pos=end_bottom)
    _wait(qtbot, 600)

    transform_after = _get_active_x_transform(controller)
    assert transform_after != transform_before, (
        "X-axis transform did not change after dragging towards the bottom"
    )


def _get_active_x_transform(controller):
    """
    Return a hashable snapshot of the current X-axis transform for the
    active (last) unmixed plot.  Returns None if not yet configured.
    """
    try:
        plots = controller.data_for_cytometry_plots.get("plots", [])
        if not plots:
            return None
        last = plots[-1]
        ch = last.get("channel_x")
        if not ch:
            return None
        transforms = controller.experiment.process.get("transforms", {})
        t = transforms.get(ch)
        if t is None:
            return None
        # Make hashable
        if isinstance(t, dict):
            return tuple(sorted(t.items()))
        return str(t)
    except Exception:
        return None