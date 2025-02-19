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

    def __init__(self, cfg, profile_id, stdout_capture, mutex):
        super().__init__()
        self.cfg = cfg
        self.profile_id = profile_id
        self.signals = WorkerSignals()
        self.mutex = mutex
        self.stdout_capture = stdout_capture  # Capture sys.stdout

    @pyqtSlot()
    def run(self):
        """Execute the function in the worker thread."""
        try:
            self.mutex.lock()

            sys.stdout = self.stdout_capture

            backintime.snapshotStatus(args=None, cfg=self.cfg, profile_id=self.profile_id)
            self.signals.result.emit(self.stdout_capture.getvalue())
        except Exception as e:
            # Handle any other exceptions here
            traceback.print_exc()
            self.signals.error.emit((str(e),))
        finally:
            # Always release the mutex after execution
            self.mutex.unlock()

class SnapshotStatus(QWidget):
    feed = pyqtSignal(object)
    def __init__(self):
        super().__init__()
        layout = QHBoxLayout()
        self.setLayout(layout)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        layout.addWidget(self.text_edit)
        # self.feed = pyqtSignal(object)
        self.feed.connect(self.update_text)
        
    def update_text(self, text):
        """Appends the new text to the existing content in the text edit."""
        current_text = self.text_edit.toPlainText()  # Get the current text
        summary = ''
        lines = text.splitlines()
        for line in lines:
            print(line)
            if line.startswith('   Snap'):
                break
            summary += f"{line}\n"
        summary += '\n'
        updated_text = current_text + "\n" + summary   # Append the new text with a newline
        self.text_edit.setText(updated_text)
        sys.stdout.flush()  # Flush the buffer to update the text edit
        
class SnapshotSummary(QWidget):
    def __init__(self, cfg, profile, mutex, status_feed):
        super().__init__()
        layout = QHBoxLayout()
        self.setLayout(layout)
        self.mutex = mutex
        self.status_feed = status_feed
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        layout.addWidget(self.text_edit)

        self.threadpool = QThreadPool.globalInstance()  # Manage multiple workers

        self.start_worker(cfg, profile)

    def start_worker(self, cfg, profile):
        """Starts the worker thread and connects signals."""
        self.stdout_capture = io.StringIO()
        
        worker = Worker(cfg, profile, self.stdout_capture, self.mutex)
        worker.signals.result.connect(self.update_text)
        worker.signals.result.connect(self.status_feed)
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
        mutex = QMutex()
        status_tab = SnapshotStatus()
        tabs.addTab(status_tab, _('Summary'))
        for profile in self.config.profiles():
            tabs.addTab(SnapshotSummary(self.config, profile, mutex, status_tab.feed), self.config.profileName(profile))   
            
        self.layout = QVBoxLayout()
        self.layout.addWidget(tabs)
        self.setLayout(self.layout)
        # self.setCentralWidget(tabs)

        buttonBox = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.layout.addWidget(buttonBox)
        buttonBox.rejected.connect(self.close)
