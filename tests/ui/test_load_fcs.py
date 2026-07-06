"""A simple UI test using pytest-qt: load an FCS file through the GUI signal flow.

This exercises the real ``View`` -> ``EventBus`` -> ``Controller`` wiring that
``honeychrome.main.main`` sets up, but without any instrument, shared memory or
background processes. It uses the bundled example FCS file (the same one the
dummy acquisition uses), whose channels match a default experiment exactly.

Run just this test with:

    pytest tests/ui/test_load_fcs.py -v
"""
import os
import shutil
from pathlib import Path

import pytest

import honeychrome
from honeychrome.controller import Controller
from honeychrome.view import View

# When True (env HONEYCHROME_SHOW_UI=1), the test builds and shows the real main
# window and pauses at the end so you can look at / interact with the GUI.
SHOW_UI = os.environ.get("HONEYCHROME_SHOW_UI", "").lower() in ("1", "true", "yes", "on")

# The example FCS shipped inside the package (2300 events).
EXAMPLE_FCS = (
    Path(honeychrome.__file__).parent
    / "instrument_driver_components"
    / "data"
    / "example_for_dummy_acquisition.fcs"
)


@pytest.fixture
def wired_app(qtbot, tmp_path):
    """Build a real Controller + View wired through the EventBus.

    The controller is backed by a fresh, empty experiment created on disk under
    pytest's ``tmp_path``, so the test never touches the user's real data.
    ``qtbot`` (from pytest-qt) provides the QApplication.
    """
    controller = Controller()  # no shared memory / instrument needed
    controller.new_experiment(tmp_path / "ui_test_experiment")

    view = View(controller=controller)
    controller.bus = view.bus  # exactly what main.main() does after building the View
    qtbot.addWidget(view.splash)  # register a Qt widget so qtbot cleans it up

    return controller, view


def test_load_fcs_via_ui_signal(wired_app, qtbot):
    controller, view = wired_app

    # Place the example FCS file into the experiment's "Raw" folder, where the
    # app looks for raw samples. The path is relative to the experiment dir.
    sample_rel_path = "Raw/example.fcs"
    destination = controller.experiment_dir / sample_rel_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(EXAMPLE_FCS, destination)

    # Optionally build and show the real main window so there is a full GUI to
    # look at (only when HONEYCHROME_SHOW_UI=1; otherwise we stay head-less).
    if SHOW_UI:
        view.load_main_window_with_experiment_and_template(
            controller.experiment.experiment_path
        )
        qtbot.addWidget(view.main_window)
        view.main_window.show()
        qtbot.waitExposed(view.main_window)

    # Act: emit the exact signal the sample panel fires when the user loads a
    # sample, and wait until the controller reports it finished loading.
    with qtbot.waitSignal(
        view.bus.statusMessage,
        timeout=5000,
        check_params_cb=lambda message: "Loaded sample" in message,
    ):
        view.bus.loadSampleRequested.emit(sample_rel_path)

    # Assert: the controller now holds the loaded flowkit Sample and its data.
    assert controller.current_sample is not None
    assert controller.current_sample_path == sample_rel_path
    assert controller.current_sample.event_count == 2300
    assert controller.raw_event_data is not None
    assert controller.raw_event_data.shape[0] == 2300

    # Pause with the GUI on screen so you can inspect it. Close the window (or
    # press the qtbot "Continue" button) to let the test finish.
    if SHOW_UI:
        qtbot.stop()
