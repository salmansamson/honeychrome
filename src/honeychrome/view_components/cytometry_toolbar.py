
from PySide6.QtGui import QAction, QPalette
from PySide6.QtWidgets import QToolBar

from view_components.icon_loader import icon


class CytometryToolbar(QToolBar):
    def __init__(self, bus, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bus = bus
        self.setMovable(False)
        self.action_add_plot = QAction(icon('plus'), "Add Plot", self)
        self.action_delete_plot = QAction(icon('x'), "Delete Plot", self)
        self.action_toggle_gating_hierarchy = QAction(icon('binary-tree'), "Toggle Gating Hierarchy", self)
        self.action_toggle_gating_hierarchy.setCheckable(True)
        self.action_move_to_start = QAction(icon('chevrons-left'), "Move Plot to Start", self)
        self.action_move_left = QAction(icon('chevron-left'), "Move Plot Left", self)
        self.action_move_right = QAction(icon('chevron-right'), "Move Plot Right", self)
        self.action_move_to_end = QAction(icon('chevrons-right'), "Move Plot to End", self)
        self.action_range_gate = QAction(icon('tallymark-2'), "Add Range Gate (1D histograms only)", self)
        self.action_rectangle_gate = QAction(icon('rectangle'), "Add Rectangle Gate (2D histograms only)", self)
        self.action_polygon_gate = QAction(icon('polygon'), "Add Polygon Gate (2D histograms only)", self)
        self.action_ellipse_gate = QAction(icon('oval-vertical'), "Add Ellipse Gate (2D histograms only)", self)
        self.action_quadrant_gates = QAction(icon('border-all'), "Add Quadrant Gates (2D histograms only)", self)
        self.addAction(self.action_add_plot)
        self.addAction(self.action_delete_plot)
        self.addAction(self.action_toggle_gating_hierarchy)
        self.addSeparator()
        self.addAction(self.action_move_to_start)
        self.addAction(self.action_move_left)
        self.addAction(self.action_move_right)
        self.addAction(self.action_move_to_end)
        self.addSeparator()
        self.addAction(self.action_range_gate)
        self.addAction(self.action_rectangle_gate)
        self.addAction(self.action_polygon_gate)
        self.addAction(self.action_ellipse_gate)
        self.addAction(self.action_quadrant_gates)

        grid_widget = self.parent()
        self.action_add_plot.triggered.connect(grid_widget.show_new_plot_widget)
        self.action_delete_plot.triggered.connect(grid_widget.delete_current_plot)
        self.action_toggle_gating_hierarchy.triggered.connect(grid_widget.gating_tree.toggle)
        self.action_move_to_start.triggered.connect(lambda: grid_widget.permute_plot_widgets('start'))
        self.action_move_left.triggered.connect(lambda: grid_widget.permute_plot_widgets('left'))
        self.action_move_right.triggered.connect(lambda: grid_widget.permute_plot_widgets('right'))
        self.action_move_to_end.triggered.connect(lambda: grid_widget.permute_plot_widgets('end'))
        self.action_range_gate.triggered.connect(lambda: grid_widget.selected_plot.new_range_gate())
        self.action_rectangle_gate.triggered.connect(lambda: grid_widget.selected_plot.new_rectangle_gate())
        self.action_polygon_gate.triggered.connect(lambda: grid_widget.selected_plot.initiate_polygon_roi())
        self.action_ellipse_gate.triggered.connect(lambda: grid_widget.selected_plot.new_ellipse_gate())
        self.action_quadrant_gates.triggered.connect(lambda: grid_widget.selected_plot.new_quadrant_gate())


        # Adaptive stylesheet
        palette = self.palette()
        base = palette.color(QPalette.ColorRole.Base)
        is_dark = base.value() < 128

        # Define line color depending on theme
        line_color = "rgba(255, 255, 255, 60%)" if is_dark else "rgba(0, 0, 0, 25%)"

        self.setStyleSheet(f"""
            QToolBar {{
                background: transparent;
                spacing: 14px;
            }}
            QToolBar::separator {{
                width: 2px;
                background: {line_color};
                margin: 1px 18px;
                border-radius: 1px;
            }}
        """)

        self.update_button_state(None)

    def update_button_state(self, type):
        if type is None:
            self.action_add_plot.setVisible(True)
            self.action_delete_plot.setVisible(False)
            self.action_move_to_start.setVisible(False)
            self.action_move_left.setVisible(False)
            self.action_move_right.setVisible(False)
            self.action_move_to_end.setVisible(False)
            self.action_range_gate.setVisible(False)
            self.action_rectangle_gate.setVisible(False)
            self.action_polygon_gate.setVisible(False)
            self.action_ellipse_gate.setVisible(False)
            self.action_quadrant_gates.setVisible(False)
        else:
            self.action_add_plot.setVisible(True)
            self.action_delete_plot.setVisible(True)
            self.action_move_to_start.setVisible(True)
            self.action_move_left.setVisible(True)
            self.action_move_right.setVisible(True)
            self.action_move_to_end.setVisible(True)

            if type == 'ribbon':
                self.action_range_gate.setVisible(False)
                self.action_rectangle_gate.setVisible(False)
                self.action_polygon_gate.setVisible(False)
                self.action_ellipse_gate.setVisible(False)
                self.action_quadrant_gates.setVisible(False)
            elif type == 'hist1d':
                self.action_range_gate.setVisible(True)
                self.action_rectangle_gate.setVisible(False)
                self.action_polygon_gate.setVisible(False)
                self.action_ellipse_gate.setVisible(False)
                self.action_quadrant_gates.setVisible(False)
            elif type == 'hist2d':
                self.action_range_gate.setVisible(False)
                self.action_rectangle_gate.setVisible(True)
                self.action_polygon_gate.setVisible(True)
                self.action_ellipse_gate.setVisible(True)
                self.action_quadrant_gates.setVisible(True)


