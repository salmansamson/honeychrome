from PySide6.QtCore import QPointF, QRectF, Qt, QRect, QSize, QPoint, Slot, QObject, QEvent
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLayout, QWidget, QHBoxLayout, QLabel, QSizePolicy, QCheckBox
import pyqtgraph as pg
import numpy as np

from honeychrome.settings import heading_style, line_colors
from honeychrome.view_components.cytometry_plot_components import (
    NoPanViewBox, ZoomAxis, TransparentGraphicsLayoutWidget,
)


# --------------------- Flow Layout -------------------------
# (Standard Qt FlowLayout implementation)
class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=6, spacing=6):
        super().__init__(parent)
        self.itemList = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def clear(self):
        for i in reversed(range(self.count())):
            item = self.takeAt(i)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def addItem(self, item):
        self.itemList.append(item)

    def count(self):
        return len(self.itemList)

    def itemAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self.doLayout(QRect(0, 0, width, 0), testOnly=True)
        return height

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.doLayout(rect, testOnly=False)

    def sizeHint(self):
        return QSize(400, 200)

    def doLayout(self, rect, testOnly=False):
        x = rect.x()
        y = rect.y()
        lineHeight = 0

        for item in self.itemList:
            wid = item.widget()
            spaceX = self.spacing()
            spaceY = self.spacing()
            nextX = x + item.sizeHint().width() + spaceX

            if nextX - spaceX > rect.right():
                x = rect.x()
                y = y + lineHeight + spaceY
                nextX = x + item.sizeHint().width() + spaceX
                lineHeight = 0

            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())

        return y + lineHeight - rect.y()


# --------------------- Legend Entry -------------------------
class LegendEntry(QWidget):
    """A single legend row: colored square + label."""
    def __init__(self, color, text):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(5)

        colorBox = QLabel()
        colorBox.setFixedSize(14, 14)
        colorBox.setStyleSheet(f"background-color: {color}; border:1px solid #444;")
        layout.addWidget(colorBox)

        nameLabel = QLabel(text)
        layout.addWidget(nameLabel)

        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)




class BottomAxisVerticalTickLabels(pg.AxisItem):
    def __init__(self, **kwargs):
        self.angle = 90
        self._label_padding = 15
        self.orientation = 'bottom'
        super().__init__(self.orientation, **kwargs)

        # Give extra space by default to prevent clipping
        self.setStyle(tickTextOffset=30, tickLength=5)

    def setTicks(self, ticks):
        extra_offset = int(10 + abs(self.angle) * 0.4)
        self.setStyle(tickTextOffset=extra_offset)
        super().setTicks(ticks)
        self.updateGeometry()
        self.update()

    def drawPicture(self, p, axisSpec, tickSpecs, textSpecs):
        # Draw tick lines normally (skip text)
        super().drawPicture(p, axisSpec, tickSpecs, [])

        # Draw rotated text labels manually
        p.save()
        for rect, flags, text in textSpecs:
            p.save()

            # --- DEBUG VISUALS ---
            # 1. Draw the original (unrotated) text rect in red
            # p.setPen(QPen(QColor("red"), 1, Qt.DashLine))
            # p.drawRect(rect)

            # 2. Draw the tick anchor point in green
            tick_anchor = QPointF(rect.center())
            # p.setPen(QPen(QColor("green"), 3))
            # p.drawPoint(tick_anchor)

            # --- TRANSFORMATIONS ---
            if self.orientation == 'bottom' and self.angle == 90:
                p.translate(tick_anchor)
                p.rotate(-self.angle)

                # 3. Draw local origin axes in blue (X) and magenta (Y)
                # p.setPen(QPen(QColor("blue"), 1))
                # p.drawLine(0, 0, 40, 0)  # X-axis
                # p.setPen(QPen(QColor("magenta"), 1))
                # p.drawLine(0, 0, 0, 40)  # Y-axis

                # 4. Draw the rotated text bounding rect in yellow
                text_rect = QRectF(0, -rect.height() / 2, rect.width(), rect.height())
                # p.setPen(QPen(QColor("yellow"), 1))
                # p.drawRect(text_rect)

                # --- Draw the text ---
                align = Qt.AlignRight | Qt.AlignVCenter
                # p.setPen(QPen(QColor("white")))
                p.drawText(text_rect, int(align), text)

            else:
                # Non-rotated text fallback
                # p.setPen(QPen(QColor("white")))
                p.drawText(rect, int(flags), text)

            p.restore()
        p.restore()

class TransparentPlotWidget(pg.PlotWidget):
    def wheelEvent(self, event: QWheelEvent):
        # We explicitly ignore the event.
        # This tells Qt: "I don't want this, give it to my parent."
        event.ignore()

class ProfilesViewer(QFrame):
    def __init__(self, bus, controller, pen_width=2, parent=None):
        super().__init__(parent)

        # connect
        self.bus = bus
        self.controller = controller
        self.pen_width = pen_width

        if self.bus:
            self.bus.showSelectedProfiles.connect(self.plot_profiles)
            self.bus.spectralControlAdded.connect(self.plot_latest_profile)
            self.bus.showSelectedProfiles.connect(lambda x: self.bus.spilloverSelectedCellChanged.emit(None, None))

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel("Profiles Viewer")
        self.layout.addWidget(self.title)
        self.title.setStyleSheet(heading_style)

        # ---- Flowing Legend ----
        self.legendContainer = QWidget()
        self.legendLayout = FlowLayout(self.legendContainer)
        self.layout.addWidget(self.legendContainer)

        # Create the PyQtGraph widget
        bottom_axis_vertical_tick_labels = BottomAxisVerticalTickLabels()
        self.plot_widget = TransparentPlotWidget(axisItems={'bottom': bottom_axis_vertical_tick_labels})
        self.layout.addWidget(self.plot_widget, stretch=1)
        vb = self.plot_widget.getViewBox()
        vb.setMenuEnabled(False)  # disable right-click menu

        # Configure the plot
        self.plot_widget.setLabel('left', 'Intensity')
        self.plot_widget.setLabel('bottom', 'All Fluorescence')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.addLegend()

        # Store plot items for potential updates
        self.plot_items = {}

        # ---- Collapsible peak-channel histogram panel ----
        self._hist_toggle = QCheckBox('Show peak-channel event histograms')
        self._hist_toggle.setChecked(False)
        self._hist_toggle.setToolTip(
            'For each selected control, plot a 1-D histogram of its peak channel.\n'
            'Gate boundaries are marked. When cleaned data are available and "Use Cleaned"\n'
            'is ticked, the cleaned positive and negative pools are shown as filled overlays.\n'
            'Axis style matches the Raw Data tab (biexponential transform, real-value ticks).'
        )
        self.layout.addWidget(self._hist_toggle)

        self._hist_panel = QWidget()
        hist_panel_layout = QVBoxLayout(self._hist_panel)
        hist_panel_layout.setContentsMargins(0, 4, 0, 0)
        hist_panel_layout.setSpacing(0)

        # Use the same graphics layout as CytometryPlotWidget so ZoomAxis works correctly
        self._hist_glw = TransparentGraphicsLayoutWidget()
        self._hist_glw.setMinimumHeight(200)
        self._hist_glw.setMaximumHeight(280)

        # Dummy viewbox just to satisfy ZoomAxis linkToView requirement
        self._hist_vb = NoPanViewBox()
        self._hist_axis_bottom = ZoomAxis('bottom', self._hist_vb)
        self._hist_axis_left = ZoomAxis('left', self._hist_vb)

        self._hist_glw.addItem(self._hist_axis_left,  row=0, col=0)
        self._hist_glw.addItem(self._hist_vb,          row=0, col=1)
        self._hist_glw.addItem(self._hist_axis_bottom, row=1, col=1)

        self._hist_axis_left.linkToView(self._hist_vb)
        self._hist_axis_bottom.linkToView(self._hist_vb)

        self._hist_vb.setMouseEnabled(x=False, y=False)
        self._hist_vb.enableAutoRange(axis=self._hist_vb.YAxis, enable=True)

        # Left axis — plain count, no transform
        self._hist_axis_left.setTicks(None)

        hist_panel_layout.addWidget(self._hist_glw)
        self._hist_panel.setVisible(False)
        self.layout.addWidget(self._hist_panel)

        self._hist_toggle.toggled.connect(self._hist_panel.setVisible)
        self._hist_toggle.toggled.connect(self._refresh_histogram)

        if self.controller.experiment.process['profiles']:
            self.plot_profiles([])

    def _refresh_histogram(self, *_):
        """Redraw the peak-channel histogram for the currently-displayed profiles."""
        if not self._hist_toggle.isChecked():
            return
        labels = list(self.plot_items.keys()) or list(
            self.controller.experiment.process.get('profiles', {}).keys()
        )
        self._plot_peak_histograms(labels)

    def _plot_peak_histograms(self, labels: list):
        """
        Draw 1-D histogram of the peak fluorescence channel for the selected
        control, using the same logicle transform and ZoomAxis ticks as the
        Raw Data tab.  Only active when exactly one control is selected.
        """
        if len(labels) != 1:
            self._hist_vb.clear()
            return
        
        from honeychrome.controller_components.spectral_functions import get_raw_events
        from honeychrome.controller_components.functions import sample_from_fcs

        self._hist_vb.clear()

        # Remove any previously-added legend label widget
        old_legend = getattr(self, '_hist_legend_label', None)
        if old_legend is not None:
            try:
                old_legend.setParent(None)
                old_legend.deleteLater()
            except Exception:
                pass
        self._hist_legend_label = None

        if not labels:
            return

        spectral_model   = self.controller.experiment.process.get('spectral_model', [])
        cleaned_store    = self.controller.experiment.process.get('cleaned_events', {})
        event_channels_pnn = self.controller.experiment.settings['raw']['event_channels_pnn']
        fluor_ch_ids     = self.controller.filtered_raw_fluorescence_channel_ids
        experiment_dir   = self.controller.experiment_dir
        all_samples      = self.controller.experiment.samples.get('all_samples', {})
        all_samples_rev  = {v: k for k, v in all_samples.items()}
        raw_gating       = self.controller.raw_gating
        transformations  = self.controller.raw_transformations  # dict[str -> Transform]

        legend_items: list[tuple[str, str]] = []

        for i, label in enumerate(labels):
            color    = line_colors[i % len(line_colors)]
            color_qt = pg.mkColor(color)

            control = next((c for c in spectral_model if c.get('label') == label), None)
            if control is None:
                continue

            peak_ch_name = control.get('gate_channel', '')
            if not peak_ch_name or peak_ch_name not in event_channels_pnn:
                continue
            try:
                peak_local_idx = fluor_ch_ids.index(event_channels_pnn.index(peak_ch_name))
            except (ValueError, IndexError):
                continue

            xform_obj = transformations.get(peak_ch_name) if transformations else None

            # ------------------------------------------------------------------
            # Helper: transform raw values and histogram them.
            # Matches Raw Data tab: uses step_scale as bin edges when a transform
            # is available (same bins, same resolution).  Normalises counts to
            # percent-of-peak so series with very different event counts overlay
            # cleanly.  Returns (edges, pct) where len(edges) == len(pct) + 1.
            # ------------------------------------------------------------------
            def _hist(vals: np.ndarray, _xf=xform_obj) -> tuple[np.ndarray, np.ndarray]:
                import honeychrome.settings as _settings
                n_bins = _settings.hist_bins_retrieved
                if _xf is not None and _xf.scale is not None:
                    count, _ = np.histogram(vals, bins=_xf.scale)
                    count = count.astype(float)
                    peak = count.max()
                    pct = count / peak * 100 if peak > 0 else count
                    return _xf.step_scale, pct
                else:
                    lo = float(np.nanpercentile(vals, 0.1))
                    hi = float(np.nanpercentile(vals, 99.9))
                    edges = np.linspace(lo, hi, n_bins + 2)
                    count, _ = np.histogram(vals, bins=edges)
                    count = count.astype(float)
                    peak = count.max()
                    pct = count / peak * 100 if peak > 0 else count
                    return edges, pct

            use_cleaned = control.get('use_cleaned', False)
            cleaned     = cleaned_store.get(label) if use_cleaned else None

            rel_path = all_samples_rev.get(control.get('sample_name', ''))

            _COL_ALL_GRAY  = (160, 160, 160, 100)   # gray        — all single-stained events
            _COL_CLEAN_POS = (160,  50, 220, 200)   # purple      — cleaned & selected positive
            _COL_MATCHED   = ( 80, 160, 255, 200)   # bright blue — scatter-matched negative

            if cleaned is not None:
                pos_events = cleaned.get('positive')
                neg_events = cleaned.get('negative')
                if pos_events is None or len(pos_events) == 0:
                    continue
                pos_peak_raw = pos_events[:, peak_local_idx]
                neg_peak_raw = (neg_events[:, peak_local_idx]
                                if (neg_events is not None and len(neg_events) > 0)
                                else None)

                # All-events background
                if rel_path:
                    try:
                        sample = sample_from_fcs(str(experiment_dir / rel_path))
                        all_ev = get_raw_events(sample, fluor_ch_ids)
                        x_all, y_all = _hist(all_ev[:, peak_local_idx])
                        item = pg.PlotDataItem(stepMode="center", fillLevel=0,
                                            brush=(*_COL_ALL_GRAY[:3], 60),
                                            pen=pg.mkPen(_COL_ALL_GRAY, width=1))
                        item.setData(x_all, y_all)
                        self._hist_vb.addItem(item)
                        legend_items.append(('#a0a0a0', f'{label} — all events'))
                    except Exception:
                        pass

                # Cleaned positive — solid blue (Raw Data style)
                x_pos, y_pos = _hist(pos_peak_raw)
                item = pg.PlotDataItem(stepMode="center", fillLevel=0,
                                    brush=(*_COL_CLEAN_POS[:3], 120),
                                    pen=pg.mkPen(_COL_CLEAN_POS, width=2))
                item.setData(x_pos, y_pos)
                self._hist_vb.addItem(item)
                legend_items.append(('#a032dc', f'{label} — cleaned +ve'))

                # Matched negative — lighter blue, dashed outline
                if neg_peak_raw is not None:
                    x_neg, y_neg = _hist(neg_peak_raw)
                    item = pg.PlotDataItem(stepMode="center", fillLevel=0,
                                        brush=(*_COL_MATCHED[:3], 80),
                                        pen=pg.mkPen(_COL_MATCHED, width=1, style=Qt.DashLine))
                    item.setData(x_neg, y_neg)
                    self._hist_vb.addItem(item)
                    legend_items.append(('#50a0ff', f'{label} — matched −ve (dashed)'))

            else:
                # Standard gate-mean path
                if not rel_path:
                    continue
                try:
                    sample = sample_from_fcs(str(experiment_dir / rel_path))
                    all_ev = get_raw_events(sample, fluor_ch_ids)
                    x_all, y_all = _hist(all_ev[:, peak_local_idx])
                    item = pg.PlotDataItem(stepMode="center", fillLevel=0,
                                        brush=(*_COL_ALL_GRAY[:3], 150),
                                        pen=pg.mkPen(_COL_ALL_GRAY[:3], width=2))
                    item.setData(x_all, y_all)
                    self._hist_vb.addItem(item)
                    legend_items.append(('#a0a0a0', label))
                except Exception:
                    continue

                # Gate boundary InfiniteLines
                for gate_lbl, gate_style in [
                    (control.get('gate_label', ''), Qt.SolidLine),
                    (f'Neg {label}',               Qt.DashLine),
                ]:
                    if not gate_lbl:
                        continue
                    try:
                        if not raw_gating.find_matching_gate_paths(gate_lbl):
                            continue
                        mask = raw_gating.gate_sample(sample).get_gate_membership(gate_lbl)
                        if mask.sum() == 0:
                            continue
                        boundary_raw = float(all_ev[mask, peak_local_idx].min())
                        if xform_obj is not None and xform_obj.xform is not None:
                            boundary_t = float(xform_obj.xform.apply(
                                np.array([boundary_raw]))[0])
                        else:
                            boundary_t = boundary_raw
                        self._hist_vb.addItem(pg.InfiniteLine(
                            pos=boundary_t, angle=90,
                            pen=pg.mkPen(color, width=1, style=gate_style),
                            label=gate_lbl,
                            labelOpts={'position': 0.85, 'color': color},
                        ))
                    except Exception:
                        pass

        # Apply transform axis and labels to the selected control's peak channel
        first_ctrl = next(
            (c for c in spectral_model if c.get('label') in labels), None)
        if first_ctrl and transformations:
            ch = first_ctrl.get('gate_channel', '')
            xf = transformations.get(ch)
            if xf is not None and xf.step_scale is not None:
                self._hist_axis_bottom.setTicks(xf.ticks())
                self._hist_axis_bottom.zoomZero = xf.zero
                self._hist_axis_bottom.limits   = xf.limits
                self._hist_vb.setXRange(xf.limits[0], xf.limits[1], padding=0)
            self._hist_axis_bottom.setLabel(ch)

        self._hist_axis_left.setLabel('% of peak')
        self._hist_vb.setYRange(0, 100, padding=0.02)
        self._hist_vb.enableAutoRange(axis=self._hist_vb.YAxis, enable=False)

        # Simple colour-coded text legend
        if legend_items:
            parts = [
                f'<span style="color:{hx};">&#9632;</span> {txt}'
                for hx, txt in legend_items
            ]
            lbl = QLabel('  '.join(parts))
            lbl.setTextFormat(Qt.RichText)
            lbl.setWordWrap(True)
            self._hist_panel.layout().addWidget(lbl)
            self._hist_legend_label = lbl

    def show_context_menu(self, event):
        # Empty method to completely disable context menu
        pass

    @Slot()
    def plot_latest_profile(self):
        spectral_model = self.controller.experiment.process['spectral_model']
        if spectral_model:
            control = spectral_model[-1]['label']
            if control:
                if control in self.controller.experiment.process['profiles']:
                    self.plot_profiles([control], show_legend=False)

    @Slot(list)
    def plot_profiles(self, profile_list, show_legend=True):

        # Clear previous plots
        self.plot_widget.clear()
        self.plot_items.clear()
        self.legendLayout.clear()

        profiles = self.controller.experiment.process['profiles']

        x = list(range(len(self.controller.filtered_raw_fluorescence_channel_ids)))
        ticks = [[(m, self.controller.experiment.settings['raw']['event_channels_pnn'][n]) for m, n in
                   enumerate(self.controller.filtered_raw_fluorescence_channel_ids)], []]
        self.plot_widget.getAxis('bottom').setTicks(ticks)


        # Plot each profile
        if profile_list:
            pass
        else:
            profile_list = list(profiles.keys())

        profile_list = [p for p in profile_list if p]
        for i, profile_name in enumerate(profile_list):
            if profile_name in profiles:
                color = line_colors[i % len(line_colors)]
                pen = pg.mkPen(color=color, width=self.pen_width)
                plot_item = self.plot_widget.plot(x, profiles[profile_name], pen=pen)
                self.plot_items[profile_name] = plot_item
                if show_legend:
                    entry = LegendEntry(color, profile_name)
                    self.legendLayout.addWidget(entry)

        # self.plot_widget.autoRange()
        self.plot_widget.setXRange(0, len(self.controller.filtered_raw_fluorescence_channel_ids))  # Set custom x-axis range
        self.plot_widget.setYRange(0, 1)  # Set custom y-axis range

        # Refresh histogram if it's visible
        if self._hist_toggle.isChecked():
            self._plot_peak_histograms(profile_list)




if __name__ == '__main__':
    from PySide6.QtWidgets import QApplication, QVBoxLayout
    import sys

    app = QApplication(sys.argv)

    from honeychrome.controller import Controller
    from pathlib import Path
    from event_bus import EventBus

    bus = EventBus()
    kc = Controller()
    base_directory = Path.home() / 'spectral_cytometry'
    experiment_name = base_directory / '20240620 Spectral Symposium-poor cell unmixed'
    experiment_path = experiment_name.with_suffix('.kit')
    kc.load_experiment(experiment_path) # note this loads first sample too and runs calculate all histograms and statistics

    plot_frame = ProfilesViewer(bus, kc)

    # Plot the profiles
    plot_frame.plot_profiles([])
    plot_frame.show()

    plot_frame.resize(950, 600)
    sys.exit(app.exec())