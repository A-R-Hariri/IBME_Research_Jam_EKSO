import os

os.environ.setdefault("PYQTGRAPH_QT_LIB", "PySide6")

import sys
from collections import deque
from multiprocessing.connection import Client

import pyqtgraph as pg
import serial.tools.list_ports
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton,
    QSpinBox, QVBoxLayout, QWidget,
)

from dataport import (
    add_cmd, CMD_cancel_action, CMD_DataLogger, CMD_get_date, CMD_get_feedback,
    CMD_get_settings, CMD_get_state_data, CMD_get_step_ready_status,
    CMD_get_time, CMD_request_action, CMD_set_value,
)
from serial_port import CMD_SerialPort

SERVER_ADDRESS = ("localhost", 6000)
SERVER_AUTHKEY = b"secret password"

DEFAULT_CSV = "ekso_data.csv"

N_CHANNELS = 27

# Replace these once the frame layout of CMD_GET_DATA is confirmed.
CHANNEL_NAMES = ["ch{:02d}".format(i) for i in range(N_CHANNELS)]

# CMD_get_datalog runs at DATA_LOGGING_PERIOD_MSEC = 20, so 50 rows/sec.
POLL_PERIOD_MS = 50
DEFAULT_BUFFER_SAMPLES = 500

PLOT_PENS = ["#378ADD", "#1D9E75", "#D85A30"]


class CsvTail:
    """Incremental reader for a CSV another process is appending to."""

    def __init__(self, path):
        self.path = path
        self.fh = None
        self.partial = ""

    def start(self, from_end=True):
        self.fh = open(self.path, "r")
        if from_end:
            self.fh.seek(0, os.SEEK_END)
        self.partial = ""

    def read_rows(self):
        rows = []
        if self.fh is None:
            return rows

        chunk = self.fh.read()
        if not chunk:
            return rows

        self.partial += chunk
        while "\n" in self.partial:
            line, self.partial = self.partial.split("\n", 1)
            line = line.strip().rstrip(",")
            if not line:
                continue
            parts = line.split(",")
            if len(parts) != N_CHANNELS:
                continue
            try:
                rows.append([int(p) for p in parts])
            except ValueError:
                continue
        return rows

    def stop(self):
        if self.fh is not None:
            self.fh.close()
        self.fh = None


class ChannelDialog(QDialog):
    """Pick exactly 3 of the 27 logged columns."""

    REQUIRED = 3

    def __init__(self, preset=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select channels to plot")

        self.boxes = []
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        for i, name in enumerate(CHANNEL_NAMES):
            box = QCheckBox("{:02d}  {}".format(i, name))
            box.stateChanged.connect(self._update_state)
            self.boxes.append(box)
            grid.addWidget(box, i % 9, i // 9)

        if preset:
            for i in preset:
                if 0 <= i < N_CHANNELS:
                    self.boxes[i].setChecked(True)

        self.count_label = QLabel()
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(grid)
        layout.addWidget(self.count_label)
        layout.addWidget(self.buttons)

        self._update_state()

    def _update_state(self):
        n = len(self.selected())
        self.count_label.setText("Selected: {} of {}".format(n, self.REQUIRED))
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(n == self.REQUIRED)

    def selected(self):
        return [i for i, b in enumerate(self.boxes) if b.isChecked()]


class SetValueDialog(QDialog):
    """Replacement for the two blocking input() calls in menu.py option 5."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set value")

        self.id_spin = QSpinBox()
        self.id_spin.setRange(200, 219)
        self.id_spin.setValue(200)

        self.val_spin = QDoubleSpinBox()
        self.val_spin.setRange(-32768.0, 32767.0)
        self.val_spin.setDecimals(2)
        self.val_spin.setValue(0.0)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout(self)
        form.addRow("Parameter ID", self.id_spin)
        form.addRow("Value", self.val_spin)
        form.addRow(buttons)

    def values(self):
        return self.id_spin.value(), self.val_spin.value()


class PlotWindow(QMainWindow):
    """Rolling plot of 3 selected columns, fed by tailing the CSV."""

    def __init__(self, csv_path, channels, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Data stream: " + os.path.basename(csv_path))
        self.resize(900, 640)

        self.channels = list(channels)
        self.tail = CsvTail(csv_path)
        self.sample_index = 0
        self.rows_since_tick = 0

        self.buffer_spin = QSpinBox()
        self.buffer_spin.setRange(50, 20000)
        self.buffer_spin.setSingleStep(50)
        self.buffer_spin.setValue(DEFAULT_BUFFER_SAMPLES)
        self.buffer_spin.valueChanged.connect(self._resize_buffers)

        self.pause_box = QCheckBox("Pause")
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self._clear)

        self.rate_label = QLabel("0 rows/s")
        self.total_label = QLabel("0 samples")

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Window (samples)"))
        controls.addWidget(self.buffer_spin)
        controls.addWidget(self.pause_box)
        controls.addWidget(self.clear_button)
        controls.addStretch(1)
        controls.addWidget(self.rate_label)
        controls.addWidget(self.total_label)

        pg.setConfigOptions(antialias=True, background=None, foreground="k")
        self.graphics = pg.GraphicsLayoutWidget()

        self.x_buf = deque(maxlen=self.buffer_spin.value())
        self.y_bufs = []
        self.curves = []
        first_plot = None
        for row, ch in enumerate(self.channels):
            plot = self.graphics.addPlot(row=row, col=0)
            plot.showGrid(x=True, y=True, alpha=0.25)
            plot.setLabel("left", "{:02d} {}".format(ch, CHANNEL_NAMES[ch]))
            if first_plot is None:
                first_plot = plot
            else:
                plot.setXLink(first_plot)
            if row == len(self.channels) - 1:
                plot.setLabel("bottom", "sample")
            self.curves.append(plot.plot(pen=pg.mkPen(PLOT_PENS[row], width=1.5)))
            self.y_bufs.append(deque(maxlen=self.buffer_spin.value()))

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addLayout(controls)
        layout.addWidget(self.graphics, 1)
        self.setCentralWidget(central)

        self.tail.start(from_end=True)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(POLL_PERIOD_MS)

        self.rate_timer = QTimer(self)
        self.rate_timer.timeout.connect(self._update_rate)
        self.rate_timer.start(1000)

    def _resize_buffers(self, n):
        self.x_buf = deque(self.x_buf, maxlen=n)
        self.y_bufs = [deque(b, maxlen=n) for b in self.y_bufs]

    def _clear(self):
        self.x_buf.clear()
        for b in self.y_bufs:
            b.clear()
        self._redraw()

    def _poll(self):
        rows = self.tail.read_rows()
        if not rows:
            return

        self.rows_since_tick += len(rows)
        for row in rows:
            self.sample_index += 1
            self.x_buf.append(self.sample_index)
            for k, ch in enumerate(self.channels):
                self.y_bufs[k].append(row[ch])

        if not self.pause_box.isChecked():
            self._redraw()

    def _redraw(self):
        xs = list(self.x_buf)
        for curve, buf in zip(self.curves, self.y_bufs):
            curve.setData(xs, list(buf))

    def _update_rate(self):
        self.rate_label.setText("{} rows/s".format(self.rows_since_tick))
        self.total_label.setText("{} samples".format(self.sample_index))
        self.rows_since_tick = 0

    def closeEvent(self, event):
        self.timer.stop()
        self.rate_timer.stop()
        self.tail.stop()
        super().closeEvent(event)


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ekso dataport")
        self.resize(560, 780)

        self.conn = None
        self.plot_window = None
        self.last_channels = [0, 1, 2]

        central = QWidget()
        root = QVBoxLayout(central)
        root.addWidget(self._build_server_group())
        root.addWidget(self._build_port_group())
        root.addWidget(self._build_logger_group())
        root.addWidget(self._build_command_group())
        root.addWidget(self._build_stream_group())
        root.addWidget(self._build_log_view(), 1)
        self.setCentralWidget(central)

        self.refresh_ports()
        self._set_connected(False)

    def _build_server_group(self):
        group = QGroupBox("Server")
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.connect_server)
        self.shutdown_button = QPushButton("Shut down server")
        self.shutdown_button.clicked.connect(self.shutdown_server)
        self.server_label = QLabel("not connected")

        layout = QHBoxLayout(group)
        layout.addWidget(self.connect_button)
        layout.addWidget(self.shutdown_button)
        layout.addWidget(self.server_label, 1)
        return group

    def _build_port_group(self):
        group = QGroupBox("Serial port")
        self.port_combo = QComboBox()
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_ports)
        self.open_port_button = QPushButton("Open")
        self.open_port_button.clicked.connect(self.open_port)
        self.close_port_button = QPushButton("Close")
        self.close_port_button.clicked.connect(self.close_port)

        layout = QHBoxLayout(group)
        layout.addWidget(self.port_combo, 1)
        layout.addWidget(self.refresh_button)
        layout.addWidget(self.open_port_button)
        layout.addWidget(self.close_port_button)
        return group

    def _build_logger_group(self):
        group = QGroupBox("Log file")
        self.csv_edit = QLineEdit(DEFAULT_CSV)
        self.open_log_button = QPushButton("Open")
        self.open_log_button.clicked.connect(self.open_log)
        self.close_log_button = QPushButton("Close")
        self.close_log_button.clicked.connect(self.close_log)

        layout = QHBoxLayout(group)
        layout.addWidget(self.csv_edit, 1)
        layout.addWidget(self.open_log_button)
        layout.addWidget(self.close_log_button)
        return group

    def _build_command_group(self):
        group = QGroupBox("Commands")
        grid = QGridLayout(group)

        entries = [
            ("Get time", lambda: self.queue(CMD_get_time, [None])),
            ("Get date", lambda: self.queue(CMD_get_date, [None])),
            ("Get settings", lambda: self.queue(CMD_get_settings, [None])),
            ("Get feedback", lambda: self.queue(CMD_get_feedback, [None])),
            ("Set value", self.set_value),
            ("Cancel action", lambda: self.queue(CMD_cancel_action, [None])),
            ("Walk (take step)", lambda: self.queue(CMD_request_action, ["walk"])),
            ("Get state data", lambda: self.queue(CMD_get_state_data, [None])),
            ("Get step ready", lambda: self.queue(CMD_get_step_ready_status, [None])),
        ]

        self.command_buttons = []
        for i, (label, slot) in enumerate(entries):
            button = QPushButton(label)
            button.clicked.connect(slot)
            grid.addWidget(button, i // 3, i % 3)
            self.command_buttons.append(button)
        return group

    def _build_stream_group(self):
        group = QGroupBox("Data")
        self.start_stream_button = QPushButton("Start stream")
        self.start_stream_button.clicked.connect(self.start_stream)
        self.stop_stream_button = QPushButton("Stop stream")
        self.stop_stream_button.clicked.connect(self.stop_stream)
        self.start_push_button = QPushButton("Start push data")
        self.start_push_button.clicked.connect(self.start_push)
        self.stop_push_button = QPushButton("Stop push data")
        self.stop_push_button.clicked.connect(self.stop_push)

        layout = QGridLayout(group)
        layout.addWidget(self.start_stream_button, 0, 0)
        layout.addWidget(self.stop_stream_button, 0, 1)
        layout.addWidget(self.start_push_button, 1, 0)
        layout.addWidget(self.stop_push_button, 1, 1)
        return group

    def _build_log_view(self):
        group = QGroupBox("Sent")
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Consolas", 9))
        self.log_view.setPlainText(
            "Command responses print in the server.py console, not here.\n"
        )
        layout = QVBoxLayout(group)
        layout.addWidget(self.log_view)
        return group

    def log(self, text):
        self.log_view.appendPlainText(text)

    def _set_connected(self, state):
        for widget in (
            self.shutdown_button, self.open_port_button, self.close_port_button,
            self.open_log_button, self.close_log_button,
            self.start_stream_button, self.stop_stream_button,
            self.start_push_button, self.stop_push_button,
        ):
            widget.setEnabled(state)
        for button in self.command_buttons:
            button.setEnabled(state)
        self.connect_button.setEnabled(not state)
        self.server_label.setText(
            "connected to {}:{}".format(*SERVER_ADDRESS) if state
            else "not connected"
        )

    def connect_server(self):
        try:
            self.conn = Client(SERVER_ADDRESS, authkey=SERVER_AUTHKEY)
        except Exception as exc:
            self.conn = None
            QMessageBox.critical(
                self, "Connection failed",
                "{}\n\nStart server.py first.".format(exc),
            )
            return
        self.log("connected")
        self._set_connected(True)

    def send(self, message):
        if self.conn is None:
            QMessageBox.warning(self, "Not connected", "Connect to the server first.")
            return False
        try:
            self.conn.send(message)
        except Exception as exc:
            self.conn = None
            self._set_connected(False)
            QMessageBox.critical(self, "Send failed", str(exc))
            return False
        return True

    def queue(self, func, args):
        """Server-side queued execution, matching menu.py."""
        if self.send([add_cmd, [func, args]]):
            self.log("queue {}({})".format(func.__name__, args))

    def direct(self, func, args):
        """Server-side immediate execution, matching console.py."""
        if self.send([func, args]):
            self.log("direct {}({})".format(func.__name__, args))

    def refresh_ports(self):
        self.port_combo.clear()
        for port in serial.tools.list_ports.comports():
            self.port_combo.addItem(
                "{}  {}".format(port.device, port.description), port.device
            )
        if self.port_combo.count() == 0:
            self.port_combo.addItem("no ports found", None)

    def open_port(self):
        device = self.port_combo.currentData()
        if not device:
            QMessageBox.warning(self, "No port", "No serial port selected.")
            return
        self.direct(CMD_SerialPort, ["open", device])

    def close_port(self):
        self.direct(CMD_SerialPort, ["close", None])

    def open_log(self):
        name = self.csv_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "No file", "Enter a log file name.")
            return
        self.direct(CMD_DataLogger, ["open", name])

    def close_log(self):
        self.direct(CMD_DataLogger, ["close", None])

    def set_value(self):
        dialog = SetValueDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        param_id, value = dialog.values()
        self.queue(CMD_set_value, [param_id, value])

    def start_stream(self):
        path = self.csv_edit.text().strip()
        if not os.path.exists(path):
            QMessageBox.warning(
                self, "No log file",
                "{} does not exist yet. Open the log file first.".format(path),
            )
            return

        dialog = ChannelDialog(preset=self.last_channels, parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        self.last_channels = dialog.selected()

        self.queue(CMD_DataLogger, ["start"])

        if self.plot_window is not None:
            self.plot_window.close()
        self.plot_window = PlotWindow(path, self.last_channels, parent=self)
        self.plot_window.setWindowFlag(Qt.Window, True)
        self.plot_window.show()

    def stop_stream(self):
        self.queue(CMD_DataLogger, ["stop"])

    def start_push(self):
        self.queue(CMD_DataLogger, ["start_read_push"])

    def stop_push(self):
        self.queue(CMD_DataLogger, ["stop_read_push"])

    def shutdown_server(self):
        if self.conn is None:
            return
        try:
            self.conn.send("close_server")
            self.conn.close()
        except Exception:
            pass
        self.conn = None
        self._set_connected(False)
        self.log("server shut down")

    def closeEvent(self, event):
        if self.plot_window is not None:
            self.plot_window.close()
        if self.conn is not None:
            try:
                self.conn.send([CMD_DataLogger, ["close", None]])
                self.conn.send([CMD_SerialPort, ["close", None]])
                self.conn.send("close_server")
                self.conn.close()
            except Exception:
                pass
            self.conn = None
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setPalette(app.style().standardPalette())
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
