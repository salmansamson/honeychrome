"""
scatter_cleaning_viewer.py
---------------------------
Diagnostic widget for Stage 3 scatter matching.
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

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _root_scatter_channels(controller) -> tuple[str, str]:
    """
    Return (channel_x, channel_y) for the scatter biplot from the first
    hist2d at source_gate='root' that has one FSC and one SSC channel.
    Falls back to the first root hist2d regardless, then to ('FSC-A','SSC-A').
    """
    raw_plots = controller.experiment.cytometry.get('raw_plots') or []
    first_root_hist2d = None
    for plot in raw_plots:
        if plot.get('type') == 'hist2d' and plot.get('source_gate') == 'root':
            cx = plot.get('channel_x', '')
            cy = plot.get('channel_y', '')
            has_fsc = 'FSC' in cx.upper() or 'FSC' in cy.upper()
            has_ssc = 'SSC' in cx.upper() or 'SSC' in cy.upper()
            if has_fsc and has_ssc:
                return cx, cy
            if first_root_hist2d is None:
                first_root_hist2d = (cx, cy)
    return first_root_hist2d or ('FSC-A', 'SSC-A')


def _scatter_col_indices(controller, ch_x: str, ch_y: str) -> tuple[int | None, int | None]:
    """
    Return the column indices of ch_x and ch_y within the scatter sub-array
    that SpectralCleaner stores (shape (n, n_scatter_ch), ordered by
    settings.scatter_channel_ids).

    If the channels are not among the scatter channels, return (None, None).
    """
    pnn = controller.experiment.settings['raw']['event_channels_pnn']
    sc_ids = controller.experiment.settings['raw']['scatter_channel_ids']
    # sc_ids is a list of absolute column indices into the full event array.
    # We need: position of ch_x / ch_y within sc_ids.
    try:
        abs_x = pnn.index(ch_x)
        abs_y = pnn.index(ch_y)
        col_x = sc_ids.index(abs_x)
        col_y = sc_ids.index(abs_y)
        return col_x, col_y
    except ValueError:
        return None, None


def _event_col_indices(controller, ch_x: str, ch_y: str) -> tuple[int | None, int | None]:
    """Absolute column indices into the raw event array for ch_x and ch_y."""
    pnn = controller.experiment.settings['raw']['event_channels_pnn']
    try:
        return pnn.index(ch_x), pnn.index(ch_y)
    except ValueError:
        return None, None


# ---------------------------------------------------------------------------
# Square scatter plot (GraphicsLayoutWidget with labelled axes)
# ---------------------------------------------------------------------------

class _SquareScatterWidget(pg.GraphicsLayoutWidget):
    """
    Square plot with bottom and left AxisItems and a ViewBox.
    Enforces square aspect via resizeEvent.
    """

    def __init__(self, label_x: str = 'X', label_y: str = 'Y', parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._axis_left   = pg.AxisItem('left')
        self._axis_bottom = pg.AxisItem('bottom')
        self.vb = pg.ViewBox()
        self.vb.setAspectLocked(True)
        self.vb.setMenuEnabled(False)
        self.vb.setMouseEnabled(x=False, y=False)

        self.addItem(self._axis_left,   row=0, col=0)
        self.addItem(self.vb,           row=0, col=1)
        self.addItem(self._axis_bottom, row=1, col=1)

        self._axis_left.linkToView(self.vb)
        self._axis_bottom.linkToView(self.vb)

        self._axis_bottom.setLabel(label_x)
        self._axis_left.setLabel(label_y)

    def set_channel_labels(self, label_x: str, label_y: str):
        self._axis_bottom.setLabel(label_x)
        self._axis_left.setLabel(label_y)

    def clear_vb(self):
        self.vb.clear()

    def add_item(self, item):
        self.vb.addItem(item)

    def auto_range(self):
        self.vb.autoRange()

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def wheelEvent(self, event):
        event.ignore()


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class ScatterCleaningViewer(QFrame):
    # Consistent colour scheme — same constants used for legend
    _COL_ALL_NEG   = (150, 150, 200,  50)   # dim blue-grey  — all negative events
    _COL_MATCHED   = ( 80, 160, 255, 200)   # bright blue    — scatter-matched negative
    _COL_ALL_POS   = (180, 180, 180,  50)   # dim grey       — all positive events
    _COL_GATED_POS = (255, 120,  50, 170)   # orange         — gated positive
    _COL_CLEAN_POS = (160,  50, 220, 230)   # purple         — cleaned & selected positive
    _COL_HULL      = 'y'                    # yellow dashed  — convex hull

    _LEGEND = [
        (_COL_ALL_NEG,   'All negative events'),
        (_COL_MATCHED,   'Scatter-matched negative'),
        (_COL_ALL_POS,   'All positive events'),
        (_COL_GATED_POS, 'Gated positive'),
        (_COL_CLEAN_POS, 'Cleaned & selected positive'),
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

        title = QLabel('Scatter-matching Diagnostics')
        title.setStyleSheet(heading_style)
        outer.addWidget(title)

        self._toggle = QCheckBox('Show scatter-matching plots')
        self._toggle.setChecked(False)
        self._toggle.setEnabled(False)
        self._toggle.setToolTip('Run "Clean Controls" first to populate this panel.')
        outer.addWidget(self._toggle)

        self._content = QWidget()
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 4, 0, 0)
        content_layout.setSpacing(6)

        # Control selector
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

        # Legend
        legend_row = QHBoxLayout()
        for color, text in self._LEGEND:
            r, g, b, _ = color
            swatch = QLabel('■')
            swatch.setStyleSheet(f'color: rgb({r},{g},{b});')
            legend_row.addWidget(swatch)
            legend_row.addWidget(QLabel(text))
            legend_row.addSpacing(10)
        hull_swatch = QLabel('—')
        hull_swatch.setStyleSheet('color: yellow;')
        legend_row.addWidget(hull_swatch)
        legend_row.addWidget(QLabel('Match boundary (exact hull)'))
        legend_row.addStretch()
        content_layout.addLayout(legend_row)

        # Plot pair
        plot_row = QHBoxLayout()
        plot_row.setSpacing(8)

        left_box = QVBoxLayout()
        left_box.setSpacing(2)
        self._neg_title = QLabel('Universal Negative')
        self._neg_title.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self._neg_title.setStyleSheet('font-weight: bold; padding: 2px;')
        self._neg_title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        left_box.addWidget(self._neg_title)
        self._neg_plot = _SquareScatterWidget('FSC-A', 'SSC-A')
        self._neg_plot.setMinimumSize(320, 320)
        self._neg_plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        left_box.addWidget(self._neg_plot)
        left_w = QWidget(); left_w.setLayout(left_box)
        left_w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        right_box = QVBoxLayout()
        right_box.setSpacing(2)
        self._pos_title = QLabel('Single-Stained Control')
        self._pos_title.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self._pos_title.setStyleSheet('font-weight: bold; padding: 2px;')
        self._pos_title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        right_box.addWidget(self._pos_title)
        self._pos_plot = _SquareScatterWidget('FSC-A', 'SSC-A')
        self._pos_plot.setMinimumSize(320, 320)
        self._pos_plot.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
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
        cleaned = self.controller.experiment.process.get('cleaned_events', {})
        spectral_model = self.controller.experiment.process.get('spectral_model', [])
        # Only include controls that actually underwent scatter matching,
        # ordered as they appear in the spectral model.
        model_order = [c['label'] for c in spectral_model if 'label' in c]
        labels = [
            label for label in model_order
            if label in cleaned and cleaned[label].get('n_scatter_matched', 0) > 0
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
            'Show FSC/SSC biplots for the selected control and its universal negative.'
            if has_data else
            'Run "Clean Controls" first to populate this panel.'
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
        from honeychrome.controller_components.functions import sample_from_fcs

        self._neg_plot.clear_vb()
        self._pos_plot.clear_vb()

        cleaned_store = self.controller.experiment.process.get('cleaned_events', {})
        cleaned = cleaned_store.get(label)
        if cleaned is None:
            self._status.setText('No cleaned data for this control.')
            return

        spectral_model = self.controller.experiment.process.get('spectral_model', [])
        control = next((c for c in spectral_model if c.get('label') == label), None)
        if control is None:
            self._status.setText('Control not found in spectral model.')
            return

        experiment_dir  = self.controller.experiment_dir
        all_samples     = self.controller.experiment.samples.get('all_samples', {})
        all_samples_rev = {v: k for k, v in all_samples.items()}
        raw_gating      = self.controller.raw_gating

        # Scatter channel names from the root FSC/SSC plot
        ch_x, ch_y = _root_scatter_channels(self.controller)
        abs_x, abs_y = _event_col_indices(self.controller, ch_x, ch_y)
        if abs_x is None:
            self._status.setText(f'Channels {ch_x}/{ch_y} not found in event data.')
            return

        # scatter_pos / scatter_neg are stored as 2-column (FSC-A, SSC-A) arrays
        # by _clean_one — columns 0 and 1 are always the correct indices.

        # Update axis labels on both plots
        self._neg_plot.set_channel_labels(ch_x, ch_y)
        self._pos_plot.set_channel_labels(ch_x, ch_y)
        self._neg_title.setText(
            f'Universal Negative — {control.get("universal_negative_name", "—")}')
        self._pos_title.setText(
            f'{label} — {control.get("sample_name", "—")}')

        # ---- Positive: load all events + gated subset ----
        pos_scatter_all = None
        pos_scatter_gated = None
        pos_rel = all_samples_rev.get(control.get('sample_name', ''))
        if pos_rel:
            try:
                pos_sample = sample_from_fcs(str(experiment_dir / pos_rel))
                all_ev = pos_sample.get_events('raw')
                pos_scatter_all = all_ev[:, [abs_x, abs_y]].astype(float)
                gate_label = control.get('gate_label')
                if gate_label and raw_gating.find_matching_gate_paths(gate_label):
                    mask = raw_gating.gate_sample(
                        pos_sample).get_gate_membership(gate_label)
                    pos_scatter_gated = all_ev[mask][:, [abs_x, abs_y]].astype(float)
            except Exception as exc:
                logger.warning(f'ScatterCleaningViewer: pos load failed for "{label}": {exc}')

        # Cleaned & selected positive from stored scatter_pos
        pos_scatter_clean = None
        stored_scatter_pos = cleaned.get('scatter_pos')
        if (stored_scatter_pos is not None
                and hasattr(stored_scatter_pos, 'ndim')
                and stored_scatter_pos.ndim == 2
                and stored_scatter_pos.shape[1] >= 2
                and stored_scatter_pos.shape[0] > 0):
            pos_scatter_clean = stored_scatter_pos[:, :2].astype(float)

        # ---- Negative: load ALL ungated events as background ----
        neg_name = control.get('universal_negative_name', '')
        neg_scatter_all = None
        neg_scatter_matched = None

        # Stored scatter_neg (already scatter-matched subset)
        stored_scatter_neg = cleaned.get('scatter_neg')
        if (stored_scatter_neg is not None
                and hasattr(stored_scatter_neg, 'ndim')
                and stored_scatter_neg.ndim == 2
                and stored_scatter_neg.shape[1] >= 2
                and stored_scatter_neg.shape[0] > 0):
            neg_scatter_matched = stored_scatter_neg[:, :2].astype(float)

        # Only load and display the external negative background if scatter matching
        # actually took place (i.e. n_scatter_matched > 0). For internal-negative
        # and bead controls the universal_negative_name may still be populated but
        # is irrelevant — do not display it.
        if neg_name and cleaned.get('n_scatter_matched', 0) > 0:
            neg_rel = all_samples_rev.get(neg_name)
            if neg_rel:
                try:
                    neg_sample = sample_from_fcs(str(experiment_dir / neg_rel))
                    # ALL events — no gate — so there's no artificial y-axis cutoff
                    all_neg_ev = neg_sample.get_events('raw')
                    neg_scatter_all = all_neg_ev[:, [abs_x, abs_y]].astype(float)
                except Exception as exc:
                    logger.warning(
                        f'ScatterCleaningViewer: neg load failed for "{label}": {exc}')

        # ---- Draw negative plot ----
        if neg_scatter_all is not None and len(neg_scatter_all):
            self._neg_plot.add_item(self._pts(
                neg_scatter_all[:, 0], neg_scatter_all[:, 1],
                self._COL_ALL_NEG, size=2))

        if neg_scatter_matched is not None and len(neg_scatter_matched):
            self._neg_plot.add_item(self._pts(
                neg_scatter_matched[:, 0], neg_scatter_matched[:, 1],
                self._COL_MATCHED, size=3))

        # Hull on negative plot: use the stored hull_vertices (exact boundary used
        # by scatter_match_negative). Fall back to recomputing a smooth hull if no
        # stored hull exists (e.g. data cleaned before hull storage was added).
        stored_hull = cleaned.get('hull_vertices')
        if stored_hull is not None and len(stored_hull) >= 3:
            closed = np.vstack([stored_hull, stored_hull[0]])
            self._neg_plot.add_item(pg.PlotCurveItem(
                closed[:, 0], closed[:, 1],
                pen=pg.mkPen(self._COL_HULL, width=2),
            ))
        else:
            hull_src = (pos_scatter_clean if (pos_scatter_clean is not None and len(pos_scatter_clean) >= 4)
                        else (pos_scatter_gated if (pos_scatter_gated is not None and len(pos_scatter_gated) >= 4)
                              else None))
            if hull_src is not None:
                hull_pts = self._smooth_hull(hull_src)
                if hull_pts is not None and len(hull_pts) >= 3:
                    closed = np.vstack([hull_pts, hull_pts[0]])
                    self._neg_plot.add_item(pg.PlotCurveItem(
                        closed[:, 0], closed[:, 1],
                        pen=pg.mkPen(self._COL_HULL, width=2, style=Qt.DashLine),
                    ))

        self._neg_plot.auto_range()

        # ---- Draw positive plot ----
        if pos_scatter_all is not None and len(pos_scatter_all):
            self._pos_plot.add_item(self._pts(
                pos_scatter_all[:, 0], pos_scatter_all[:, 1],
                self._COL_ALL_POS, size=2))

        if pos_scatter_gated is not None and len(pos_scatter_gated):
            self._pos_plot.add_item(self._pts(
                pos_scatter_gated[:, 0], pos_scatter_gated[:, 1],
                self._COL_GATED_POS, size=3))

        if pos_scatter_clean is not None and len(pos_scatter_clean):
            self._pos_plot.add_item(self._pts(
                pos_scatter_clean[:, 0], pos_scatter_clean[:, 1],
                self._COL_CLEAN_POS, size=4))

        self._pos_plot.auto_range()

        n_matched  = cleaned.get('n_scatter_matched', '?')
        n_pos      = cleaned.get('n_surviving_positive', '?')
        n_gated    = len(pos_scatter_gated) if pos_scatter_gated is not None else '?'
        self._status.setText(
            f'Axes: {ch_x} / {ch_y}  ·  '
            f'{n_pos} brightest-selected positive (of {n_gated} gated)  ·  '
            f'{n_matched} scatter-matched negative'
        )

    # ------------------------------------------------------------------
    # Hull helper
    # ------------------------------------------------------------------

    @staticmethod
    def _smooth_hull(pts: np.ndarray, n: int = 120) -> np.ndarray | None:
        """KDE-core convex hull interpolated to n points for smooth rendering."""
        try:
            from scipy.stats import gaussian_kde
            from scipy.spatial import ConvexHull
            from scipy.interpolate import interp1d

            kde = gaussian_kde(pts.T, bw_method='scott')
            dens = kde(pts.T)
            core = pts[dens >= np.quantile(dens, 0.50)]
            if len(core) < 4:
                core = pts

            hull  = ConvexHull(core)
            verts = core[hull.vertices]
            vc    = np.vstack([verts, verts[0]])
            diffs = np.diff(vc, axis=0)
            arc   = np.concatenate([[0], np.cumsum(np.hypot(diffs[:, 0], diffs[:, 1]))])
            total = arc[-1]
            if total == 0:
                return verts
            t_new = np.linspace(0, total, n, endpoint=False)
            fx = interp1d(arc, vc[:, 0])
            fy = interp1d(arc, vc[:, 1])
            return np.column_stack([fx(t_new), fy(t_new)])
        except Exception:
            return None