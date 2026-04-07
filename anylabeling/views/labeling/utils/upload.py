import json
import jsonlines
import os
import os.path as osp
import shutil
import time
import yaml

from PyQt6 import QtWidgets
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QVBoxLayout,
    QProgressDialog,
)

from anylabeling.views.labeling.label_converter import LabelConverter
from anylabeling.views.labeling.logger import logger
from anylabeling.views.labeling.widgets import Popup
from anylabeling.views.labeling.utils.qt import new_icon_path, scan_all_images
from anylabeling.views.labeling.utils.style import *
from anylabeling.views.labeling.utils.export import _check_filename_exist


def _default_upload_folder_path(self):
    """Prefer cached project upload dir, then project root, then legacy heuristic."""
    cached = getattr(self, "project_upload_annotation_dir", None)
    if cached and osp.isdir(cached):
        return cached
    root = getattr(self, "project_root", None)
    if root and osp.isdir(root):
        return root
    return osp.dirname(osp.dirname(self.filename))


class UploadPPOCRThread(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, converter, input_file, output_path, image_path, mode):
        super().__init__()
        self.converter = converter
        self.input_file = input_file
        self.output_path = output_path
        self.image_path = image_path
        self.mode = mode

    def run(self):
        try:
            time.sleep(1)

            self.converter.ppocr_to_custom(
                input_file=self.input_file,
                output_path=self.output_path,
                image_path=self.image_path,
                mode=self.mode,
            )

            self.finished.emit(True, "")

        except Exception as e:
            self.finished.emit(False, str(e))


class UploadOdvgThread(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, converter, input_file, output_path):
        super().__init__()
        self.converter = converter
        self.input_file = input_file
        self.output_path = output_path

    def run(self):
        try:
            time.sleep(1)

            self.converter.odvg_to_custom(
                input_file=self.input_file,
                output_path=self.output_path,
            )

            self.finished.emit(True, "")

        except Exception as e:
            self.finished.emit(False, str(e))


class UploadMotThread(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, converter, gt_file, output_path, image_path):
        super().__init__()
        self.converter = converter
        self.gt_file = gt_file
        self.output_path = output_path
        self.image_path = image_path

    def run(self):
        try:
            time.sleep(1)

            self.converter.mot_to_custom(
                input_file=self.gt_file,
                output_path=self.output_path,
                image_path=self.image_path,
            )

            self.finished.emit(True, "")

        except Exception as e:
            self.finished.emit(False, str(e))


class UploadCocoThread(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, converter, input_file, output_dir_path, mode):
        super().__init__()
        self.converter = converter
        self.input_file = input_file
        self.output_dir_path = output_dir_path
        self.mode = mode

    def run(self):
        try:
            time.sleep(1)

            self.converter.coco_to_custom(
                input_file=self.input_file,
                output_dir_path=self.output_dir_path,
                mode=self.mode,
            )

            self.finished.emit(True, "")

        except Exception as e:
            self.finished.emit(False, str(e))


def upload_vlm_r1_ovd_annotation(self):
    if not _check_filename_exist(self):
        return

    filter = "Attribute Files (*.jsonl);;All Files (*)"
    input_file, _ = QtWidgets.QFileDialog.getOpenFileName(
        self,
        self.tr("Select a custom vlm_r1_ovd annotation file"),
        "",
        filter,
    )

    if not input_file:
        return

    output_dir_path = osp.dirname(self.filename)
    if self.output_dir:
        output_dir_path = self.output_dir

    response = QtWidgets.QMessageBox()
    response.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    response.setWindowTitle(self.tr("Warning"))
    response.setText(self.tr("Current annotation will be lost"))
    response.setInformativeText(
        self.tr(
            "You are going to upload new annotations to this task. Continue?"
        )
    )
    response.setStandardButtons(
        QtWidgets.QMessageBox.StandardButton.Cancel
        | QtWidgets.QMessageBox.StandardButton.Ok
    )
    response.setStyleSheet(get_msg_box_style())

    if response.exec() != QtWidgets.QMessageBox.StandardButton.Ok:
        return

    image_list = self.image_list if self.image_list else [self.filename]
    progress_dialog = QProgressDialog(
        self.tr("Uploading..."), self.tr("Cancel"), 0, len(image_list), self
    )
    progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
    progress_dialog.setWindowTitle(self.tr("Progress"))
    progress_dialog.setMinimumWidth(500)
    progress_dialog.setMinimumHeight(150)
    progress_dialog.setStyleSheet(
        get_progress_dialog_style(color="#1d1d1f", height=20)
    )

    converter = LabelConverter()

    try:
        # parse input_data
        input_data = {}
        with jsonlines.open(input_file, "r") as reader:
            for data in list(reader):
                image_path = osp.basename(data["image"])
                input_data[image_path] = data["conversations"][1]["value"]

        for i, image_file in enumerate(image_list):
            image_filename = osp.basename(image_file)
            label_filename = osp.splitext(image_filename)[0] + ".json"
            output_file = osp.join(output_dir_path, label_filename)

            converter.vlm_r1_ovd_to_custom(
                input_data=input_data[image_filename],
                output_file=output_file,
                image_file=image_file,
            )

            progress_dialog.setValue(i)
            if progress_dialog.wasCanceled():
                break

        progress_dialog.close()
        template = self.tr(
            "Uploading annotations successfully!\n"
            "Results have been saved to:\n"
            "%s"
        )
        message_text = template % output_dir_path
        popup = Popup(
            message_text,
            self,
            icon=new_icon_path("copy-green", "svg"),
        )
        popup.show_popup(self, popup_height=65, position="center")

        # update and refresh the current canvas
        self.load_file(self.filename)

    except Exception as e:
        progress_dialog.close()
        message = f"Error occurred while uploading annotations: {str(e)}"
        logger.error(message)

        popup = Popup(
            message,
            self,
            icon=new_icon_path("error", "svg"),
        )
        popup.show_popup(self, position="center")


def upload_ppocr_annotation(self, mode):
    if not _check_filename_exist(self):
        return

    if mode == "rec":
        filter = "Attribute Files (*.txt);;All Files (*)"
        input_file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            self.tr("Select a custom annotation file (Label.txt)"),
            "",
            filter,
        )

        if not input_file:
            return

    elif mode == "kie":
        filter = "Attribute Files (*.json);;All Files (*)"
        input_file, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            self.tr("Select a custom annotation file (ppocr_kie.json)"),
            "",
            filter,
        )

        if not input_file:
            return

    response = QtWidgets.QMessageBox()
    response.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    response.setWindowTitle(self.tr("Warning"))
    response.setText(self.tr("Current annotation will be lost"))
    response.setInformativeText(
        self.tr(
            "You are going to upload new annotations to this task. Continue?"
        )
    )
    response.setStandardButtons(
        QtWidgets.QMessageBox.StandardButton.Cancel
        | QtWidgets.QMessageBox.StandardButton.Ok
    )
    response.setStyleSheet(get_msg_box_style())

    if response.exec() != QtWidgets.QMessageBox.StandardButton.Ok:
        return

    progress_dialog = QProgressDialog(
        self.tr("Uploading..."), self.tr("Cancel"), 0, 0, self
    )
    progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
    progress_dialog.setWindowTitle(self.tr("Progress"))
    progress_dialog.setMinimumWidth(500)
    progress_dialog.setMinimumHeight(150)
    progress_dialog.setRange(0, 0)
    progress_dialog.setStyleSheet(get_progress_dialog_style())

    converter = LabelConverter()
    image_path = osp.dirname(self.filename)
    output_path = osp.dirname(self.filename)
    if self.output_dir:
        output_path = self.output_dir
    self.upload_thread = UploadPPOCRThread(
        converter, input_file, output_path, image_path, mode
    )

    def on_upload_finished(success, error_msg):
        progress_dialog.close()
        if success:
            # update and refresh the current canvas
            self.load_file(self.filename)

            popup = Popup(
                self.tr(f"Uploading annotations successfully!"),
                self,
                icon=new_icon_path("copy-green", "svg"),
            )
            popup.show_popup(self, popup_height=65, position="center")
        else:
            message = (
                f"Error occurred while uploading annotations: {str(error_msg)}"
            )
            logger.error(message)
            popup = Popup(
                message,
                self,
                icon=new_icon_path("error", "svg"),
            )
            popup.show_popup(self, position="center")

    self.upload_thread.finished.connect(on_upload_finished)

    progress_dialog.show()
    self.upload_thread.start()

    progress_dialog.canceled.connect(self.upload_thread.terminate)


def upload_odvg_annotation(self):
    if not _check_filename_exist(self):
        return

    filter = "OD Files (*.json *.jsonl);;All Files (*)"
    input_file, _ = QtWidgets.QFileDialog.getOpenFileName(
        self,
        self.tr("Select a specific OD file"),
        "",
        filter,
    )

    if not input_file:
        return

    response = QtWidgets.QMessageBox()
    response.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    response.setWindowTitle(self.tr("Warning"))
    response.setText(self.tr("Current annotation will be lost"))
    response.setInformativeText(
        self.tr(
            "You are going to upload new annotations to this task. Continue?"
        )
    )
    response.setStandardButtons(
        QtWidgets.QMessageBox.StandardButton.Cancel
        | QtWidgets.QMessageBox.StandardButton.Ok
    )
    response.setStyleSheet(get_msg_box_style())

    if response.exec() != QtWidgets.QMessageBox.StandardButton.Ok:
        return

    progress_dialog = QProgressDialog(
        self.tr("Uploading..."), self.tr("Cancel"), 0, 0, self
    )
    progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
    progress_dialog.setWindowTitle(self.tr("Progress"))
    progress_dialog.setMinimumWidth(500)
    progress_dialog.setMinimumHeight(150)
    progress_dialog.setRange(0, 0)
    progress_dialog.setStyleSheet(get_progress_dialog_style())

    converter = LabelConverter()
    output_path = osp.dirname(self.filename)
    if self.output_dir:
        output_path = self.output_dir
    self.upload_thread = UploadOdvgThread(converter, input_file, output_path)

    def on_upload_finished(success, error_msg):
        progress_dialog.close()
        if success:
            # update and refresh the current canvas
            self.load_file(self.filename)

            popup = Popup(
                self.tr(f"Uploading annotations successfully!"),
                self,
                icon=new_icon_path("copy-green", "svg"),
            )
            popup.show_popup(self, popup_height=65, position="center")
        else:
            message = (
                f"Error occurred while uploading annotations: {str(error_msg)}"
            )
            logger.error(message)
            popup = Popup(
                message,
                self,
                icon=new_icon_path("error", "svg"),
            )
            popup.show_popup(self, position="center")

    self.upload_thread.finished.connect(on_upload_finished)

    progress_dialog.show()
    self.upload_thread.start()

    progress_dialog.canceled.connect(self.upload_thread.terminate)


def upload_mmgd_annotation(self, LABEL_OPACITY):
    if not _check_filename_exist(self):
        return

    filter = "Classes Files (*.txt);;All Files (*)"
    classes_file, _ = QtWidgets.QFileDialog.getOpenFileName(
        self,
        self.tr("Select a specific classes file"),
        "",
        filter,
    )
    if not classes_file:
        return

    try:
        with open(classes_file, "r", encoding="utf-8") as f:
            classes = f.read().splitlines()
    except Exception as e:
        popup = Popup(
            self.tr(f"Error reading classes file: {str(e)}"),
            self,
            icon=new_icon_path("error", "svg"),
        )
        popup.show_popup(self, position="center")
        return

    dialog = QtWidgets.QDialog(self)
    dialog.setWindowTitle(self.tr("Upload Options"))
    dialog.setMinimumWidth(500)
    dialog.setStyleSheet(get_export_option_style())

    layout = QVBoxLayout()
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(16)

    folder_layout = QVBoxLayout()
    folder_label = QtWidgets.QLabel(self.tr("Select Upload Folder"))
    folder_layout.addWidget(folder_label)

    folder_input_layout = QHBoxLayout()
    folder_input_layout.setSpacing(8)

    path_edit = QtWidgets.QLineEdit()
    path_edit.setPlaceholderText(
        self.tr("Please select a folder containing annotation files")
    )

    def browse_json_folder():
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            self.tr("Select Upload Folder"),
            None,
            QtWidgets.QFileDialog.Option.ShowDirsOnly
            | QtWidgets.QFileDialog.Option.DontResolveSymlinks
            | QtWidgets.QFileDialog.Option.DontUseNativeDialog,
        )
        if path:
            path_edit.setText(path)

    folder_button = QtWidgets.QPushButton(self.tr("Browse"))
    folder_button.clicked.connect(browse_json_folder)
    folder_button.setStyleSheet(get_cancel_btn_style())

    folder_input_layout.addWidget(path_edit)
    folder_input_layout.addWidget(folder_button)
    folder_layout.addLayout(folder_input_layout)
    layout.addLayout(folder_layout)

    category_layout = QVBoxLayout()
    category_label = QtWidgets.QLabel(self.tr("Category Settings"))
    category_layout.addWidget(category_label)

    scroll_area = QtWidgets.QScrollArea()
    scroll_area.setWidgetResizable(True)
    scroll_area.setMaximumHeight(200)
    scroll_widget = QtWidgets.QWidget()
    scroll_layout = QVBoxLayout(scroll_widget)

    category_widgets = {}
    for i, class_name in enumerate(classes):
        row_layout = QHBoxLayout()

        checkbox = QtWidgets.QCheckBox(class_name)
        checkbox.setChecked(True)

        threshold_label = QtWidgets.QLabel(self.tr("Threshold:"))
        threshold_input = QtWidgets.QDoubleSpinBox()
        threshold_input.setRange(0.0, 1.0)
        threshold_input.setSingleStep(0.01)
        threshold_input.setValue(0.20)
        threshold_input.setDecimals(2)

        row_layout.addWidget(checkbox)
        row_layout.addStretch()
        row_layout.addWidget(threshold_label)
        row_layout.addWidget(threshold_input)

        scroll_layout.addLayout(row_layout)
        category_widgets[class_name] = (checkbox, threshold_input)

    scroll_area.setWidget(scroll_widget)
    category_layout.addWidget(scroll_area)
    layout.addLayout(category_layout)

    button_layout = QHBoxLayout()
    button_layout.setContentsMargins(0, 16, 0, 0)
    button_layout.setSpacing(8)

    cancel_button = QtWidgets.QPushButton(self.tr("Cancel"))
    cancel_button.clicked.connect(dialog.reject)
    cancel_button.setStyleSheet(get_cancel_btn_style())

    ok_button = QtWidgets.QPushButton(self.tr("OK"))

    def on_ok_clicked():
        if not path_edit.text().strip():
            QtWidgets.QMessageBox.warning(
                self,
                self.tr("Warning"),
                self.tr("Upload folder path cannot be empty!"),
            )
            return

        dialog.accept()

    ok_button.clicked.connect(on_ok_clicked)
    ok_button.setStyleSheet(get_ok_btn_style())

    button_layout.addStretch()
    button_layout.addWidget(cancel_button)
    button_layout.addWidget(ok_button)
    layout.addLayout(button_layout)

    dialog.setLayout(layout)
    result = dialog.exec()

    if not result:
        return

    labels = []
    thresholds = {}
    for class_name, (checkbox, threshold_input) in category_widgets.items():
        if checkbox.isChecked():
            labels.append(class_name)
            thresholds[class_name] = threshold_input.value()

    if not labels:
        popup = Popup(
            self.tr("Please select at least one category!"),
            self,
            icon=new_icon_path("warning", "svg"),
        )
        popup.show_popup(self, position="center")
        return

    label_dir_path = path_edit.text()
    image_dir_path = osp.dirname(self.filename)
    image_file_list = os.listdir(image_dir_path)
    label_file_list = os.listdir(label_dir_path)
    output_dir_path = self.output_dir if self.output_dir else image_dir_path
    converter = LabelConverter(classes_file=classes_file)

    response = QtWidgets.QMessageBox()
    response.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    response.setWindowTitle(self.tr("Warning"))
    response.setText(self.tr("Current annotation will be lost"))
    response.setInformativeText(
        self.tr(
            "You are going to upload new annotations to this task. Continue?"
        )
    )
    response.setStandardButtons(
        QtWidgets.QMessageBox.StandardButton.Cancel
        | QtWidgets.QMessageBox.StandardButton.Ok
    )
    response.setStyleSheet(get_msg_box_style())

    if response.exec() != QtWidgets.QMessageBox.StandardButton.Ok:
        return

    progress_dialog = QProgressDialog(
        self.tr("Uploading..."),
        self.tr("Cancel"),
        0,
        len(image_file_list),
        self,
    )
    progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
    progress_dialog.setWindowTitle(self.tr("Progress"))
    progress_dialog.setMinimumWidth(500)
    progress_dialog.setMinimumHeight(150)
    progress_dialog.setStyleSheet(
        get_progress_dialog_style(color="#1d1d1f", height=20)
    )

    try:
        for i, image_filename in enumerate(image_file_list):
            label_filename = osp.splitext(image_filename)[0] + ".json"
            if (
                image_filename.endswith(".json")
                or label_filename not in label_file_list
            ):
                continue

            converter.mmgd_to_custom(
                input_file=osp.join(label_dir_path, label_filename),
                output_file=osp.join(output_dir_path, label_filename),
                image_file=osp.join(image_dir_path, image_filename),
                labels=labels,
                thresholds=thresholds,
            )

            progress_dialog.setValue(i)
            if progress_dialog.wasCanceled():
                break

        progress_dialog.close()
        template = self.tr(
            "Uploading annotations successfully!\n"
            "Results have been saved to:\n"
            "%s"
        )
        message_text = template % output_dir_path
        popup = Popup(
            message_text,
            self,
            icon=new_icon_path("copy-green", "svg"),
        )
        popup.show_popup(self, popup_height=65, position="center")

        for label in labels:
            if not self.unique_label_list.find_items_by_label(label):
                item = self.unique_label_list.create_item_from_label(label)
                self.unique_label_list.addItem(item)
                rgb = self._get_rgb_by_label(label)
                self.unique_label_list.set_item_label(
                    item, label, rgb, LABEL_OPACITY
                )

        self.load_file(self.filename)

    except Exception as e:
        progress_dialog.close()
        message = f"Error occurred while uploading annotations: {str(e)}"
        logger.error(message)

        popup = Popup(
            message,
            self,
            icon=new_icon_path("error", "svg"),
        )
        popup.show_popup(self, position="center")


def upload_mot_annotation(self, LABEL_OPACITY):
    if not _check_filename_exist(self):
        return

    filter = "Classes Files (*.txt);;All Files (*)"
    classes_file, _ = QtWidgets.QFileDialog.getOpenFileName(
        self,
        self.tr("Select a specific classes file"),
        "",
        filter,
    )

    if not classes_file:
        return

    filter = "Gt Files (*.txt);;All Files (*)"
    gt_file, _ = QtWidgets.QFileDialog.getOpenFileName(
        self,
        self.tr("Select a specific gt file"),
        "",
        filter,
    )

    if not gt_file:
        popup = Popup(
            self.tr("Please select a specific gt file!"),
            self,
            icon=new_icon_path("warning", "svg"),
        )
        popup.show_popup(self, position="center")
        return

    response = QtWidgets.QMessageBox()
    response.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    response.setWindowTitle(self.tr("Warning"))
    response.setText(self.tr("Current annotation will be lost"))
    response.setInformativeText(
        self.tr(
            "You are going to upload new annotations to this task. Continue?"
        )
    )
    response.setStandardButtons(
        QtWidgets.QMessageBox.StandardButton.Cancel
        | QtWidgets.QMessageBox.StandardButton.Ok
    )
    response.setStyleSheet(get_msg_box_style())

    if response.exec() != QtWidgets.QMessageBox.StandardButton.Ok:
        return

    # Initialize unique labels
    with open(classes_file, "r", encoding="utf-8") as f:
        labels = f.read().splitlines()
        for label in labels:
            if not self.unique_label_list.find_items_by_label(label):
                item = self.unique_label_list.create_item_from_label(label)
                self.unique_label_list.addItem(item)
                rgb = self._get_rgb_by_label(label)
                self.unique_label_list.set_item_label(
                    item, label, rgb, LABEL_OPACITY
                )

    progress_dialog = QProgressDialog(
        self.tr("Uploading..."), self.tr("Cancel"), 0, 0, self
    )
    progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
    progress_dialog.setWindowTitle(self.tr("Progress"))
    progress_dialog.setMinimumWidth(500)
    progress_dialog.setMinimumHeight(150)
    progress_dialog.setRange(0, 0)
    progress_dialog.setStyleSheet(get_progress_dialog_style())

    converter = LabelConverter(classes_file=classes_file)
    image_path = osp.dirname(self.filename)
    output_path = image_path
    if self.output_dir:
        output_path = self.output_dir
    self.upload_thread = UploadMotThread(
        converter, gt_file, output_path, image_path
    )

    def on_upload_finished(success, error_msg):
        progress_dialog.close()
        if success:
            # update and refresh the current canvas
            self.load_file(self.filename)

            popup = Popup(
                self.tr(f"Uploading annotations successfully!"),
                self,
                icon=new_icon_path("copy-green", "svg"),
            )
            popup.show_popup(self, popup_height=65, position="center")
        else:
            message = (
                f"Error occurred while uploading annotations: {str(error_msg)}"
            )
            logger.error(message)
            popup = Popup(
                message,
                self,
                icon=new_icon_path("error", "svg"),
            )
            popup.show_popup(self, position="center")

    self.upload_thread.finished.connect(on_upload_finished)

    progress_dialog.show()
    self.upload_thread.start()

    progress_dialog.canceled.connect(self.upload_thread.terminate)


def upload_mask_annotation(self, LABEL_OPACITY):
    if not _check_filename_exist(self):
        return

    filter = "Attribute Files (*.json);;All Files (*)"
    color_map_file, _ = QtWidgets.QFileDialog.getOpenFileName(
        self,
        self.tr("Select a specific color_map file"),
        "",
        filter,
    )

    if not color_map_file:
        return

    dialog = QtWidgets.QDialog(self)
    dialog.setWindowTitle(self.tr("Upload Options"))
    dialog.setMinimumWidth(500)
    dialog.setStyleSheet(get_export_option_style())

    layout = QVBoxLayout()
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(16)

    path_layout = QVBoxLayout()
    path_label = QtWidgets.QLabel(self.tr("Select Upload Folder"))
    path_layout.addWidget(path_label)

    path_input_layout = QHBoxLayout()
    path_input_layout.setSpacing(8)

    path_edit = QtWidgets.QLineEdit()
    path_edit.setText(_default_upload_folder_path(self))

    def browse_upload_folder():
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            self.tr("Select Upload Folder"),
            path_edit.text(),
            QtWidgets.QFileDialog.Option.ShowDirsOnly
            | QtWidgets.QFileDialog.Option.DontResolveSymlinks
            | QtWidgets.QFileDialog.Option.DontUseNativeDialog,
        )
        if path:
            path_edit.setText(path)

    path_button = QtWidgets.QPushButton(self.tr("Browse"))
    path_button.clicked.connect(browse_upload_folder)
    path_button.setStyleSheet(get_cancel_btn_style())

    path_input_layout.addWidget(path_edit)
    path_input_layout.addWidget(path_button)
    path_layout.addLayout(path_input_layout)
    layout.addLayout(path_layout)

    button_layout = QHBoxLayout()
    button_layout.setContentsMargins(0, 16, 0, 0)
    button_layout.setSpacing(8)

    cancel_button = QtWidgets.QPushButton(self.tr("Cancel"))
    cancel_button.clicked.connect(dialog.reject)
    cancel_button.setStyleSheet(get_cancel_btn_style())

    ok_button = QtWidgets.QPushButton(self.tr("OK"))
    ok_button.clicked.connect(dialog.accept)
    ok_button.setStyleSheet(get_ok_btn_style())

    button_layout.addStretch()
    button_layout.addWidget(cancel_button)
    button_layout.addWidget(ok_button)
    layout.addLayout(button_layout)

    dialog.setLayout(layout)
    result = dialog.exec()

    if not result:
        return

    response = QtWidgets.QMessageBox()
    response.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    response.setWindowTitle(self.tr("Warning"))
    response.setText(self.tr("Current annotation will be lost"))
    response.setInformativeText(
        self.tr(
            "You are going to upload new annotations to this task. Continue?"
        )
    )
    response.setStandardButtons(
        QtWidgets.QMessageBox.StandardButton.Cancel
        | QtWidgets.QMessageBox.StandardButton.Ok
    )
    response.setStyleSheet(get_msg_box_style())

    if response.exec() != QtWidgets.QMessageBox.StandardButton.Ok:
        return

    # Initialize unique labels
    with open(color_map_file, "r", encoding="utf-8") as f:
        mapping_table = json.load(f)
        classes = list(mapping_table["colors"].keys())
        for label in classes:
            if not self.unique_label_list.find_items_by_label(label):
                item = self.unique_label_list.create_item_from_label(label)
                self.unique_label_list.addItem(item)
                rgb = self._get_rgb_by_label(label)
                self.unique_label_list.set_item_label(
                    item, label, rgb, LABEL_OPACITY
                )

    label_dir_path = path_edit.text()
    image_dir_path = osp.dirname(self.filename)
    image_file_list = os.listdir(image_dir_path)
    label_file_list = os.listdir(label_dir_path)
    output_dir_path = self.output_dir if self.output_dir else image_dir_path
    converter = LabelConverter()

    image_list = self.image_list if self.image_list else [self.filename]
    progress_dialog = QProgressDialog(
        self.tr("Uploading..."), self.tr("Cancel"), 0, len(image_list), self
    )
    progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
    progress_dialog.setWindowTitle(self.tr("Progress"))
    progress_dialog.setMinimumWidth(500)
    progress_dialog.setMinimumHeight(150)
    progress_dialog.setStyleSheet(
        get_progress_dialog_style(color="#1d1d1f", height=20)
    )

    try:
        for i, image_filename in enumerate(image_file_list):
            if image_filename.endswith(".json"):
                continue
            data_filename = osp.splitext(image_filename)[0] + ".json"
            if osp.splitext(image_filename)[0] + ".png" in label_file_list:
                label_filename = osp.splitext(image_filename)[0] + ".png"
            elif osp.splitext(image_filename)[0] + ".jpg" in label_file_list:
                label_filename = osp.splitext(image_filename)[0] + ".jpg"
            else:
                continue
            input_file = osp.join(label_dir_path, label_filename)
            output_file = osp.join(output_dir_path, data_filename)
            image_file = osp.join(image_dir_path, image_filename)
            converter.mask_to_custom(
                input_file=input_file,
                output_file=output_file,
                image_file=image_file,
                mapping_table=mapping_table,
            )

            progress_dialog.setValue(i)
            if progress_dialog.wasCanceled():
                break

        progress_dialog.close()
        template = self.tr(
            "Uploading annotations successfully!\n"
            "Results have been saved to:\n"
            "%s"
        )
        message_text = template % output_dir_path
        popup = Popup(
            message_text,
            self,
            icon=new_icon_path("copy-green", "svg"),
        )
        popup.show_popup(self, popup_height=65, position="center")

        # update and refresh the current canvas
        self.load_file(self.filename)
        if getattr(self, "project_root", None) and osp.isdir(self.project_root):
            self.project_upload_annotation_dir = label_dir_path

    except Exception as e:
        progress_dialog.close()
        message = f"Error occurred while uploading annotations: {str(e)}"
        logger.error(message)

        popup = Popup(
            message,
            self,
            icon=new_icon_path("error", "svg"),
        )
        popup.show_popup(self, position="center")


def upload_dota_annotation(self):
    if not self.may_continue():
        return

    in_project = bool(
        getattr(self, "project_root", None)
        and osp.isdir(self.project_root)
    )
    if not in_project and not _check_filename_exist(self):
        return

    converter = LabelConverter()

    if in_project:
        bundle = _project_upload_copy_dataset(
            self, needs_classes_for_yolo=False
        )
        if not bundle:
            return
        dest_path = bundle["dest_path"]
        open_folder = bundle["open_folder"]

        response = QtWidgets.QMessageBox()
        response.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        response.setWindowTitle(self.tr("Warning"))
        response.setText(
            self.tr("Convert DOTA labels under the new project subfolder?")
        )
        response.setInformativeText(
            self.tr(
                "Each .txt next to an image is converted to JSON. "
                "Images without .txt are skipped."
            )
        )
        response.setStandardButtons(
            QtWidgets.QMessageBox.StandardButton.Cancel
            | QtWidgets.QMessageBox.StandardButton.Ok
        )
        response.setStyleSheet(get_msg_box_style())
        if response.exec() != QtWidgets.QMessageBox.StandardButton.Ok:
            return

        image_paths = scan_all_images(dest_path)
        progress_dialog = QProgressDialog(
            self.tr("Uploading..."),
            self.tr("Cancel"),
            0,
            max(len(image_paths), 1),
            self,
        )
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setWindowTitle(self.tr("Progress"))
        progress_dialog.setMinimumWidth(500)
        progress_dialog.setMinimumHeight(150)
        progress_dialog.setStyleSheet(
            get_progress_dialog_style(color="#1d1d1f", height=20)
        )

        try:
            for i, image_file in enumerate(image_paths):
                txt_file = osp.splitext(image_file)[0] + ".txt"
                json_file = osp.splitext(image_file)[0] + ".json"
                if not osp.isfile(txt_file):
                    progress_dialog.setValue(i)
                    continue
                converter.dota_to_custom(
                    input_file=txt_file,
                    output_file=json_file,
                    image_file=image_file,
                )
                progress_dialog.setValue(i)
                if progress_dialog.wasCanceled():
                    break

            progress_dialog.close()
            template = self.tr(
                "Uploading annotations successfully!\n"
                "Results have been saved to:\n"
                "%s"
            )
            popup = Popup(
                template % dest_path,
                self,
                icon=new_icon_path("copy-green", "svg"),
            )
            popup.show_popup(self, popup_height=65, position="center")

            self.project_upload_annotation_dir = dest_path
            if open_folder:
                self.import_image_folder(dest_path)
            elif self.filename:
                self.load_file(self.filename)

        except Exception as e:
            progress_dialog.close()
            message = f"Error occurred while uploading annotations: {str(e)}"
            logger.error(message)
            popup = Popup(
                message,
                self,
                icon=new_icon_path("error", "svg"),
            )
            popup.show_popup(self, position="center")
        return

    dialog = QtWidgets.QDialog(self)
    dialog.setWindowTitle(self.tr("Upload Options"))
    dialog.setMinimumWidth(500)
    dialog.setStyleSheet(get_export_option_style())

    layout = QVBoxLayout()
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(16)

    path_layout = QVBoxLayout()
    path_label = QtWidgets.QLabel(self.tr("Select Upload Folder"))
    path_layout.addWidget(path_label)

    path_input_layout = QHBoxLayout()
    path_input_layout.setSpacing(8)

    path_edit = QtWidgets.QLineEdit()
    path_edit.setText(_default_upload_folder_path(self))

    def browse_upload_folder():
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            self.tr("Select Upload Folder"),
            path_edit.text(),
            QtWidgets.QFileDialog.Option.ShowDirsOnly
            | QtWidgets.QFileDialog.Option.DontResolveSymlinks
            | QtWidgets.QFileDialog.Option.DontUseNativeDialog,
        )
        if path:
            path_edit.setText(path)

    path_button = QtWidgets.QPushButton(self.tr("Browse"))
    path_button.clicked.connect(browse_upload_folder)
    path_button.setStyleSheet(get_cancel_btn_style())

    path_input_layout.addWidget(path_edit)
    path_input_layout.addWidget(path_button)
    path_layout.addLayout(path_input_layout)
    layout.addLayout(path_layout)

    # Button section
    button_layout = QHBoxLayout()
    button_layout.setContentsMargins(0, 16, 0, 0)
    button_layout.setSpacing(8)

    cancel_button = QtWidgets.QPushButton(self.tr("Cancel"))
    cancel_button.clicked.connect(dialog.reject)
    cancel_button.setStyleSheet(get_cancel_btn_style())

    ok_button = QtWidgets.QPushButton(self.tr("OK"))
    ok_button.clicked.connect(dialog.accept)
    ok_button.setStyleSheet(get_ok_btn_style())

    button_layout.addStretch()
    button_layout.addWidget(cancel_button)
    button_layout.addWidget(ok_button)
    layout.addLayout(button_layout)

    dialog.setLayout(layout)
    result = dialog.exec()

    if not result:
        return

    label_dir_path = path_edit.text()
    image_dir_path = osp.dirname(self.filename)
    label_file_list = os.listdir(label_dir_path)
    output_dir_path = self.output_dir if self.output_dir else image_dir_path

    response = QtWidgets.QMessageBox()
    response.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    response.setWindowTitle(self.tr("Warning"))
    response.setText(self.tr("Current annotation will be lost"))
    response.setInformativeText(
        self.tr(
            "You are going to upload new annotations to this task. Continue?"
        )
    )
    response.setStandardButtons(
        QtWidgets.QMessageBox.StandardButton.Cancel
        | QtWidgets.QMessageBox.StandardButton.Ok
    )
    response.setStyleSheet(get_msg_box_style())

    if response.exec() != QtWidgets.QMessageBox.StandardButton.Ok:
        return

    image_list = self.image_list if self.image_list else [self.filename]
    progress_dialog = QProgressDialog(
        self.tr("Uploading..."), self.tr("Cancel"), 0, len(image_list), self
    )
    progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
    progress_dialog.setWindowTitle(self.tr("Progress"))
    progress_dialog.setMinimumWidth(500)
    progress_dialog.setMinimumHeight(150)
    progress_dialog.setStyleSheet(
        get_progress_dialog_style(color="#1d1d1f", height=20)
    )

    try:
        for i, image_path in enumerate(image_list):
            image_filename = osp.basename(image_path)
            label_filename = osp.splitext(image_filename)[0] + ".txt"
            if label_filename not in label_file_list:
                continue

            input_file = osp.join(label_dir_path, label_filename)
            output_file = osp.join(
                output_dir_path, osp.splitext(image_filename)[0] + ".json"
            )
            image_file = osp.join(image_dir_path, image_filename)

            converter.dota_to_custom(
                input_file=input_file,
                output_file=output_file,
                image_file=image_file,
            )

            progress_dialog.setValue(i)
            if progress_dialog.wasCanceled():
                break

        progress_dialog.close()
        template = self.tr(
            "Uploading annotations successfully!\n"
            "Results have been saved to:\n"
            "%s"
        )
        message_text = template % output_dir_path
        popup = Popup(
            message_text,
            self,
            icon=new_icon_path("copy-green", "svg"),
        )
        popup.show_popup(self, popup_height=65, position="center")

        # update and refresh the current canvas
        self.load_file(self.filename)
        if getattr(self, "project_root", None) and osp.isdir(self.project_root):
            self.project_upload_annotation_dir = label_dir_path

    except Exception as e:
        progress_dialog.close()
        message = f"Error occurred while uploading annotations: {str(e)}"
        logger.error(message)

        popup = Popup(
            message,
            self,
            icon=new_icon_path("error", "svg"),
        )
        popup.show_popup(self, position="center")


def upload_coco_annotation(self, mode):
    if not _check_filename_exist(self):
        return

    filter = "Attribute Files (*.json);;All Files (*)"
    input_file, _ = QtWidgets.QFileDialog.getOpenFileName(
        self,
        self.tr("Select a custom coco annotation file"),
        "",
        filter,
    )

    if not input_file:
        return

    output_dir_path = osp.dirname(self.filename)
    if self.output_dir:
        output_dir_path = self.output_dir

    response = QtWidgets.QMessageBox()
    response.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    response.setWindowTitle(self.tr("Warning"))
    response.setText(self.tr("Current annotation will be lost"))
    response.setInformativeText(
        self.tr(
            "You are going to upload new annotations to this task. Continue?"
        )
    )
    response.setStandardButtons(
        QtWidgets.QMessageBox.StandardButton.Cancel
        | QtWidgets.QMessageBox.StandardButton.Ok
    )
    response.setStyleSheet(get_msg_box_style())

    if response.exec() != QtWidgets.QMessageBox.StandardButton.Ok:
        return

    progress_dialog = QProgressDialog(
        self.tr("Uploading..."), self.tr("Cancel"), 0, 0, self
    )
    progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
    progress_dialog.setWindowTitle(self.tr("Progress"))
    progress_dialog.setMinimumWidth(500)
    progress_dialog.setMinimumHeight(150)
    progress_dialog.setRange(0, 0)
    progress_dialog.setStyleSheet(get_progress_dialog_style())

    self.upload_thread = UploadCocoThread(
        LabelConverter(), input_file, output_dir_path, mode
    )

    def on_upload_finished(success, error_msg):
        progress_dialog.close()
        if success:
            # update and refresh the current canvas
            self.load_file(self.filename)

            popup = Popup(
                self.tr(f"Uploading annotations successfully!"),
                self,
                icon=new_icon_path("copy-green", "svg"),
            )
            popup.show_popup(self, popup_height=65, position="center")
        else:
            message = (
                f"Error occurred while uploading annotations: {str(error_msg)}"
            )
            logger.error(message)
            popup = Popup(
                message,
                self,
                icon=new_icon_path("error", "svg"),
            )
            popup.show_popup(self, position="center")

    self.upload_thread.finished.connect(on_upload_finished)

    progress_dialog.show()
    self.upload_thread.start()

    progress_dialog.canceled.connect(self.upload_thread.terminate)


def upload_voc_annotation(self, mode):
    if not self.may_continue():
        return

    in_project = bool(
        getattr(self, "project_root", None)
        and osp.isdir(self.project_root)
    )
    if not in_project and not _check_filename_exist(self):
        return

    converter = LabelConverter()

    if in_project:
        bundle = _project_upload_copy_dataset(
            self, needs_classes_for_yolo=False
        )
        if not bundle:
            return
        dest_path = bundle["dest_path"]
        open_folder = bundle["open_folder"]

        response = QtWidgets.QMessageBox()
        response.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        response.setWindowTitle(self.tr("Warning"))
        response.setText(
            self.tr("Convert VOC XML under the new project subfolder?")
        )
        response.setInformativeText(
            self.tr(
                "XML files are matched to images by base name anywhere under "
                "the copied tree. Images without XML are skipped."
            )
        )
        response.setStandardButtons(
            QtWidgets.QMessageBox.StandardButton.Cancel
            | QtWidgets.QMessageBox.StandardButton.Ok
        )
        response.setStyleSheet(get_msg_box_style())
        if response.exec() != QtWidgets.QMessageBox.StandardButton.Ok:
            return

        xml_by_stem = _collect_voc_xml_by_basename(dest_path)
        image_paths = scan_all_images(dest_path)
        progress_dialog = QProgressDialog(
            self.tr("Uploading..."),
            self.tr("Cancel"),
            0,
            max(len(image_paths), 1),
            self,
        )
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setWindowTitle(self.tr("Progress"))
        progress_dialog.setMinimumWidth(500)
        progress_dialog.setMinimumHeight(150)
        progress_dialog.setStyleSheet(
            get_progress_dialog_style(color="#1d1d1f", height=20)
        )

        try:
            for i, image_path in enumerate(image_paths):
                stem = osp.splitext(osp.basename(image_path))[0].lower()
                if stem not in xml_by_stem:
                    progress_dialog.setValue(i)
                    continue
                json_file = osp.splitext(image_path)[0] + ".json"
                converter.voc_to_custom(
                    input_file=xml_by_stem[stem],
                    output_file=json_file,
                    image_filename=osp.basename(image_path),
                    mode=mode,
                )
                progress_dialog.setValue(i)
                if progress_dialog.wasCanceled():
                    break

            progress_dialog.close()
            self.project_upload_annotation_dir = dest_path
            popup = Popup(
                self.tr("Uploading annotations successfully!"),
                self,
                icon=new_icon_path("copy-green", "svg"),
            )
            popup.show_popup(self, popup_height=65, position="center")

            if open_folder:
                self.import_image_folder(dest_path)
            elif self.filename:
                self.load_file(self.filename)

        except Exception as e:
            progress_dialog.close()
            logger.error(str(e))
            popup = Popup(
                str(e),
                self,
                icon=new_icon_path("error", "svg"),
            )
            popup.show_popup(self, position="center")
        return

    dialog = QtWidgets.QDialog(self)
    dialog.setWindowTitle(self.tr("Upload Options"))
    dialog.setMinimumWidth(500)
    dialog.setStyleSheet(get_export_option_style())

    layout = QVBoxLayout()
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(16)

    path_layout = QVBoxLayout()
    path_label = QtWidgets.QLabel(self.tr("Select Upload Folder"))
    path_layout.addWidget(path_label)

    path_input_layout = QHBoxLayout()
    path_input_layout.setSpacing(8)

    path_edit = QtWidgets.QLineEdit()
    path_edit.setText(_default_upload_folder_path(self))

    def browse_upload_folder():
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            self.tr("Select Upload Folder"),
            path_edit.text(),
            QtWidgets.QFileDialog.Option.ShowDirsOnly
            | QtWidgets.QFileDialog.Option.DontResolveSymlinks
            | QtWidgets.QFileDialog.Option.DontUseNativeDialog,
        )
        if path:
            path_edit.setText(path)

    path_button = QtWidgets.QPushButton(self.tr("Browse"))
    path_button.clicked.connect(browse_upload_folder)
    path_button.setStyleSheet(get_cancel_btn_style())

    path_input_layout.addWidget(path_edit)
    path_input_layout.addWidget(path_button)
    path_layout.addLayout(path_input_layout)
    layout.addLayout(path_layout)

    button_layout = QHBoxLayout()
    button_layout.setContentsMargins(0, 16, 0, 0)
    button_layout.setSpacing(8)

    cancel_button = QtWidgets.QPushButton(self.tr("Cancel"))
    cancel_button.clicked.connect(dialog.reject)
    cancel_button.setStyleSheet(get_cancel_btn_style())

    ok_button = QtWidgets.QPushButton(self.tr("OK"))
    ok_button.clicked.connect(dialog.accept)
    ok_button.setStyleSheet(get_ok_btn_style())

    button_layout.addStretch()
    button_layout.addWidget(cancel_button)
    button_layout.addWidget(ok_button)
    layout.addLayout(button_layout)

    dialog.setLayout(layout)
    result = dialog.exec()

    if not result:
        return

    label_dir_path = path_edit.text()
    image_dir_path = osp.dirname(self.filename)
    label_file_list = os.listdir(label_dir_path)
    output_dir_path = self.output_dir if self.output_dir else image_dir_path

    response = QtWidgets.QMessageBox()
    response.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    response.setWindowTitle(self.tr("Warning"))
    response.setText(self.tr("Current annotation will be lost"))
    response.setInformativeText(
        self.tr(
            "You are going to upload new annotations to this task. Continue?"
        )
    )
    response.setStandardButtons(
        QtWidgets.QMessageBox.StandardButton.Cancel
        | QtWidgets.QMessageBox.StandardButton.Ok
    )
    response.setStyleSheet(get_msg_box_style())

    if response.exec() != QtWidgets.QMessageBox.StandardButton.Ok:
        return

    image_list = self.image_list if self.image_list else [self.filename]
    progress_dialog = QProgressDialog(
        self.tr("Uploading..."), self.tr("Cancel"), 0, len(image_list), self
    )
    progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
    progress_dialog.setWindowTitle(self.tr("Progress"))
    progress_dialog.setMinimumWidth(500)
    progress_dialog.setMinimumHeight(150)
    progress_dialog.setStyleSheet(
        get_progress_dialog_style(color="#1d1d1f", height=20)
    )

    try:
        for i, image_path in enumerate(image_list):
            image_filename = osp.basename(image_path)
            label_filename = osp.splitext(image_filename)[0] + ".xml"
            if label_filename not in label_file_list:
                continue

            input_file = osp.join(label_dir_path, label_filename)
            output_file = osp.join(
                output_dir_path, osp.splitext(image_filename)[0] + ".json"
            )
            converter.voc_to_custom(
                input_file=input_file,
                output_file=output_file,
                image_filename=image_filename,
                mode=mode,
            )

            progress_dialog.setValue(i)
            if progress_dialog.wasCanceled():
                break

        progress_dialog.close()
        template = self.tr(
            "Uploading annotations successfully!\n"
            "Results have been saved to:\n"
            "%s"
        )
        message_text = template % output_dir_path
        popup = Popup(
            message_text,
            self,
            icon=new_icon_path("copy-green", "svg"),
        )
        popup.show_popup(self, popup_height=65, position="center")

        # update and refresh the current canvas
        self.load_file(self.filename)
        if getattr(self, "project_root", None) and osp.isdir(self.project_root):
            self.project_upload_annotation_dir = label_dir_path

    except Exception as e:
        progress_dialog.close()
        message = f"Error occurred while uploading annotations: {str(e)}"
        logger.error(message)

        popup = Popup(
            message,
            self,
            icon=new_icon_path("error", "svg"),
        )
        popup.show_popup(self, position="center")


def upload_yolo_annotation(self, mode, LABEL_OPACITY):
    if not self.may_continue():
        return

    in_project = bool(
        getattr(self, "project_root", None)
        and osp.isdir(self.project_root)
    )
    if not in_project and not _check_filename_exist(self):
        return

    converter = None
    labels = []

    if mode == "pose":
        reuse_yaml = (
            in_project
            and getattr(self, "yaml_file", None)
            and osp.isfile(self.yaml_file)
        )
        if not reuse_yaml:
            filter = "Classes Files (*.yaml);;All Files (*)"
            self.yaml_file, _ = QtWidgets.QFileDialog.getOpenFileName(
                self,
                self.tr("Select a specific yolo-pose config file"),
                "",
                filter,
            )
        if not self.yaml_file:
            return

        try:
            converter = LabelConverter(pose_cfg_file=self.yaml_file)
        except Exception as e:
            logger.error(f"Failed to load pose config: {self.yaml_file}: {e}")
            popup = Popup(
                self.tr("Invalid pose config file:\n%s") % str(e),
                self,
                icon=new_icon_path("error", "svg"),
            )
            popup.show_popup(self, popup_height=65, position="center")
            return

        for class_name, keypoint_name in converter.pose_classes.items():
            labels.append(class_name)
            labels.extend(keypoint_name)

    elif mode in ["hbb", "obb", "seg"]:
        if not in_project:
            proj_cls = getattr(self, "project_label_classes_file_path", None)
            if proj_cls and osp.isfile(proj_cls):
                self.classes_file = proj_cls
                reuse_cls = True
            else:
                reuse_cls = (
                    getattr(self, "classes_file", None)
                    and osp.isfile(self.classes_file)
                )
            if not reuse_cls:
                filter = "Classes Files (*.txt);;All Files (*)"
                self.classes_file, _ = QtWidgets.QFileDialog.getOpenFileName(
                    self,
                    self.tr("Select a specific classes file"),
                    "",
                    filter,
                )
            if not self.classes_file:
                return

            with open(self.classes_file, "r", encoding="utf-8") as f:
                labels = f.read().splitlines()
            converter = LabelConverter(classes_file=self.classes_file)

    if in_project:
        bundle = _project_upload_copy_dataset(
            self,
            needs_classes_for_yolo=mode in ["hbb", "obb", "seg"],
        )
        if not bundle:
            return

        dest_path = bundle["dest_path"]
        preserve_existing = bundle["preserve_existing"]
        open_folder = bundle["open_folder"]

        if mode in ["hbb", "obb", "seg"]:
            classes_path = _resolve_project_classes_file(self)
            if _folder_has_yolo_txt_next_to_images(dest_path):
                if not classes_path:
                    popup = Popup(
                        self.tr(
                            "YOLO labels were copied but no project class list is set. "
                            "Use Upload → Upload Custom Label Classes File."
                        ),
                        self,
                        icon=new_icon_path("warning", "svg"),
                    )
                    popup.show_popup(self, position="center")
                    return
                self.classes_file = classes_path
                converter = LabelConverter(classes_file=classes_path)
                with open(classes_path, "r", encoding="utf-8") as f:
                    labels = f.read().splitlines()

        response = QtWidgets.QMessageBox()
        response.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        response.setWindowTitle(self.tr("Warning"))
        if preserve_existing:
            response.setText(
                self.tr("Convert labels under the new project subfolder?")
            )
            response.setInformativeText(
                self.tr(
                    "Existing JSON may be merged per image. Images without "
                    "matching labels are left unchanged."
                )
            )
        else:
            response.setText(
                self.tr("Convert YOLO labels under the new project subfolder?")
            )
            response.setInformativeText(
                self.tr(
                    "JSON will be written next to each image. "
                    "Images without .txt labels are skipped."
                )
            )
        response.setStandardButtons(
            QtWidgets.QMessageBox.StandardButton.Cancel
            | QtWidgets.QMessageBox.StandardButton.Ok
        )
        response.setStyleSheet(get_msg_box_style())
        if response.exec() != QtWidgets.QMessageBox.StandardButton.Ok:
            return

        image_paths = scan_all_images(dest_path)
        progress_dialog = QProgressDialog(
            self.tr("Uploading..."),
            self.tr("Cancel"),
            0,
            max(len(image_paths), 1),
            self,
        )
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setWindowTitle(self.tr("Progress"))
        progress_dialog.setMinimumWidth(500)
        progress_dialog.setMinimumHeight(150)
        progress_dialog.setStyleSheet(
            get_progress_dialog_style(color="#1d1d1f", height=20)
        )

        try:
            for i, image_file in enumerate(image_paths):
                txt_file = osp.splitext(image_file)[0] + ".txt"
                json_file = osp.splitext(image_file)[0] + ".json"
                if not osp.isfile(txt_file) or converter is None:
                    progress_dialog.setValue(i)
                    if progress_dialog.wasCanceled():
                        break
                    continue

                existing_shapes = []
                if preserve_existing and osp.exists(json_file):
                    with open(json_file, "r", encoding="utf-8") as f:
                        existing_data = json.load(f)
                        existing_shapes = existing_data.get("shapes", [])

                if mode in ["hbb", "seg"]:
                    converter.yolo_to_custom(
                        input_file=txt_file,
                        output_file=json_file,
                        image_file=image_file,
                        mode=mode,
                    )
                elif mode == "obb":
                    converter.yolo_obb_to_custom(
                        input_file=txt_file,
                        output_file=json_file,
                        image_file=image_file,
                    )
                elif mode == "pose":
                    converter.yolo_pose_to_custom(
                        input_file=txt_file,
                        output_file=json_file,
                        image_file=image_file,
                    )

                if preserve_existing and existing_shapes:
                    with open(json_file, "r", encoding="utf-8") as f:
                        new_data = json.load(f)
                    new_data["shapes"] = existing_shapes + new_data.get(
                        "shapes", []
                    )
                    with open(json_file, "w", encoding="utf-8") as f:
                        json.dump(new_data, f, indent=2, ensure_ascii=False)

                progress_dialog.setValue(i)
                if progress_dialog.wasCanceled():
                    break

            progress_dialog.close()
            self.project_upload_annotation_dir = dest_path
            popup = Popup(
                self.tr("Upload completed successfully!"),
                self,
                icon=new_icon_path("copy-green", "svg"),
            )
            popup.show_popup(self, popup_height=65, position="center")

            for label in labels:
                if not label or self.unique_label_list.find_items_by_label(
                    label
                ):
                    continue
                item = self.unique_label_list.create_item_from_label(label)
                self.unique_label_list.addItem(item)
                rgb = self._get_rgb_by_label(label)
                self.unique_label_list.set_item_label(
                    item, label, rgb, LABEL_OPACITY
                )

            if open_folder:
                self.import_image_folder(dest_path)
            elif self.filename:
                self.load_file(self.filename)

        except Exception as e:
            progress_dialog.close()
            message = f"Error occurred while uploading annotations: {str(e)}"
            logger.error(message)
            popup = Popup(
                message,
                self,
                icon=new_icon_path("error", "svg"),
            )
            popup.show_popup(self, position="center")
        return

    if mode in ["hbb", "obb", "seg"] and converter is None:
        return

    dialog = QtWidgets.QDialog(self)
    dialog.setWindowTitle(self.tr("Upload Options"))
    dialog.setMinimumWidth(500)
    dialog.setStyleSheet(get_export_option_style())

    layout = QVBoxLayout()
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(16)

    path_layout = QVBoxLayout()
    path_label = QtWidgets.QLabel(self.tr("Select Upload Folder"))
    path_layout.addWidget(path_label)

    path_input_layout = QHBoxLayout()
    path_input_layout.setSpacing(8)

    path_edit = QtWidgets.QLineEdit()
    path_edit.setText(_default_upload_folder_path(self))

    def browse_upload_folder():
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            self.tr("Select Upload Folder"),
            path_edit.text(),
            QtWidgets.QFileDialog.Option.ShowDirsOnly
            | QtWidgets.QFileDialog.Option.DontResolveSymlinks
            | QtWidgets.QFileDialog.Option.DontUseNativeDialog,
        )
        if path:
            path_edit.setText(path)

    path_button = QtWidgets.QPushButton(self.tr("Browse"))
    path_button.clicked.connect(browse_upload_folder)
    path_button.setStyleSheet(get_cancel_btn_style())

    path_input_layout.addWidget(path_edit)
    path_input_layout.addWidget(path_button)
    path_layout.addLayout(path_input_layout)
    layout.addLayout(path_layout)

    preserve_checkbox = QtWidgets.QCheckBox(
        self.tr("Preserve existing annotations")
    )
    preserve_checkbox.setChecked(False)
    layout.addWidget(preserve_checkbox)

    button_layout = QHBoxLayout()
    button_layout.setContentsMargins(0, 16, 0, 0)
    button_layout.setSpacing(8)

    cancel_button = QtWidgets.QPushButton(self.tr("Cancel"))
    cancel_button.clicked.connect(dialog.reject)
    cancel_button.setStyleSheet(get_cancel_btn_style())

    ok_button = QtWidgets.QPushButton(self.tr("OK"))
    ok_button.clicked.connect(dialog.accept)
    ok_button.setStyleSheet(get_ok_btn_style())

    button_layout.addStretch()
    button_layout.addWidget(cancel_button)
    button_layout.addWidget(ok_button)
    layout.addLayout(button_layout)

    dialog.setLayout(layout)
    result = dialog.exec()

    if not result:
        return

    label_dir_path = path_edit.text()
    preserve_existing = preserve_checkbox.isChecked()
    image_dir_path = osp.dirname(self.filename)
    image_file_list = os.listdir(image_dir_path)
    label_file_list = os.listdir(label_dir_path)
    output_dir_path = self.output_dir if self.output_dir else image_dir_path

    response = QtWidgets.QMessageBox()
    response.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    response.setWindowTitle(self.tr("Warning"))
    if preserve_existing:
        response.setText(
            self.tr("New annotations will be merged with existing ones")
        )
        response.setInformativeText(
            self.tr(
                "You are going to add new annotations to this task. Existing annotations will be preserved. Continue?"
            )
        )
    else:
        response.setText(self.tr("Current annotation will be lost"))
        response.setInformativeText(
            self.tr(
                "You are going to upload new annotations to this task. Continue?"
            )
        )
    response.setStandardButtons(
        QtWidgets.QMessageBox.StandardButton.Cancel
        | QtWidgets.QMessageBox.StandardButton.Ok
    )
    response.setStyleSheet(get_msg_box_style())

    if response.exec() != QtWidgets.QMessageBox.StandardButton.Ok:
        return

    progress_dialog = QProgressDialog(
        self.tr("Uploading..."),
        self.tr("Cancel"),
        0,
        len(image_file_list),
        self,
    )
    progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
    progress_dialog.setWindowTitle(self.tr("Progress"))
    progress_dialog.setMinimumWidth(500)
    progress_dialog.setMinimumHeight(150)
    progress_dialog.setStyleSheet(
        get_progress_dialog_style(color="#1d1d1f", height=20)
    )

    try:
        for i, image_filename in enumerate(image_file_list):
            if image_filename.endswith(".json"):
                continue
            label_filename = osp.splitext(image_filename)[0] + ".txt"
            data_filename = osp.splitext(image_filename)[0] + ".json"
            if label_filename not in label_file_list:
                continue
            input_file = osp.join(label_dir_path, label_filename)
            output_file = osp.join(output_dir_path, data_filename)
            image_file = osp.join(image_dir_path, image_filename)

            existing_shapes = []
            if preserve_existing and osp.exists(output_file):
                with open(output_file, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
                    existing_shapes = existing_data.get("shapes", [])

            if mode in ["hbb", "seg"]:
                converter.yolo_to_custom(
                    input_file=input_file,
                    output_file=output_file,
                    image_file=image_file,
                    mode=mode,
                )
            elif mode == "obb":
                converter.yolo_obb_to_custom(
                    input_file=input_file,
                    output_file=output_file,
                    image_file=image_file,
                )
            elif mode == "pose":
                converter.yolo_pose_to_custom(
                    input_file=input_file,
                    output_file=output_file,
                    image_file=image_file,
                )

            # Merge with existing shapes if needed
            if preserve_existing and existing_shapes:
                with open(output_file, "r", encoding="utf-8") as f:
                    new_data = json.load(f)
                new_data["shapes"] = existing_shapes + new_data.get(
                    "shapes", []
                )
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(new_data, f, indent=2, ensure_ascii=False)

            progress_dialog.setValue(i)
            if progress_dialog.wasCanceled():
                break

        progress_dialog.close()
        self.load_file(self.filename)
        if getattr(self, "project_root", None) and osp.isdir(
            self.project_root
        ):
            self.project_upload_annotation_dir = label_dir_path
        popup = Popup(
            self.tr("Upload completed successfully!"),
            self,
            icon=new_icon_path("copy-green", "svg"),
        )
        popup.show_popup(self, position="center")

        for label in labels:
            if not label or self.unique_label_list.find_items_by_label(label):
                continue
            item = self.unique_label_list.create_item_from_label(label)
            self.unique_label_list.addItem(item)
            rgb = self._get_rgb_by_label(label)
            self.unique_label_list.set_item_label(
                item, label, rgb, LABEL_OPACITY
            )

    except Exception as e:
        progress_dialog.close()
        message = f"Error occurred while uploading annotations: {str(e)}"
        logger.error(message)

        popup = Popup(
            message,
            self,
            icon=new_icon_path("error", "svg"),
        )
        popup.show_popup(self, position="center")


def upload_label_classes_file(self):
    file_path = None
    proj = getattr(self, "project_root", None)
    saved = getattr(self, "project_label_classes_file_path", None)
    if proj and osp.isdir(proj) and saved and osp.isfile(saved):
        answer = QtWidgets.QMessageBox.question(
            self,
            self.tr("Label classes"),
            self.tr(
                "Use the same label classes file as for this project?\n\n%s"
            )
            % saved,
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No
            | QtWidgets.QMessageBox.StandardButton.Cancel,
            QtWidgets.QMessageBox.StandardButton.Yes,
        )
        if answer == QtWidgets.QMessageBox.StandardButton.Cancel:
            return
        if answer == QtWidgets.QMessageBox.StandardButton.Yes:
            file_path = saved
    if file_path is None:
        filter = "Label Files (*.txt);;All Files (*)"
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            self.tr("Select a specific label classes file"),
            "",
            filter,
        )
    if not file_path:
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            labels = [line.strip() for line in f.readlines()]

        if not labels:
            popup = Popup(
                self.tr("No labels found in the file!"),
                self,
                icon=new_icon_path("error", "svg"),
            )
            popup.show_popup(self, position="center")
            return

        response = QtWidgets.QMessageBox()
        response.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        response.setWindowTitle(self.tr("Warning"))
        response.setText(self.tr("Current labels will be lost"))
        response.setInformativeText(
            self.tr(
                "You are going to upload new labels to this task. Continue?"
            )
        )
        response.setStandardButtons(
            QtWidgets.QMessageBox.StandardButton.Cancel
            | QtWidgets.QMessageBox.StandardButton.Ok
        )
        response.setStyleSheet(get_msg_box_style())

        if response.exec() != QtWidgets.QMessageBox.StandardButton.Ok:
            return

        # Update unique_label_list
        self.unique_label_list.clear()
        self.load_labels(labels)

        # Update label_dialog.label_list
        self.label_dialog.label_list.clear()
        self.label_dialog.label_list.addItems(labels)
        if self.label_dialog._sort_labels:
            self.label_dialog.sort_labels()

        _root = getattr(self, "project_root", None)
        if _root and osp.isdir(_root):
            self.project_label_classes_file_path = file_path

        popup = Popup(
            self.tr(f"Successfully loaded {len(set(labels))} labels!"),
            self,
            icon=new_icon_path("copy-green", "svg"),
        )
        popup.show_popup(self, position="center")

    except Exception as e:
        message = (
            f"Error occurred while uploading label classes file: {str(e)}"
        )
        logger.error(message)

        popup = Popup(
            message,
            self,
            icon=new_icon_path("error", "svg"),
        )
        popup.show_popup(self, position="center")


def upload_shape_attrs_file(self, LABEL_OPACITY):
    filter = "Shape Attributes Files (*.json);;All Files (*)"
    file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
        self,
        self.tr("Select a specific shape attributes file"),
        "",
        filter,
    )
    if not file_path:
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            attributes_data = json.load(f)
            self.attribute_widget_types = attributes_data.get(
                "__widget_types__", {}
            )
            self.attributes = {
                k: v
                for k, v in attributes_data.items()
                if not k.startswith("__")
            }
            for label in list(self.attributes.keys()):
                if not self.unique_label_list.find_items_by_label(label):
                    item = self.unique_label_list.create_item_from_label(label)
                    self.unique_label_list.addItem(item)
                    rgb = self._get_rgb_by_label(label)
                    self.unique_label_list.set_item_label(
                        item, label, rgb, LABEL_OPACITY
                    )

        # update the shape attributes dialog
        self.shape_attributes.show()
        self.scroll_area.show()
        self.canvas.h_shape_is_hovered = False
        self.canvas.mode_changed.disconnect(self.set_edit_mode)

        popup = Popup(
            self.tr(f"Uploading shape attributes file successfully!"),
            self,
            icon=new_icon_path("copy-green", "svg"),
        )
        popup.show_popup(self, popup_height=65, position="center")

    except Exception as e:
        message = (
            f"Error occurred while uploading shape attributes file: {str(e)}"
        )
        logger.error(message)

        popup = Popup(
            message,
            self,
            icon=new_icon_path("error", "svg"),
        )
        popup.show_popup(self, position="center")


def upload_label_flags_file(self, LABEL_OPACITY):
    filter = "Label Flags Files (*.yaml);;All Files (*)"
    file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
        self,
        self.tr("Select a specific flags file"),
        "",
        filter,
    )
    if not file_path:
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            # Each line in the file is an flag-level flag
            self.label_flags = yaml.safe_load(f)
            for label in list(self.label_flags.keys()):
                if not self.unique_label_list.find_items_by_label(label):
                    item = self.unique_label_list.create_item_from_label(label)
                    self.unique_label_list.addItem(item)
                    rgb = self._get_rgb_by_label(label)
                    self.unique_label_list.set_item_label(
                        item, label, rgb, LABEL_OPACITY
                    )

        # update the label dialog
        self.label_dialog.upload_flags(self.label_flags)

        popup = Popup(
            self.tr(f"Uploading flags file successfully!"),
            self,
            icon=new_icon_path("copy-green", "svg"),
        )
        popup.show_popup(self, popup_height=65, position="center")

    except Exception as e:
        message = f"Error occurred while uploading flags file: {str(e)}"
        logger.error(message)

        popup = Popup(
            message,
            self,
            icon=new_icon_path("error", "svg"),
        )
        popup.show_popup(self, position="center")


def upload_image_flags_file(self):
    filter = "Image Flags Files (*.txt);;All Files (*)"
    file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
        self,
        self.tr("Select a specific flags file"),
        "",
        filter,
    )
    if not file_path:
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            # Each line in the file is an image-level flag
            self.image_flags = f.read().splitlines()
            self.load_flags({k: False for k in self.image_flags})
        self.flag_dock.show()

        # update and refresh the current canvas
        self.load_file(self.filename)

        popup = Popup(
            self.tr(f"Uploading flags file successfully!"),
            self,
            icon=new_icon_path("copy-green", "svg"),
        )
        popup.show_popup(self, popup_height=65, position="center")

    except Exception as e:
        message = f"Error occurred while uploading flags file: {str(e)}"
        logger.error(message)
        popup = Popup(
            message,
            self,
            icon=new_icon_path("error", "svg"),
        )
        popup.show_popup(self, position="center")


def _safe_project_subdir_name(name):
    name = (name or "").strip()
    for c in '<>:"/\\|?*':
        name = name.replace(c, "_")
    name = name.strip().strip(".") or "imported"
    if name in (".", ".."):
        name = "imported"
    return name


def _is_safe_copy_pair(src: str, dst: str) -> bool:
    src, dst = osp.abspath(src), osp.abspath(dst)
    if src == dst:
        return False
    if dst.startswith(src + os.sep):
        return False
    if src.startswith(dst + os.sep):
        return False
    return True


def _copy_tree_contents(src_root: str, dst_root: str) -> None:
    for root, _, files in os.walk(src_root):
        rel = os.path.relpath(root, src_root)
        dest_dir = dst_root if rel == "." else osp.join(dst_root, rel)
        os.makedirs(dest_dir, exist_ok=True)
        for fname in files:
            shutil.copy2(osp.join(root, fname), osp.join(dest_dir, fname))


def _resolve_project_classes_file(self):
    for path in (
        getattr(self, "project_label_classes_file_path", None),
        getattr(self, "classes_file", None),
    ):
        if path and osp.isfile(path):
            return path
    return None


def _folder_has_yolo_txt_next_to_images(folder: str) -> bool:
    for img in scan_all_images(folder):
        if osp.isfile(osp.splitext(img)[0] + ".txt"):
            return True
    return False


def _collect_voc_xml_by_basename(dest_root: str) -> dict:
    """Map lowercase stem -> full path for each .xml under dest_root."""
    m = {}
    for root, _, files in os.walk(dest_root):
        for f in files:
            if f.lower().endswith(".xml"):
                stem = osp.splitext(f)[0].lower()
                m[stem] = osp.join(root, f)
    return m


def _project_upload_copy_dataset(
    self, *, needs_classes_for_yolo: bool = False
):
    """Dialog + copy external folder into project. Returns dict or None."""
    project_root = getattr(self, "project_root", None)
    if not project_root or not osp.isdir(project_root):
        return None

    dialog = QtWidgets.QDialog(self)
    dialog.setWindowTitle(self.tr("Upload to project"))
    dialog.setMinimumWidth(520)
    dialog.setStyleSheet(get_export_option_style())

    layout = QVBoxLayout()
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(14)

    layout.addWidget(QtWidgets.QLabel(self.tr("Source folder (images and labels)")))
    src_row = QHBoxLayout()
    src_row.setSpacing(8)
    src_edit = QtWidgets.QLineEdit()
    src_edit.setPlaceholderText(
        self.tr("External folder to copy into the project")
    )

    def browse_src():
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            self.tr("Select source folder"),
            src_edit.text() or project_root,
            QtWidgets.QFileDialog.Option.ShowDirsOnly
            | QtWidgets.QFileDialog.Option.DontResolveSymlinks
            | QtWidgets.QFileDialog.Option.DontUseNativeDialog,
        )
        if path:
            src_edit.setText(path)

    browse_btn = QtWidgets.QPushButton(self.tr("Browse"))
    browse_btn.clicked.connect(browse_src)
    browse_btn.setStyleSheet(get_cancel_btn_style())
    src_row.addWidget(src_edit)
    src_row.addWidget(browse_btn)
    layout.addLayout(src_row)

    layout.addWidget(
        QtWidgets.QLabel(
            self.tr("Subfolder name under project (new folder for this upload)")
        )
    )
    tgt_edit = QtWidgets.QLineEdit()
    tgt_edit.setPlaceholderText(
        self.tr("Leave empty to use the source folder name")
    )
    layout.addWidget(tgt_edit)

    preserve_cb = QtWidgets.QCheckBox(
        self.tr("Preserve existing JSON annotations when converting (merge)")
    )
    preserve_cb.setChecked(False)
    layout.addWidget(preserve_cb)

    open_cb = QtWidgets.QCheckBox(
        self.tr("Open the imported folder in the file list when done")
    )
    open_cb.setChecked(True)
    layout.addWidget(open_cb)

    btn_row = QHBoxLayout()
    btn_row.setContentsMargins(0, 12, 0, 0)
    btn_row.setSpacing(8)
    cancel_btn = QtWidgets.QPushButton(self.tr("Cancel"))
    cancel_btn.clicked.connect(dialog.reject)
    cancel_btn.setStyleSheet(get_cancel_btn_style())
    ok_btn = QtWidgets.QPushButton(self.tr("OK"))
    ok_btn.clicked.connect(dialog.accept)
    ok_btn.setStyleSheet(get_ok_btn_style())
    btn_row.addStretch()
    btn_row.addWidget(cancel_btn)
    btn_row.addWidget(ok_btn)
    layout.addLayout(btn_row)
    dialog.setLayout(layout)

    if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return None

    src = osp.abspath(osp.normpath(src_edit.text().strip()))
    if not src or not osp.isdir(src):
        popup = Popup(
            self.tr("Please choose a valid source folder."),
            self,
            icon=new_icon_path("warning", "svg"),
        )
        popup.show_popup(self, position="center")
        return None

    if needs_classes_for_yolo and _folder_has_yolo_txt_next_to_images(src):
        if not _resolve_project_classes_file(self):
            popup = Popup(
                self.tr(
                    "This dataset has YOLO .txt labels. Set the project class list first: "
                    "Upload → Upload Custom Label Classes File, then try again."
                ),
                self,
                icon=new_icon_path("warning", "svg"),
            )
            popup.show_popup(self, position="center")
            return None

    raw_name = tgt_edit.text().strip()
    tgt_name = _safe_project_subdir_name(
        raw_name if raw_name else osp.basename(src)
    )
    dest_path = osp.abspath(osp.join(project_root, tgt_name))

    pr_abs = osp.abspath(project_root)
    if not dest_path.startswith(pr_abs + os.sep) and dest_path != pr_abs:
        popup = Popup(
            self.tr("Invalid destination path."),
            self,
            icon=new_icon_path("error", "svg"),
        )
        popup.show_popup(self, position="center")
        return None

    if not _is_safe_copy_pair(src, dest_path):
        popup = Popup(
            self.tr(
                "Cannot copy: source and destination overlap. "
                "Choose another subfolder name or a different source."
            ),
            self,
            icon=new_icon_path("warning", "svg"),
        )
        popup.show_popup(self, position="center")
        return None

    if osp.lexists(dest_path):
        msg = QtWidgets.QMessageBox(self)
        msg.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        msg.setWindowTitle(self.tr("Folder exists"))
        msg.setText(
            self.tr(
                "Folder \"%s\" already exists under the project. "
                "Merge copied files into it?"
            )
            % tgt_name
        )
        msg.setInformativeText(
            self.tr("Existing files with the same name will be overwritten.")
        )
        msg.setStandardButtons(
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No
        )
        msg.setDefaultButton(QtWidgets.QMessageBox.StandardButton.No)
        msg.setStyleSheet(get_msg_box_style())
        if msg.exec() != QtWidgets.QMessageBox.StandardButton.Yes:
            return None
    else:
        os.makedirs(dest_path, exist_ok=True)

    progress = QProgressDialog(
        self.tr("Copying into project..."),
        self.tr("Cancel"),
        0,
        0,
        self,
    )
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setWindowTitle(self.tr("Progress"))
    progress.setMinimumWidth(480)
    progress.setMinimumHeight(120)
    progress.setRange(0, 0)
    progress.setStyleSheet(get_progress_dialog_style())
    progress.show()
    QtWidgets.QApplication.processEvents()

    try:
        _copy_tree_contents(src, dest_path)
    except Exception as e:
        progress.close()
        logger.error(str(e))
        popup = Popup(
            self.tr("Copy failed: %s") % str(e),
            self,
            icon=new_icon_path("error", "svg"),
        )
        popup.show_popup(self, position="center")
        return None

    progress.close()
    return {
        "dest_path": dest_path,
        "preserve_existing": preserve_cb.isChecked(),
        "open_folder": open_cb.isChecked(),
    }
