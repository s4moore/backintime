import sys, traceback, io

from PyQt6.QtCore import QFileSystemWatcher, pyqtSlot, QObject, pyqtSignal, QRunnable, QThreadPool, QMutex
import qttools
import snapshots
import encfstools
import snapshotlog
import tools
import backintime
import qttools
from statedata import StateData
from PyQt6.QtWidgets import (
    QApplication, 
    QMainWindow, 
    QPushButton, 
    QDialog, 
    QDialogButtonBox, 
    QVBoxLayout, 
    QLabel,
    QTabWidget,
    QWidget,
    QHBoxLayout,
    QLineEdit,
    QTextEdit
)
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtCore import Qt

# class WorkerSignals(QObject):
#     """Signals from a running worker thread.

#     finished
#         No data

#     error
#         tuple (exctype, value, traceback.format_exc())

#     result
#         object data returned from processing, anything

#     progress
#         float indicating % progress
#     """

#     finished = pyqtSignal()
#     error = pyqtSignal(tuple)
#     result = pyqtSignal(object)
#     progress = pyqtSignal(float)

# from PyQt5.QtCore import QRunnable, QThreadPool, pyqtSlot, QObject, pyqtSignal
# from PyQt5.QtWidgets import QWidget, QHBoxLayout, QTextEdit
# import io
# import sys
# import traceback
# import backintime  # Assuming this is the correct import

class WorkerSignals(QObject):
    """Defines signals available from a running worker thread."""
    finished = pyqtSignal()
    error = pyqtSignal(tuple)
    result = pyqtSignal(object)


class Worker(QRunnable):
    """Worker thread that runs snapshotStatus in a separate thread."""

    mutex = QMutex()  # Create a shared mutex for synchronization

    def __init__(self, cfg, profile_id, stdout_capture):
        super().__init__()
        self.cfg = cfg
        self.profile_id = profile_id
        self.signals = WorkerSignals()
        self.stdout_capture = stdout_capture  # Capture sys.stdout

    @pyqtSlot()
    def run(self):
        """Execute the function in the worker thread."""
        try:
            # Try to acquire the mutex to ensure only one thread runs snapshotStatus at a time
            if Worker.mutex.tryLock():
                try:
                    # Redirect stdout to capture
                    sys.stdout = self.stdout_capture

                    # Run the snapshotStatus function
                    result = backintime.snapshotStatus(args=None, cfg=self.cfg, profile_id=self.profile_id)
                finally:
                    # Always release the mutex after execution
                    Worker.mutex.unlock()
            else:
                # If the mutex is already locked, you can emit a message or handle as needed
                self.signals.error.emit(("Mutex is already locked",))

        except Exception:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            # Emit the captured output when result is available
            self.signals.result.emit(self.stdout_capture.getvalue())
        finally:
            # Ensure the capture is cleaned up
            self.signals.finished.emit()
            sys.stdout = sys.__stdout__  # Reset stdout to original

class SnapshotSummary(QWidget):
    def __init__(self, cfg, profile):
        super().__init__()
        layout = QHBoxLayout()
        self.setLayout(layout)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        layout.addWidget(self.text_edit)

        self.threadpool = QThreadPool.globalInstance()  # Manage multiple workers

        self.start_worker(cfg, profile)

    def start_worker(self, cfg, profile):
        """Starts the worker thread and connects signals."""
        self.stdout_capture = io.StringIO()
        
        worker = Worker(cfg, profile, self.stdout_capture)
        worker.signals.result.connect(self.update_text)
        worker.signals.error.connect(self.handle_error)
        worker.signals.finished.connect(self.on_worker_finished)

        self.threadpool.start(worker)  # Runs the worker in a thread

    def update_text(self, text):
        """Updates the text edit with output from the worker."""
        self.text_edit.setText(text)

    def handle_error(self, error):
        """Handles errors from the worker thread."""
        exctype, value, traceback_str = error
        self.text_edit.setText(f"Error: {value}\n{traceback_str}")

    def on_worker_finished(self):
        """Cleans up when the worker finishes."""
        pass  # No action needed now since we handle everything via signals



class StatusViewDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)

        self.config = parent.config
        self.snapshots = parent.snapshots
        self.mainWindow = parent
        self.enableUpdate = False
        self.decode = None

        state_data = StateData()
        self.resize(*state_data.logview_dims)

        import icon
        self.setWindowIcon(icon.VIEW_SNAPSHOT_LOG)
        self.setWindowTitle(_('Snapshot status'))

        tabs = QTabWidget()
        tabs.setTabPosition(QTabWidget.TabPosition.North)
        tabs.setMovable(True)

        tabs.addTab(SnapshotSummary(self.config, None), _('Summary'))
        for profile in self.config.profiles():
            tabs.addTab(SnapshotSummary(self.config, profile), self.config.profileName(profile))   
            
        self.layout = QVBoxLayout()
        self.layout.addWidget(tabs)
        self.setLayout(self.layout)
        # self.setCentralWidget(tabs)

        buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.layout.addWidget(buttonBox)
        buttonBox.rejected.connect(self.close)
