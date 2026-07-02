"""
Honeychrome Plugin
Compare transforms tab
---------------------------
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QPushButton, QLabel, QComboBox, QHBoxLayout, QGridLayout, QFrame, QSplitter, QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QHeaderView, QSpinBox, QDoubleSpinBox
from PySide6.QtCore import Qt, Signal, QRectF, QTimer, QSize
import numpy as np
import colorcet as cc
import pyqtgraph as pg
from copy import deepcopy

from honeychrome.settings import cytometry_plot_width_target

from honeychrome.controller_components.functions import (
    build_display_label_map,
)

from honeychrome.controller_components.transform import Transform
from honeychrome.view_components.cytometry_plot_components import (
    InteractiveLabel,
    NoPanViewBox,
    ZoomAxis,
    TransparentGraphicsLayoutWidget,
)
import honeychrome.settings as settings
from honeychrome.controller_components.transform import transforms_menu_items

import logging

logger = logging.getLogger(__name__)

plugin_name = 'Compare Transforms Plugin'

row_height = 30
cell_width = 200
class FullyExpandedTree(QTreeWidget):
    def __init__(self):
        super().__init__()
        # Ensure scrollbars never appear
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Connect signals to auto-resize when user interacts
        self.itemExpanded.connect(self.update_size)
        self.itemCollapsed.connect(self.update_size)

        self.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.header().setSectionResizeMode(1, QHeaderView.Stretch)

    def update_size(self):
        # Calculate total height of visible rows
        total_height = self.header().height()
        for i in range(self.topLevelItemCount()):
            total_height += self.visualItemRect(self.topLevelItem(i)).height()
            # If expanded, add heights of children
            if self.topLevelItem(i).isExpanded():
                for j in range(self.topLevelItem(i).childCount()):
                    total_height += self.visualItemRect(self.topLevelItem(i).child(j)).height()


        # Add a small buffer for borders
        self.setFixedHeight(total_height + 5)

class TransformsComparisonPlotWidget(QWidget):
    """
    Based on AfComparisonPlotWidget from the autospectral tab.

    A single density-heatmap biplot that mirrors the style of CytometryPlotWidget
    (dark background, colorcet colourmap, logicle transforms, ZoomAxis drag zoom)
    but operates on a locally held event array rather than the shared controller
    data pipeline.

    Parameters
    ----------
    title : str
        Label shown above the plot.
    controller : Controller
        Used to read unmixed_transformations for initial transform params,
        unmixed pnn/fl_ids for channel menus, and unmixed_lookup_tables for gating.
    """

    # Emitted when the source gate is changed so the parent can redraw both plots
    # with a consistent gate mask.
    sourceGateChanged = Signal(str)
    # Emitted when either channel is changed, so the sibling plot can mirror it.
    channelChanged = Signal(str, str)   # (channel_x, channel_y)

    def __init__(self, title: str, controller, parent=None, editable_transforms=False):
        super().__init__(parent)
        self.controller = controller
        self._title_text = title

        # Local copies of Transform objects (not shared with Unmixed Data tab)
        self._transformations: dict[str, Transform] = {}
        # Current source gate name
        self._source_gate: str = 'root'
        # Current channel names
        self._channel_x: str | None = None
        self._channel_y: str | None = None

        # Build colourmap LUT (same as CytometryPlotWidget)
        colors = cc.palette[settings.colourmap_name_retrieved]
        cmap = pg.ColorMap(
            pos=0.9 * np.linspace(0.0, 1.0, len(colors)) ** 2
                + 0.1 * np.linspace(0.0, 1.0, len(colors)),
            color=colors,
        )
        rgba_lut = cmap.getLookupTable(alpha=True)
        rgba_lut[0, 3] = 0   # fully transparent for zero-count bins
        self._rgba_lut = rgba_lut

        # ---- Layout ----
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.graphics_widget = TransparentGraphicsLayoutWidget(parent=self)
        gl = self.graphics_widget.ci.layout
        gl.setHorizontalSpacing(0)
        gl.setVerticalSpacing(0)

        # Title label (gate source selector)
        self.plot_title = InteractiveLabel(title, parent_plot=self)
        self.plot_title.setParent(self)
        self.graphics_widget.addItem(self.plot_title, row=0, col=2)

        # ViewBox
        self.vb = NoPanViewBox()
        self.vb.setParent(self)
        self.graphics_widget.addItem(self.vb, row=1, col=2)

        # Axes and labels
        self.label_y = InteractiveLabel('Y Axis', parent_plot=self, angle=-90)
        self.graphics_widget.addItem(self.label_y, row=1, col=0)
        self.axis_left = ZoomAxis('left', self.vb)
        self.graphics_widget.addItem(self.axis_left, row=1, col=1)

        self.axis_bottom = ZoomAxis('bottom', self.vb)
        self.graphics_widget.addItem(self.axis_bottom, row=2, col=2)
        self.label_x = InteractiveLabel('X Axis', parent_plot=self)
        self.graphics_widget.addItem(self.label_x, row=3, col=2)

        self.axis_left.linkToView(self.vb)
        self.axis_bottom.linkToView(self.vb)
        self.label_x.setParent(self.axis_bottom)
        self.label_y.setParent(self.axis_left)
        self.axis_bottom.setParent(self)
        self.axis_left.setParent(self)

        self.axis_bottom.zoom_timer.timeout.connect(lambda: self._apply_zoom('x'))
        self.axis_left.zoom_timer.timeout.connect(lambda: self._apply_zoom('y'))

        # Disable right-click context menu (no gates in comparison plots)
        self.vb.raiseContextMenu = lambda ev: None

        # Heatmap image item
        self.img = pg.ImageItem(parent=self)
        self.img.setLookupTable(self._rgba_lut)
        self.vb.addItem(self.img)

        # Status label (shown when computing or on error)
        self._status_label = QLabel('', alignment=Qt.AlignLeft)
        self._status_label.setStyleSheet('color: #aaaaaa;')

        # transforms label
        self.transforms_tree = FullyExpandedTree()
        self.transforms_tree.setHeaderLabels(["Parameter", "Value"])
        self.editable_transforms = editable_transforms
        self._running = False

        main_layout.addWidget(self.graphics_widget)
        main_layout.addWidget(self._status_label)
        main_layout.addWidget(self.transforms_tree)

        # Axis label left-click: change channel
        self.label_x.leftClickMenuFunction = self._set_channel_x
        self.label_y.leftClickMenuFunction = self._set_channel_y

        self.label_x.rightClickMenuFunction = self.set_axis_transform
        self.label_y.rightClickMenuFunction = self.set_axis_transform

        # Title left-click: change source gate
        self.plot_title.leftClickMenuFunction = self._set_source_gate

    def resizeEvent(self, event):
        side = min(1.5*cytometry_plot_width_target, self.width())
        self.graphics_widget.setFixedHeight(side)
        self.graphics_widget.resize(side, side)
        super().resizeEvent(event)

    def sizeHint(self):
        # Suggest a square to the layout
        return QSize(cytometry_plot_width_target, cytometry_plot_width_target)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def initialise_from_controller(self, channel_x: str, channel_y: str):
        """
        Copy Transform objects from controller.unmixed_transformations,
        set initial channels, and configure axes.  Call after set_event_data().
        """
        src = self.controller.unmixed_transformations or {}
        self._transformations = {}
        for ch, tr in src.items():
            self._transformations[ch] = deepcopy(tr)

        self._channel_x = channel_x
        self._channel_y = channel_y
        self._source_gate = 'root'
        self._configure_axes()
        self._construct_transformations_tree()

    def set_channels(self, channel_x: str, channel_y: str):
        """Change the displayed channels and reconfigure axes."""
        self._channel_x = channel_x
        self._channel_y = channel_y
        self._construct_transformations_tree()
        self._configure_axes()
        self._draw()

    def set_source_gate(self, gate_name: str):
        """Change the source gate (called from external sync)."""
        self._source_gate = gate_name
        self._configure_title()
        self._draw()

    def redraw(self):
        self._draw()

    def clear(self):
        self.img.clear()
        self._status_label.setText('')

    # ------------------------------------------------------------------
    # Internal: axis configuration
    # ------------------------------------------------------------------

    def _configure_axes(self):
        if not self._running: self._running = True; QTimer.singleShot(100, lambda: [self._configure_axes_debounced(), setattr(self, '_running', False)])

    def _configure_axes_debounced(self):
        if (not self._transformations
                or self._channel_x not in self._transformations
                or self._channel_y not in self._transformations):
            return

        pnn = self.controller.experiment.settings['unmixed'].get('event_channels_pnn', [])
        fl_ids = self.controller.experiment.settings['unmixed'].get('fluorescence_channel_ids', [])
        fl_names = [pnn[i] for i in fl_ids] if pnn and fl_ids else []
        pnn_labels = build_display_label_map(
            pnn, self.controller.experiment.process.get('spectral_model')
        )
        fl_display = [pnn_labels.get(n, n) for n in fl_names]

        self.label_x.rightItemSelected = self._transformations[self._channel_x].id
        self.label_y.rightItemSelected = self._transformations[self._channel_y].id
        self.label_x.rightClickMenuItems = transforms_menu_items
        self.label_y.rightClickMenuItems = transforms_menu_items

        # X axis
        self.label_x.setText(pnn_labels.get(self._channel_x, self._channel_x))
        self.label_x.leftClickMenuItems = fl_display
        self.label_x.leftItemSelected = (
            fl_names.index(self._channel_x) if self._channel_x in fl_names else 0
        )
        tr_x = self._transformations[self._channel_x]
        self.axis_bottom.setTicks(tr_x.ticks())
        self.axis_bottom.zoomZero = tr_x.zero
        self.axis_bottom.fullRange = (0, 1.1)
        self.axis_bottom.limits = tr_x.limits
        self.vb.setXRange(*tr_x.limits, padding=0)

        # Y axis
        self.label_y.setText(pnn_labels.get(self._channel_y, self._channel_y))
        self.label_y.leftClickMenuItems = fl_display
        self.label_y.leftItemSelected = (
            fl_names.index(self._channel_y) if self._channel_y in fl_names else 0
        )
        tr_y = self._transformations[self._channel_y]
        self.axis_left.setTicks(tr_y.ticks())
        self.axis_left.zoomZero = tr_y.zero
        self.axis_left.fullRange = (0, 1.1)
        self.axis_left.limits = tr_y.limits
        self.vb.setYRange(*tr_y.limits, padding=0)

        self._configure_title()

    def _configure_title(self):
        """Populate gate source menu from the unmixed gating strategy."""
        gating = self.controller.unmixed_gating
        if gating is None:
            gate_names = ['root']
        else:
            gate_ids = [
                g for g in gating.get_gate_ids()
                if gating._get_gate_node(g[0], g[1]).gate_type != 'QuadrantGate'
            ]
            gate_names = ['root'] + [g[0] for g in gate_ids]

        # Validate current gate still exists
        if self._source_gate not in gate_names:
            self._source_gate = 'root'

        self.plot_title.setText(f'{self._title_text}  [{self._source_gate}]')
        self.plot_title.leftClickMenuItems = gate_names
        self.plot_title.leftClickMenuFunction = self._set_source_gate
        self.plot_title.leftItemSelected = gate_names.index(self._source_gate)

    def _construct_transformations_tree(self):
        if (not self._transformations
                or self._channel_x not in self._transformations
                or self._channel_y not in self._transformations):
            return

        ### redraw transforms_tree
        self.transforms_tree.clear()
        for channel in [self._channel_x, self._channel_y]:
            parent = QTreeWidgetItem(self.transforms_tree, [channel])
            parent.setSizeHint(0, QSize(cell_width, row_height))
            tr = self._transformations[channel]
            if tr.id == 0:
                transform_type = 'Linear'
                transform_parameters = {'Transform':transform_type, 'linear T':tr.scale_t, 'linear A':tr.linear_a, 'bins':tr.scale_bins}
            elif tr.id == 1:
                transform_type = 'Logicle'
                transform_parameters = {'Transform':transform_type, 'logicle T':tr.scale_t, 'logicle A':tr.logicle_a, 'logicle W':tr.logicle_w, 'logicle M':tr.logicle_m, 'bins':tr.scale_bins}
            elif tr.id == 2:
                transform_type = 'Log'
                transform_parameters = {'Transform':transform_type, 'log T':tr.scale_t, 'log M':tr.log_m, 'bins':tr.scale_bins}
            else:
                transform_type = 'Default'
                transform_parameters = {'Transform':transform_type, 'bins':tr.scale_bins}

            transform_parameters.update({'crop scale lower':tr.limits[0], 'crop scale upper':tr.limits[1]})
            for key, value in transform_parameters.items():
                child = QTreeWidgetItem(parent, [key, str(value)])
                if self.editable_transforms:
                    if key == 'Transform':
                        combo = QComboBox()
                        transform_list = ["Linear", "Logicle", "Log"]
                        combo.addItems(transform_list)
                        combo.setCurrentIndex(tr.id)
                        self.transforms_tree.setItemWidget(child, 1, combo)
                        combo.currentIndexChanged.connect(lambda index, parent_axis=self.axis_bottom if channel == self._channel_x else self.axis_left: self.set_axis_transform(index, parent_axis))
                    else:
                        if key in ['bins']:
                            spin = QSpinBox()
                            spin.setRange(10, 1000)
                            spin.setSingleStep(10)
                        elif key in ['crop scale lower', 'crop scale upper']:
                            spin = QDoubleSpinBox()
                            spin.setRange(0.0, 1.0)
                            spin.setSingleStep(0.01)
                        elif key in ['logicle A', 'logicle W', 'logicle M', 'linear A', 'log M']:
                            spin = QDoubleSpinBox()
                            spin.setRange(0.0, 10.0)
                            spin.setSingleStep(0.1)
                        elif key in ['logicle T', 'linear T', 'log T']:
                            spin = QDoubleSpinBox()
                            spin.setRange(10000, 10**9)
                            spin.setSingleStep(int(0.1*value+1))
                        else:
                            spin = QDoubleSpinBox()
                            spin.setRange(-10**9, 10**9)
                            spin.setSingleStep(0.1)

                        spin.setValue(value)
                        self.transforms_tree.setItemWidget(child, 1, spin)
                        spin.valueChanged.connect(
                            lambda val, ch=channel, parameter=key:
                            self.adjust_axis_transform(ch, parameter, val)
                        )



                child.setSizeHint(0, QSize(cell_width, row_height))

        self.transforms_tree.expandAll()


    # ------------------------------------------------------------------
    # Internal: drawing
    # ------------------------------------------------------------------

    def _draw(self):
        if self.controller.unmixed_event_data is None:
            self.img.clear()
            return
        if (self._channel_x not in self._transformations
                or self._channel_y not in self._transformations):
            return

        pnn = self.controller.experiment.settings['unmixed'].get('event_channels_pnn', [])
        if self._channel_x not in pnn or self._channel_y not in pnn:
            return

        x_col = pnn.index(self._channel_x)
        y_col = pnn.index(self._channel_y)

        # Start with all events; gate masking will narrow this down if needed.
        event_data = self.controller.unmixed_event_data

        # Compute a per-event gate mask using the same mechanism as
        # apply_gates_in_place in functions.py.  The unmixed_lookup_tables,
        # unmixed_transformations, and unmixed_gating are all populated on the
        # controller regardless of which tab is currently active, so this works
        # from the AutoSpectral tab.
        mask = self._compute_gate_mask(event_data)
        if mask is not None:
            event_data = event_data[mask]

        tr_x = self._transformations[self._channel_x]
        tr_y = self._transformations[self._channel_y]

        try:
            heatmap, _, _ = np.histogram2d(
                event_data[:, x_col],
                event_data[:, y_col],
                bins=[tr_x.scale, tr_y.scale],
            )
        except Exception as e:
            logger.error(f'TransformComparisonPlotWidget._draw histogram failed: {e}')
            return

        # Apply density cutoff (match CytometryPlotWidget: bins below cutoff → 0)
        cutoff = settings.density_cutoff_retrieved
        heatmap[heatmap < cutoff] = 0

        # Rescale border bins to interior max — mirrors calc_hist2d() in functions.py
        # so that edge overflow events don't compress the interior colour range.
        if heatmap.shape[0] > 2 and heatmap.shape[1] > 2:
            global_max = heatmap.max()
            inside_max = heatmap[1:-1, 1:-1].max()
            if inside_max > 0 and inside_max < global_max:
                scale = inside_max / global_max
                heatmap[0, :] *= scale
                heatmap[-1, :] *= scale
                heatmap[1:-1, 0] *= scale
                heatmap[1:-1, -1] *= scale

        self.img.setImage(heatmap)
        self.img.setRect(QRectF(
            tr_x.limits[0], tr_y.limits[0],
            tr_x.limits[1] - tr_x.limits[0],
            tr_y.limits[1] - tr_y.limits[0],
        ))

    # ------------------------------------------------------------------
    # Internal: gate membership computation
    # ------------------------------------------------------------------

    def _compute_gate_mask(self, event_data: np.ndarray) -> np.ndarray | None:
        """
        Compute a per-event boolean mask for self._source_gate applied to
        event_data, using the controller's unmixed_lookup_tables,
        unmixed_transformations, and unmixed_gating.

        This replicates the logic of apply_gates_in_place() from functions.py,
        walking the full gate ancestry so that child gates correctly inherit
        their parent's membership.

        Returns None if 'root' is selected or if gating is unavailable.
        Returns a boolean ndarray of length len(event_data) otherwise.
        """
        if self._source_gate == 'root':
            return None

        gating = self.controller.unmixed_gating
        lookup_tables = self.controller.unmixed_lookup_tables
        transforms = self.controller.unmixed_transformations
        pnn = self.controller.experiment.settings['unmixed'].get('event_channels_pnn', [])

        if gating is None or not lookup_tables or not transforms or not pnn:
            return None

        # Build the full ancestry path to the target gate, root-first
        try:
            paths = gating.find_matching_gate_paths(self._source_gate)
        except Exception:
            return None
        if not paths:
            return None

        # Ancestry: all gates in the path from root to target (exclusive of
        # 'root' itself since every event is in root), then the target gate.
        ancestry_path = list(paths[0])   # e.g. ('root', 'Cells')
        gate_sequence = [g for g in ancestry_path if g != 'root'] + [self._source_gate]
        # Deduplicate while preserving order (target may already be last)
        seen = set()
        gate_sequence_dedup = []
        for g in gate_sequence:
            if g not in seen:
                seen.add(g)
                gate_sequence_dedup.append(g)

        n_events = len(event_data)
        # Start with all-True (every event is in 'root')
        cumulative_mask = np.ones(n_events, dtype=bool)

        for gate_name in gate_sequence_dedup:
            if gate_name not in lookup_tables:
                # Gate not found in lookup tables — skip
                logger.warning(
                    f'AfComparisonPlotWidget._compute_gate_mask: '
                    f'"{gate_name}" not in unmixed_lookup_tables'
                )
                return None

            try:
                gate = gating.get_gate(gate_name)
                channels = gate.get_dimension_ids()

                if len(channels) == 1:
                    xchan = channels[0]
                    if xchan not in pnn:
                        return None
                    ix = pnn.index(xchan)
                    x = event_data[:, ix]
                    scale_x = transforms[xchan].scale
                    idx = np.searchsorted(scale_x, x) - 2
                    lt = lookup_tables[gate_name]
                    idx = np.clip(idx, 0, len(lt) - 1)
                    gate_mask = lt[idx]

                else:  # 2-channel gate
                    if gate.gate_type == 'QuadrantGate':
                        xchan = gate.dimensions[0].dimension_ref
                        ychan = gate.dimensions[1].dimension_ref
                    else:
                        xchan = channels[0]
                        ychan = channels[1]
                    if xchan not in pnn or ychan not in pnn:
                        return None
                    ix = pnn.index(xchan)
                    iy = pnn.index(ychan)
                    x = event_data[:, ix]
                    y = event_data[:, iy]
                    scale_x = transforms[xchan].scale
                    scale_y = transforms[ychan].scale
                    idx_x = np.searchsorted(scale_x, x) - 2
                    idx_y = np.searchsorted(scale_y, y) - 2
                    bins_x = transforms[xchan].scale_bins + 1
                    flat_idx = idx_x * bins_x + idx_y
                    lt = lookup_tables[gate_name]
                    flat_idx = np.clip(flat_idx, 0, len(lt) - 1)
                    gate_mask = lt[flat_idx]

                cumulative_mask = cumulative_mask & gate_mask.astype(bool)

            except Exception as e:
                logger.error(
                    f'AfComparisonPlotWidget._compute_gate_mask: '
                    f'error computing mask for "{gate_name}": {e}'
                )
                return None

        return cumulative_mask

    # ------------------------------------------------------------------
    # Internal: zoom (mirrors CytometryPlotWidget.apply_zoom)
    # ------------------------------------------------------------------

    def _apply_zoom(self, axis_name: str):
        if axis_name == 'x':
            axis = self.axis_bottom
            channel = self._channel_x
            vb_set_range = self.vb.setXRange
            vb_range_ind = 0
            map_pos = self.vb.mapToView(axis.initial_pos).x() if axis.initial_pos else 0.5
            factor_flip = False
        else:
            axis = self.axis_left
            channel = self._channel_y
            vb_set_range = self.vb.setYRange
            vb_range_ind = 1
            map_pos = self.vb.mapToView(axis.initial_pos).y() if axis.initial_pos else 0.5
            factor_flip = True

        if axis._pending_delta == 0 or channel not in self._transformations:
            return

        step = axis._pending_delta
        axis._pending_delta = 0
        if abs(step) < 1:
            return

        zoom_rate = 1.04
        factor = (1 / zoom_rate) if step > 0 else zoom_rate
        if factor_flip:
            factor = 1 / factor

        tr = self._transformations[channel]
        vmin, vmax = self.vb.viewRange()[vb_range_ind]

        if tr.id == 1:  # logicle
            if map_pos < 0.5 * vmax:
                tr.logicle_w = tr.logicle_w / factor
                tr.set_transform()
            else:
                new_max = (vmax - axis.zoomZero) * factor + axis.zoomZero
                new_min = (vmin - axis.zoomZero) * factor + axis.zoomZero
                if new_max < axis.fullRange[1] * 1.01:
                    vb_set_range(new_min, new_max, padding=0)
                axis.limits = (new_min, new_max)
                tr.set_transform(limits=axis.limits)
        else:  # linear or log
            new_max = (vmax - axis.zoomZero) * factor + axis.zoomZero
            new_min = (vmin - axis.zoomZero) * factor + axis.zoomZero
            if new_max < axis.fullRange[1] * 1.01:
                vb_set_range(new_min, new_max, padding=0)
            axis.limits = (new_min, new_max)
            tr.set_transform(limits=axis.limits)

        axis.zoomZero = tr.zero
        axis.setTicks(tr.ticks())
        self._draw()
        self._construct_transformations_tree()
        self._configure_axes()

    # ------------------------------------------------------------------
    # Slot: channel changed via label click
    # ------------------------------------------------------------------

    def _set_channel_x(self, n, _parent):
        pnn = self.controller.experiment.settings['unmixed'].get('event_channels_pnn', [])
        fl_ids = self.controller.experiment.settings['unmixed'].get('fluorescence_channel_ids', [])
        fl_names = [pnn[i] for i in fl_ids] if pnn and fl_ids else []
        if 0 <= n < len(fl_names):
            self._channel_x = fl_names[n]
            self._construct_transformations_tree()
            self._configure_axes()
            self._draw()
            self.channelChanged.emit(self._channel_x, self._channel_y)

    def _set_channel_y(self, n, _parent):
        pnn = self.controller.experiment.settings['unmixed'].get('event_channels_pnn', [])
        fl_ids = self.controller.experiment.settings['unmixed'].get('fluorescence_channel_ids', [])
        fl_names = [pnn[i] for i in fl_ids] if pnn and fl_ids else []
        if 0 <= n < len(fl_names):
            self._channel_y = fl_names[n]
            self._construct_transformations_tree()
            self._configure_axes()
            self._draw()
            self.channelChanged.emit(self._channel_x, self._channel_y)

    def set_axis_transform(self, n, parent):
        if parent == self.axis_bottom:
            channel = self._channel_x
        else:
            channel = self._channel_y

        self._transformations[channel].set_transform(id=n)
        self._construct_transformations_tree()
        self._configure_axes()
        self._draw()

    def adjust_axis_transform(self, channel, parameter, value):

        if parameter in ['crop scale lower', 'crop scale upper']:
            if parameter == 'crop scale lower':
                self._transformations[channel].limits[0] = value
            else:
                self._transformations[channel].limits[1] = value
        else:
            if parameter in ['linear T', 'logicle T', 'log T']:
                attr = 'scale_t'
            elif parameter == 'linear A':
                attr = 'linear_a'
            elif parameter == 'logicle A':
                attr = 'logicle_a'
            elif parameter == 'logicle W':
                attr = 'logicle_w'
            elif parameter == 'logicle M':
                attr = 'logicle_m'
            elif parameter == 'log M':
                attr = 'log_m'
            elif parameter == 'bins':
                attr = 'scale_bins'
            else:
                return
            setattr(self._transformations[channel], attr, value)

        self._transformations[channel].set_transform()
        self._configure_axes()
        self._draw()

    def _set_source_gate(self, n, _parent):
        gate_names = self.plot_title.leftClickMenuItems
        if 0 <= n < len(gate_names):
            self._source_gate = gate_names[n]
            self._configure_title()
            self._draw()
            self.sourceGateChanged.emit(self._source_gate)

    # ------------------------------------------------------------------
    # Required by InteractiveLabel / CytometryPlotWidget contract
    # ------------------------------------------------------------------

    def select_plot_on_parent_grid(self):
        pass   # No parent grid — no-op

    def update_table_height(self):
        # 1. Force the table to recalculate its contents
        self.transforms_tree.resizeRowsToContents()

        # 2. Calculate the height of all rows + the header (if visible)
        total_height = self.transforms_tree.horizontalHeader().height()
        for i in range(self.transforms_tree.rowCount()):
            total_height += self.transforms_tree.rowHeight(i)

        # 3. Add a small buffer for grid lines/borders (approx 2px)
        total_height += 2

        # 4. Set fixed height
        self.transforms_tree.setFixedHeight(total_height)


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

        # the content widget goes in a scroll widget, which goes in the PluginWidget
        content_widget = QWidget()
        main_layout = QVBoxLayout(content_widget)

        # make this widget scrollable and resizeable
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(content_widget)
        scroll.setWidgetResizable(True)

        overall_layout = QVBoxLayout(self)
        overall_layout.addWidget(scroll)


        # --- Add GUI elements ---
        self.label = QLabel('Compare channel transforms in unmixed plots.')
        self.label.setTextFormat(Qt.RichText)
        self.label.setWordWrap(True)

        # Side-by-side plot widgets
        plot_splitter = QSplitter(Qt.Horizontal)

        self._plot_expt = TransformsComparisonPlotWidget(
            'Transforms from experiment', self.controller, parent=self, editable_transforms=False
        )
        self._plot_expt.sourceGateChanged.connect(self._on_expt_gate_changed)
        self._plot_expt.channelChanged.connect(self._on_expt_channel_changed)

        self._plot_adj = TransformsComparisonPlotWidget(
            'Adjustable transforms', self.controller, parent=self, editable_transforms=True
        )
        self._plot_adj.sourceGateChanged.connect(self._on_adj_gate_changed)
        self._plot_adj.channelChanged.connect(self._on_adj_channel_changed)

        column_left_widget = QWidget()
        column_right_widget = QWidget()
        column_left_layout = QVBoxLayout(column_left_widget)
        column_right_layout = QVBoxLayout(column_right_widget)
        column_left_layout.addWidget(self._plot_expt)
        column_right_layout.addWidget(self._plot_adj)
        column_left_layout.setAlignment(Qt.AlignTop)
        column_right_layout.setAlignment(Qt.AlignTop)
        plot_splitter.addWidget(column_left_widget)
        plot_splitter.addWidget(column_right_widget)
        plot_splitter.setSizes([1000, 1000])

        # values and controls frame
        values_frame = QFrame(self)
        controls_frame = QFrame(self)

        column_left_layout.addWidget(values_frame)
        self.values_layout = QVBoxLayout(values_frame)
        column_right_layout.addWidget(controls_frame)
        self.controls_layout = QVBoxLayout(controls_frame)

        main_layout.addWidget(self.label)
        main_layout.addWidget(plot_splitter)
        main_layout.addStretch()

        if self.bus:
            self.bus.modeChangeRequested.connect(self._on_mode_change)
            self.bus.loadSampleRequested.connect(self._on_sample_loaded)


    # ======================================================================
    # Bus signal handlers
    # ======================================================================

    def _on_mode_change(self, mode):
        if mode == plugin_name:
            self._refresh_ui()
            if self.controller.raw_event_data is not None:
                QTimer.singleShot(0, self._initialise_comparison_plots)

    def _on_sample_loaded(self, _sample_path):
        if self.controller.current_mode == plugin_name:
            QTimer.singleShot(0, self._initialise_comparison_plots)



    # ======================================================================
    # Full UI refresh
    # ======================================================================

    def _refresh_ui(self):
        if self.controller.experiment.process.get('unmixing_matrix') is None:
            return
        # self.controls_layout.addWidget()

    def _initialise_comparison_plots(self):
        """
        Feed event data to both plot widgets and initialise their transforms
        from the live unmixed_transformations.  Pick default X/Y channels.
        Existing channel, scaling, and gate selections are preserved.
        """
        pnn = self.controller.experiment.settings['unmixed'].get('event_channels_pnn', [])
        fl_ids = self.controller.experiment.settings['unmixed'].get('fluorescence_channel_ids', [])
        if not pnn or not fl_ids or len(fl_ids) < 2:
            return

        fl_names = [pnn[i] for i in fl_ids]
        # Default: first two fluorescence channels
        ch_x = fl_names[0]
        ch_y = fl_names[1]

        # Preserve existing channel selections if both plots already have them
        if (self._plot_expt._channel_x in fl_names
                and self._plot_expt._channel_y in fl_names):
            ch_x = self._plot_expt._channel_x
            ch_y = self._plot_expt._channel_y

        gate_expt = self._plot_expt._source_gate
        gate_adj = self._plot_adj._source_gate

        self._plot_expt.initialise_from_controller(ch_x, ch_y)
        self._plot_expt._source_gate = gate_expt
        self._plot_expt._configure_axes()
        self._plot_expt.redraw()

        self._plot_adj.initialise_from_controller(ch_x, ch_y)
        self._plot_adj._source_gate = gate_adj
        self._plot_adj._configure_axes()
        self._plot_adj.redraw()

    def _on_expt_gate_changed(self, gate_name: str):
        """Sync source gate."""
        self._plot_adj.set_source_gate(gate_name)

    def _on_adj_gate_changed(self, gate_name: str):
        """Sync source gate."""
        self._plot_expt.set_source_gate(gate_name)

    def _on_expt_channel_changed(self, ch_x: str, ch_y: str):
        """Mirror channel selection from OLS to AF plot."""
        self._plot_adj.blockSignals(True)
        self._plot_adj.set_channels(ch_x, ch_y)
        self._plot_adj.blockSignals(False)

    def _on_adj_channel_changed(self, ch_x: str, ch_y: str):
        """Mirror channel selection from AF to OLS plot."""
        self._plot_expt.blockSignals(True)
        self._plot_expt.set_channels(ch_x, ch_y)
        self._plot_expt.blockSignals(False)



if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication
    from honeychrome.controller import Controller
    from honeychrome.view_components.event_bus import EventBus
    from pathlib import Path

    app = QApplication(sys.argv)

    controller = Controller()
    bus = EventBus()
    controller.bus = bus
    experiment_name = Path.home() / 'Experiments' / 'AutoSpectral Full Workflow Imported.kit'
    controller.load_experiment(experiment_name)

    controller.load_sample(controller.experiment.samples['single_stain_controls'][-1])

    controller.set_mode('Unmixed Data')
    controller.initialise_data_for_cytometry_plots()
    controller.set_mode(plugin_name)

    widget = PluginWidget(controller=controller, bus=bus)
    widget._on_mode_change(plugin_name)
    widget.show()


    sys.exit(app.exec())
