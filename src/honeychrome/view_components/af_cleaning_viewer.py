"""
af_cleaning_viewer.py
----------------------
Diagnostic widget for intrusive noise exclusion.

Shows a two-panel biplot for the selected control:
  Left  — Universal negative (unstained), showing where the noise boundary
          was defined in (noise channel, fluorophore peak channel) space.
  Right — Single-stained control, showing the same boundary applied and
          which events were excluded.

Mirrors the R gate.af.sample.plot() / gate.af.identify.plot() functions.
"""

from __future__ import annotations

import logging

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel,
    QSizePolicy, QSplitter, QVBoxLayout, QWidget,
)

from honeychrome.settings import heading_style
from honeychrome.view_components.help_toggle_widget import WheelBlocker

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Minimal square scatter sub-widget  (same pattern as scatter_cleaning_viewer)
# ---------------------------------------------------------------------------

class _SquarePlotWidget(pg.GraphicsLayoutWidget):
    def __init__(self, ch_x: str = 'AF ch', ch_y: str = 'Peak ch', parent=None):
        super().__init__(parent)
        self.setBackground(None)
        self._ch_x = ch_x
        self._ch_y = ch_y
        self.vb = pg.ViewBox(lockAspect=False)
        self.vb.setMouseEnabled(x=False, y=False)
        self._plot = self.addPlot(viewBox=self.vb)
        self._plot.setLabel('bottom', ch_x)
        self._plot.setLabel('left', ch_y)
        self._plot.showGrid(x=True, y=True, alpha=0.15)

    def set_channel_labels(self, ch_x: str, ch_y: str):
        self._ch_x = ch_x
        self._ch_y = ch_y
        self._plot.setLabel('bottom', ch_x)
        self._plot.setLabel('left', ch_y)

    def clear_vb(self):
        self.vb.clear()

    def add_item(self, item):
        self.vb.addItem(item)

    def auto_range(self):
        self.vb.autoRange()


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class AfCleaningViewer(QFrame):
    # Colour scheme
    _COL_AF_DIM      = (150, 150, 200,  60)   # dim blue — low noise negative events
    _COL_AF_BRIGHT   = (255,  80,  80, 180)   # red      — high noise negative events
    _COL_ALL_POS     = (180, 180, 180,  50)   # grey     — all positive events
    _COL_KEPT_POS    = ( 80, 200,  80, 200)   # green    — noise-excluded (clean) positives
    _COL_REMOVED_POS = (255,  80,  80, 200)   # red      — excluded noise from positives
    _COL_BOUNDARY    = 'y'                    # yellow   — exclusion boundary

    _LEGEND = [
        (_COL_AF_DIM,      'Low-noise negative events'),
        (_COL_AF_BRIGHT,   'High-noise negative events'),
        (_COL_ALL_POS,     'All positive events'),
        (_COL_KEPT_POS,    'Noise-excluded positives (kept)'),
        (_COL_REMOVED_POS, 'Noise-contaminated positives (removed)'),
    ]

    def __init__(self, bus, controller, parent=None):
        super().__init__(parent)
        self.bus = bus
        self.controller = controller

        if self.bus:
            self.bus.spectralModelUpdated.connect(self._on_model_updated)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)

        title = QLabel('Noise Exclusion Diagnostics')
        title.setStyleSheet(heading_style)
        outer.addWidget(title)

        self._toggle = QCheckBox('Show noise exclusion plots')
        self._toggle.setChecked(False)
        self._toggle.setEnabled(False)
        self._toggle.setToolTip(
            'Tick "Exclude noise" in Clean Controls options and run Clean Controls first.')
        outer.addWidget(self._toggle)

        self._content = QWidget()
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 4, 0, 0)
        content_layout.setSpacing(6)

        # Control selector row
        ctrl_row = QHBoxLayout()
        ctrl_row.addWidget(QLabel('Control:'))
        self._combo = QComboBox()
        self._combo.setMinimumWidth(220)
        self._combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        ctrl_row.addWidget(self._combo)
        ctrl_row.addStretch()
        self._status = QLabel('')
        ctrl_row.addWidget(self._status)
        content_layout.addLayout(ctrl_row)

        # Legend row
        legend_row = QHBoxLayout()
        for color, text in self._LEGEND:
            r, g, b, _ = color
            swatch = QLabel('■')
            swatch.setStyleSheet(f'color: rgb({r},{g},{b});')
            legend_row.addWidget(swatch)
            legend_row.addWidget(QLabel(text))
            legend_row.addSpacing(10)
        bnd_swatch = QLabel('—')
        bnd_swatch.setStyleSheet('color: yellow;')
        legend_row.addWidget(bnd_swatch)
        legend_row.addWidget(QLabel('Noise exclusion boundary'))
        legend_row.addStretch()
        content_layout.addLayout(legend_row)

        # Plot pair
        left_box = QVBoxLayout()
        left_box.setSpacing(2)
        self._neg_title = QLabel('Unstained — Noise boundary definition')
        self._neg_title.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self._neg_title.setStyleSheet('font-weight: bold; padding: 2px;')
        self._neg_title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        left_box.addWidget(self._neg_title)
        self._neg_plot = _SquarePlotWidget()
        self._neg_plot.setMinimumSize(320, 320)
        self._neg_plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._neg_wheel_blocker = WheelBlocker(self)
        self._neg_plot.viewport().installEventFilter(self._neg_wheel_blocker)
        left_box.addWidget(self._neg_plot)
        left_w = QWidget(); left_w.setLayout(left_box)
        left_w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        right_box = QVBoxLayout()
        right_box.setSpacing(2)
        self._pos_title = QLabel('Single-Stained Control — Noise exclusion applied')
        self._pos_title.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self._pos_title.setStyleSheet('font-weight: bold; padding: 2px;')
        self._pos_title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        right_box.addWidget(self._pos_title)
        self._pos_plot = _SquarePlotWidget()
        self._pos_plot.setMinimumSize(320, 320)
        self._pos_plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._pos_wheel_blocker = WheelBlocker(self)
        self._pos_plot.viewport().installEventFilter(self._pos_wheel_blocker)
        right_box.addWidget(self._pos_plot)
        right_w = QWidget(); right_w.setLayout(right_box)
        right_w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_w)
        splitter.addWidget(right_w)
        splitter.setSizes([500, 500])
        content_layout.addWidget(splitter)

        self._content.setVisible(False)
        outer.addWidget(self._content)

        self._toggle.toggled.connect(self._content.setVisible)
        self._toggle.toggled.connect(self._on_toggle)
        self._combo.currentTextChanged.connect(self._refresh_plots)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def refresh_combo(self):
        cleaned = self.controller.cleaned_events
        spectral_model = self.controller.experiment.process.get('spectral_model', [])
        # Only show controls that actually had noise exclusion run (af_ch_idx is set),
        # ordered as they appear in the spectral model.
        model_order = [c['label'] for c in spectral_model if 'label' in c]
        labels = [
            label for label in model_order
            if label in cleaned and cleaned[label].get('af_ch_idx') is not None
        ]
        current = self._combo.currentText()
        self._combo.blockSignals(True)
        self._combo.clear()
        self._combo.addItems(labels)
        if current in labels:
            self._combo.setCurrentText(current)
        self._combo.blockSignals(False)
        has_data = bool(labels)
        self._toggle.setEnabled(has_data)
        self._toggle.setToolTip(
            'Show Noise exclusion biplots for the selected control.'
            if has_data else
            'Enable "Exclude noise" in Clean Controls options and run Clean Controls first.'
        )

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot()
    def _on_model_updated(self):
        self.refresh_combo()
        if self._toggle.isChecked():
            self._refresh_plots()

    @Slot(bool)
    def _on_toggle(self, checked: bool):
        if checked:
            self.refresh_combo()
            self._refresh_plots()

    @Slot(str)
    def _refresh_plots(self, _=''):
        if not self._toggle.isChecked():
            return
        label = self._combo.currentText()
        if not label:
            self._neg_plot.clear_vb()
            self._pos_plot.clear_vb()
            self._status.setText('')
            return
        self._draw(label)

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    @staticmethod
    def _pts(x, y, rgba, size=2) -> pg.ScatterPlotItem:
        r, g, b, a = rgba
        return pg.ScatterPlotItem(
            x=x.astype(float), y=y.astype(float),
            size=size, pen=None,
            brush=pg.mkBrush(r, g, b, a),
        )

    def _draw(self, label: str):
        self._neg_plot.clear_vb()
        self._pos_plot.clear_vb()

        cleaned_store = self.controller.cleaned_events
        cleaned = cleaned_store.get(label)
        if cleaned is None:
            self._status.setText('No cleaned data for this control.')
            return

        af_ch_idx   = cleaned.get('af_ch_idx')
        peak_ch_idx = cleaned.get('af_peak_ch_idx')
        boundary    = cleaned.get('af_boundary_neg')

        if af_ch_idx is None or peak_ch_idx is None:
            self._status.setText('Noise exclusion was not performed for this control.')
            return

        # Resolve channel names for axis labels
        fluor_pnn = self.controller.experiment.settings['raw']['event_channels_pnn']
        fluor_ch_ids = self.controller.filtered_raw_fluorescence_channel_ids
        try:
            af_ch_name   = fluor_pnn[fluor_ch_ids[af_ch_idx]]
            peak_ch_name = fluor_pnn[fluor_ch_ids[peak_ch_idx]]
        except (IndexError, KeyError):
            af_ch_name   = f'Ch {af_ch_idx}'
            peak_ch_name = f'Ch {peak_ch_idx}'

        spectral_model = self.controller.experiment.process.get('spectral_model', [])
        control = next((c for c in spectral_model if c.get('label') == label), None)
        neg_name = control.get('universal_negative_name', '—') if control else '—'
        sample_name = control.get('sample_name', '—') if control else '—'

        self._neg_title.setText(f'Unstained — Noise exclusion boundary {neg_name}')
        self._pos_title.setText(f'{label} — {sample_name}')
        self._neg_plot.set_channel_labels(af_ch_name, peak_ch_name)
        self._pos_plot.set_channel_labels(af_ch_name, peak_ch_name)

        # ---- LEFT PLOT: negative events coloured by AF-bright/dim split ----
        neg_events = cleaned.get('negative')
        if neg_events is not None and len(neg_events) > 0:
            neg_2d = neg_events[:, [af_ch_idx, peak_ch_idx]].astype(float)

            # Reconstruct bright/dim split using the boundary polygon
            if boundary is not None and len(boundary) >= 3:
                from matplotlib.path import Path
                inside_neg = Path(boundary).contains_points(neg_2d)
            else:
                # Fallback: label top 2% as bright
                x_vals = neg_2d[:, 0]
                inside_neg = x_vals > np.quantile(x_vals, 0.98)

            dim_pts   = neg_2d[~inside_neg]
            bright_pts = neg_2d[inside_neg]

            if len(dim_pts) > 0:
                self._neg_plot.add_item(
                    self._pts(dim_pts[:, 0], dim_pts[:, 1], self._COL_AF_DIM))
            if len(bright_pts) > 0:
                self._neg_plot.add_item(
                    self._pts(bright_pts[:, 0], bright_pts[:, 1], self._COL_AF_BRIGHT))

        # ---- RIGHT PLOT: positive events coloured kept/removed ----
        pos_events = cleaned.get('positive')
        # We need the pre-noise exclusion positive to show removed events too.
        # The cleaned['positive'] is already post-removal; we load raw gated events
        # to show all events in grey, then overlay the surviving cleaned ones.
        all_pos_2d = None
        try:
            from honeychrome.controller_components.functions import sample_from_fcs
            from honeychrome.controller_components.spectral_functions import get_raw_events
            if control:
                exp_dir = self.controller.experiment_dir
                all_samples = self.controller.experiment.samples.get('all_samples', {})
                all_samples_rev = {v: k for k, v in all_samples.items()}
                rel = all_samples_rev.get(control.get('sample_name', ''))
                if rel:
                    samp = sample_from_fcs(str(exp_dir / rel))
                    fluor_ch_ids_list = self.controller.filtered_raw_fluorescence_channel_ids
                    raw_pos, _ = get_raw_events(
                        samp, fluor_ch_ids_list,
                        gate_label=control.get('gate_label'),
                        gating_strategy=self.controller.raw_gating,
                        extra_channel_ids=self.controller.experiment.settings['raw']['scatter_channel_ids'],
                    )
                    all_pos_2d = raw_pos[:, [af_ch_idx, peak_ch_idx]].astype(float)
        except Exception as exc:
            logger.debug(f'AfCleaningViewer: could not load raw positive events: {exc}')

        if all_pos_2d is not None and len(all_pos_2d) > 0:
            self._pos_plot.add_item(
                self._pts(all_pos_2d[:, 0], all_pos_2d[:, 1], self._COL_ALL_POS, size=2))

        if pos_events is not None and len(pos_events) > 0:
            kept_2d = pos_events[:, [af_ch_idx, peak_ch_idx]].astype(float)
            self._pos_plot.add_item(
                self._pts(kept_2d[:, 0], kept_2d[:, 1], self._COL_KEPT_POS, size=2))

            # Show removed events (in raw but not in cleaned)
            if all_pos_2d is not None and boundary is not None:
                from matplotlib.path import Path
                removed_mask = Path(boundary).contains_points(all_pos_2d)
                removed_2d = all_pos_2d[removed_mask]
                if len(removed_2d) > 0:
                    self._pos_plot.add_item(
                        self._pts(removed_2d[:, 0], removed_2d[:, 1],
                                  self._COL_REMOVED_POS, size=3))

        # ---- Boundary polygon on both plots ----
        if boundary is not None and len(boundary) >= 3:
            closed = np.vstack([boundary, boundary[0]])   # close the polygon
            bnd_curve = pg.PlotDataItem(
                x=closed[:, 0].astype(float),
                y=closed[:, 1].astype(float),
                pen=pg.mkPen(self._COL_BOUNDARY, width=1.5, style=Qt.DashLine),
            )
            bnd_curve2 = pg.PlotDataItem(
                x=closed[:, 0].astype(float),
                y=closed[:, 1].astype(float),
                pen=pg.mkPen(self._COL_BOUNDARY, width=1.5, style=Qt.DashLine),
            )
            self._neg_plot.add_item(bnd_curve)
            self._pos_plot.add_item(bnd_curve2)

        self._neg_plot.auto_range()
        self._pos_plot.auto_range()

        n_rem = cleaned.get('n_removed_af', 0)
        n_surv = cleaned.get('n_surviving_positive', len(pos_events) if pos_events is not None else 0)
        self._status.setText(f'{n_rem} events removed by noise filter · {n_surv} positive events surviving')