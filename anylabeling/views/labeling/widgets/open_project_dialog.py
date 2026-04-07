"""Dialog to pick a subfolder under a project root for labeling."""

import os
import os.path as osp

import natsort
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from anylabeling.views.labeling.utils.theme import get_theme
from anylabeling.views.labeling.utils.style import (
    get_cancel_btn_style,
    get_dialog_style,
    get_ok_btn_style,
)


THUMB_W = 176
THUMB_H = 132
GRID_COLUMNS = 4


def list_immediate_subdirs(project_root: str) -> list[tuple[str, str]]:
    """Return (name, full_path) for each direct child directory, naturally sorted."""
    try:
        names = os.listdir(project_root)
    except OSError:
        return []
    pairs = []
    for name in names:
        full = osp.join(project_root, name)
        if osp.isdir(full):
            pairs.append((name, full))
    return natsort.natsorted(pairs, key=lambda x: x[0])


def _image_extensions() -> tuple[str, ...]:
    return tuple(
        f".{fmt.data().decode().lower()}"
        for fmt in QtGui.QImageReader.supportedImageFormats()
    )


def first_image_in_folder(folder_path: str) -> str | None:
    """First image file found under folder (walk order + sorted names per dir)."""
    ext = _image_extensions()
    for root, _, files in os.walk(folder_path):
        for fname in natsort.natsorted(files):
            if fname.lower().endswith(ext):
                return osp.join(root, fname)
    return None


def load_thumbnail_pixmap(
    image_path: str, max_w: int, max_h: int
) -> QtGui.QPixmap | None:
    reader = QtGui.QImageReader(image_path)
    reader.setAutoTransform(True)
    size = reader.size()
    if not size.isValid():
        return None
    w, h = size.width(), size.height()
    if w <= 0 or h <= 0:
        return None
    scale = min(max_w / w, max_h / h, 1.0)
    nw = max(1, int(w * scale))
    nh = max(1, int(h * scale))
    reader.setScaledSize(QtCore.QSize(nw, nh))
    img = reader.read()
    if img.isNull():
        return None
    return QtGui.QPixmap.fromImage(img)


class FolderBoardCard(QFrame):
    """One subfolder as a card with thumbnail + title."""

    clicked = pyqtSignal(str)
    doubleClicked = pyqtSignal(str)

    def __init__(self, folder_name: str, folder_path: str, parent=None):
        super().__init__(parent)
        self._folder_path = folder_path
        self._selected = False
        self.setObjectName("folderCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.setFixedWidth(THUMB_W + 24)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self._thumb_label = QLabel()
        self._thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb_label.setFixedSize(THUMB_W, THUMB_H)
        self._thumb_label.setScaledContents(False)
        layout.addWidget(self._thumb_label, alignment=Qt.AlignmentFlag.AlignCenter)

        self._title_label = QLabel(folder_name)
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_label.setWordWrap(True)
        self._title_label.setMaximumWidth(THUMB_W + 16)
        fm = self._title_label.fontMetrics()
        self._title_label.setMaximumHeight(fm.lineSpacing() * 2 + 4)
        layout.addWidget(self._title_label)

        self.setToolTip(folder_path)
        self._apply_style()

    @property
    def folder_path(self) -> str:
        return self._folder_path

    def set_thumbnail(self, pix: QtGui.QPixmap | None) -> None:
        t = get_theme()
        self._thumb_label.setStyleSheet("")
        if pix is None or pix.isNull():
            empty = QtGui.QPixmap(THUMB_W, THUMB_H)
            empty.fill(QtGui.QColor(t["surface"]))
            self._thumb_label.setPixmap(empty)
        else:
            self._thumb_label.setPixmap(pix)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._apply_style()

    def _apply_style(self) -> None:
        t = get_theme()
        if self._selected:
            border = f"2px solid {t['selection']}"
            bg = t["background_secondary"]
        else:
            border = f"1px solid {t['border_light']}"
            bg = t["background_secondary"]
        self.setStyleSheet(
            f"""
            QFrame#folderCard {{
                background: {bg};
                border: {border};
                border-radius: 12px;
            }}
            QFrame#folderCard:hover {{
                background: {t["surface_hover"]};
            }}
            """
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._folder_path)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.doubleClicked.emit(self._folder_path)
        super().mouseDoubleClickEvent(event)


class OpenProjectDialog(QDialog):
    """Shows subfolders of ``project_root`` as thumbnail cards."""

    def __init__(self, project_root: str, parent=None):
        super().__init__(parent)
        self._project_root = osp.normpath(osp.abspath(project_root))
        self.selected_path: str | None = None
        self._cards: list[FolderBoardCard] = []
        self._selected_folder: str | None = None

        self.setWindowTitle(
            self.tr("Open project — %s")
            % osp.basename(self._project_root)
        )
        self.setMinimumSize(800, 560)
        self.resize(960, 640)
        self.setStyleSheet(get_dialog_style())

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        path_label = QLabel(self.tr("Project root:"))
        path_value = QLabel(self._project_root)
        path_value.setWordWrap(True)
        path_value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(path_label)
        layout.addWidget(path_value)

        hint = QLabel(
            self.tr(
                "Click a folder card to select it (thumbnail = first image inside). "
                "Double-click or Load to open."
            )
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        board_widget = QWidget()
        self._grid = QGridLayout(board_widget)
        self._grid.setSpacing(16)
        self._grid.setContentsMargins(4, 4, 4, 4)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop)

        pairs = list_immediate_subdirs(self._project_root)
        for idx, (name, full) in enumerate(pairs):
            card = FolderBoardCard(name, full, board_widget)
            card.clicked.connect(self._on_card_clicked)
            card.doubleClicked.connect(self._on_card_double_clicked)
            first = first_image_in_folder(full)
            pix = None
            if first:
                pix = load_thumbnail_pixmap(first, THUMB_W, THUMB_H)
            card.set_thumbnail(pix)
            self._cards.append(card)
            row = idx // GRID_COLUMNS
            col = idx % GRID_COLUMNS
            self._grid.addWidget(card, row, col, Qt.AlignmentFlag.AlignTop)
            if idx % 6 == 0:
                QtWidgets.QApplication.processEvents()

        scroll.setWidget(board_widget)
        layout.addWidget(scroll, stretch=1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton(self.tr("Cancel"))
        cancel_btn.setStyleSheet(get_cancel_btn_style())
        cancel_btn.clicked.connect(self.reject)
        load_btn = QPushButton(self.tr("Load"))
        load_btn.setStyleSheet(get_ok_btn_style())
        load_btn.setDefault(True)
        load_btn.clicked.connect(self._accept_selection)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(load_btn)
        layout.addLayout(btn_row)

    def _on_card_clicked(self, path: str) -> None:
        self._selected_folder = path
        for c in self._cards:
            c.set_selected(c.folder_path == path)

    def _on_card_double_clicked(self, path: str) -> None:
        self._selected_folder = path
        for c in self._cards:
            c.set_selected(c.folder_path == path)
        self.selected_path = path
        self.accept()

    def _accept_selection(self):
        if not self._selected_folder:
            QMessageBox.warning(
                self,
                self.tr("No selection"),
                self.tr("Please click a folder card to select."),
            )
            return
        self.selected_path = self._selected_folder
        self.accept()
