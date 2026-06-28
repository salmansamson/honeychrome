"""
Honeychrome Plugin
Compare transforms tab
---------------------------
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QPushButton, QLabel, QComboBox
from PySide6.QtCore import Qt

plugin_name = 'Compare Transforms Plugin'



class AfComparisonPlotWidget(QWidget):
    """
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
    # Emitted when a zoom/scaling is applied on one axis, so the sibling can mirror.
    scalingChanged = Signal(str, object)  # (axis_name, Transform)

    def __init__(self, title: str, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self._title_text = title

        # Local copies of Transform objects (not shared with Unmixed Data tab)
        self._transformations: dict[str, Transform] = {}
        # Event data for this plot (full array, gate mask applied only for display)
        self._event_data: np.ndarray | None = None
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
        self._status_label = QLabel('', alignment=Qt.AlignCenter)
        self._status_label.setStyleSheet('color: #aaaaaa;')

        main_layout.addWidget(self.graphics_widget)
        main_layout.addWidget(self._status_label)

        # Axis label left-click: change channel
        self.label_x.leftClickMenuFunction = self._set_channel_x
        self.label_y.leftClickMenuFunction = self._set_channel_y

        # Title left-click: change source gate
        self.plot_title.leftClickMenuFunction = self._set_source_gate

        self.setMinimumHeight(280)
        self.setMinimumWidth(280)

    # ------------------------------------------------------------------
    # Square aspect ratio — always keeps width == height
    # ------------------------------------------------------------------

    def sizeHint(self):
        from PySide6.QtCore import QSize
        side = max(self.minimumHeight(), self.width())
        return QSize(side, side)

    def resizeEvent(self, event):
        # Force square: set height to match width, clamped to minimum
        side = max(self.minimumHeight(), event.size().width())
        if self.height() != side:
            self.setFixedHeight(side)
        super().resizeEvent(event)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_status(self, text: str):
        self._status_label.setText(text)

    def set_event_data(self, event_data: np.ndarray | None):
        """Set the full (ungated) unmixed event array for this plot."""
        self._event_data = event_data

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

    def set_channels(self, channel_x: str, channel_y: str):
        """Change the displayed channels and reconfigure axes."""
        self._channel_x = channel_x
        self._channel_y = channel_y
        self._configure_axes()
        self._draw()

    def set_scaling(self, axis_name: str, tr):
        """
        Mirror scaling/zoom from the sibling plot.
        tr is the Transform object that was already modified by the sibling's _apply_zoom.
        We copy its parameters into our own Transform and update the view accordingly.
        """
        if axis_name == 'x':
            channel = self._channel_x
            axis = self.axis_bottom
            vb_set_range = self.vb.setXRange
        else:
            channel = self._channel_y
            axis = self.axis_left
            vb_set_range = self.vb.setYRange

        if channel not in self._transformations:
            return

        my_tr = self._transformations[channel]
        # Copy the transform state from the sibling
        my_tr.id = tr.id
        my_tr.logicle_w = tr.logicle_w
        my_tr.logicle_a = tr.logicle_a
        my_tr.limits = tr.limits
        my_tr.set_transform(my_tr.id, my_tr.limits)

        vb_set_range(*my_tr.limits, padding=0)
        axis.zoomZero = my_tr.zero
        axis.limits = my_tr.limits
        axis.setTicks(my_tr.ticks())
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
        self._event_data = None
        self._status_label.setText('')

    # ------------------------------------------------------------------
    # Internal: axis configuration
    # ------------------------------------------------------------------

    def _configure_axes(self):
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

    # ------------------------------------------------------------------
    # Internal: drawing
    # ------------------------------------------------------------------

    def _draw(self):
        if self._event_data is None:
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
        event_data = self._event_data

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
            logger.error(f'AfComparisonPlotWidget._draw histogram failed: {e}')
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
        self.scalingChanged.emit(axis_name, tr)

    # ------------------------------------------------------------------
    # Slot: channel changed via label click
    # ------------------------------------------------------------------

    def _set_channel_x(self, n, _parent):
        pnn = self.controller.experiment.settings['unmixed'].get('event_channels_pnn', [])
        fl_ids = self.controller.experiment.settings['unmixed'].get('fluorescence_channel_ids', [])
        fl_names = [pnn[i] for i in fl_ids] if pnn and fl_ids else []
        if 0 <= n < len(fl_names):
            self._channel_x = fl_names[n]
            self._configure_axes()
            self._draw()
            self.channelChanged.emit(self._channel_x, self._channel_y)

    def _set_channel_y(self, n, _parent):
        pnn = self.controller.experiment.settings['unmixed'].get('event_channels_pnn', [])
        fl_ids = self.controller.experiment.settings['unmixed'].get('fluorescence_channel_ids', [])
        fl_names = [pnn[i] for i in fl_ids] if pnn and fl_ids else []
        if 0 <= n < len(fl_names):
            self._channel_y = fl_names[n]
            self._configure_axes()
            self._draw()
            self.channelChanged.emit(self._channel_x, self._channel_y)

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

        overall_layout = QVBoxLayout(self)
        overall_layout.addWidget(scroll)


        # --- Add some GUI elements to show functionality ---
        self.label = QLabel('Compare channel transforms in unmixed plots.')
        self.label.setTextFormat(Qt.RichText)
        self.label.setWordWrap(True)

        # Add gate selection combobox
        self.plot_combo = QComboBox()
        self.plot_combo.addItem("Select Unmixed Plot:")

        main_layout.addWidget(self.label)
        main_layout.addWidget(self.plot_combo)


        self.refresh()

    def refresh(self):
        # put some data from the controller into the label
        import json

        self.label.setText(f'''
        <h1>Hello world!</h1>
        
        <p>Cytometry data can be accessed from the controller object (and the experiment object from controller.experiment):</p>
        
        <ul>
            <li> controller.experiment_dir: <pre>{self.controller.experiment_dir}</pre> </li>
            <li> controller.current_sample_path: <pre>{self.controller.current_sample_path}</pre> </li>
            <li> controller.expreriment.samples: <pre>{json.dumps(self.controller.experiment.samples, indent=2)}</pre> </li>
        </ul>
        ''')
