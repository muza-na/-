import sys
import os
from datetime import timedelta
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout,
                             QVBoxLayout, QPushButton, QListWidget, QLabel,
                             QSlider, QFileDialog, QSplitter, QListWidgetItem, QFrame)
from PyQt6.QtCore import Qt, QTimer, QSettings, QEvent
from PyQt6.QtGui import QPixmap, QKeyEvent
import vlc

# Безопасный импорт OpenCV
try:
    import cv2

    OPENCV_AVAILABLE = True
except ModuleNotFoundError:
    OPENCV_AVAILABLE = False
    print("Предупреждение: библиотека 'opencv-python' не найдена. Установите через: pip install opencv-python")

# Константы стилей (Палитра из ТЗ)
BG_MAIN = "#1E1F24"
BG_PANEL = "#252730"
ACCENT_PURPLE = "#6C5CE7"
TEXT_MAIN = "#FFFFFF"
TEXT_MUTED = "#A0A5B5"

STYLE_SHEET = f"""
    QMainWindow {{
        background-color: {BG_MAIN};
    }}
    QWidget {{
        color: {TEXT_MAIN};
        font-family: 'Segoe UI', Arial, sans-serif;
    }}
    QFrame#LeftPanel, QFrame#BottomPanel {{
        background-color: {BG_PANEL};
        border-radius: 12px;
    }}
    QPushButton {{
        background-color: transparent;
        border: none;
        color: {TEXT_MAIN};
        padding: 8px;
        text-align: left;
        font-size: 14px;
    }}
    QPushButton:hover {{
        background-color: #313442;
        border-radius: 6px;
    }}
    QPushButton#BtnOpen {{
        background-color: {ACCENT_PURPLE};
        font-weight: bold;
        border-radius: 8px;
        padding: 10px;
        text-align: center;
    }}
    QPushButton#BtnOpen:hover {{
        background-color: #5F3DC4;
    }}
    QListWidget {{
        background-color: transparent;
        border: none;
    }}
    QListWidget::item {{
        background-color: {BG_PANEL};
        border-radius: 8px;
        margin-bottom: 6px;
        padding: 4px;
    }}
    QListWidget::item:selected {{
        background-color: {ACCENT_PURPLE};
    }}
    QSlider::groove:horizontal {{
        height: 6px;
        background: #313442;
        border-radius: 3px;
    }}
    QSlider::sub-page:horizontal {{
        background: {ACCENT_PURPLE};
        border-radius: 3px;
    }}
    QSlider::handle:horizontal {{
        background: white;
        width: 14px;
        margin-top: -4px;
        margin-bottom: -4px;
        border-radius: 7px;
    }}
    QPushButton#SpeedBtn, QPushButton#EnhanceBtn {{
        background-color: #313442;
        border-radius: 6px;
        padding: 5px 10px;
        text-align: center;
    }}
    QPushButton#SpeedBtn[active="true"], QPushButton#EnhanceBtn[active="true"] {{
        background-color: {ACCENT_PURPLE};
    }}
"""


class VideoItemWidget(QWidget):
    """Кастомный виджет для карточки видео в списке недавних"""

    def __init__(self, title, duration, thumb_path):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self.lbl_thumb = QLabel()
        self.lbl_thumb.setFixedSize(64, 36)
        self.lbl_thumb.setStyleSheet("border-radius: 4px; background-color: black;")

        if thumb_path and os.path.exists(thumb_path):
            pixmap = QPixmap(thumb_path).scaled(
                64, 36,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation
            )
            self.lbl_thumb.setPixmap(pixmap)
        else:
            self.lbl_thumb.setText("🎬")
            self.lbl_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.lbl_thumb)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet("font-weight: bold; font-size: 12px; background: transparent;")

        self.lbl_dur = QLabel(duration)
        self.lbl_dur.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; background: transparent;")

        text_layout.addWidget(self.lbl_title)
        text_layout.addWidget(self.lbl_dur)
        layout.addLayout(text_layout)
        layout.addStretch()


class VideoFrame(QFrame):
    """Кастомный виджет видео, поддерживающий двойной клик для Full Screen"""

    def __init__(self, click_callback):
        super().__init__()
        self.click_callback = click_callback
        self.setStyleSheet("background-color: #000000; border-radius: 12px;")

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.click_callback()


class VideoPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Universal Video Player")
        self.setGeometry(100, 100, 1150, 750)
        self.setStyleSheet(STYLE_SHEET)

        # Настройки хранения истории
        self.settings = QSettings("UniversalPlayerCorp", "VideoPlayerApp")

        os.makedirs("cache_thumbnails", exist_ok=True)
        self.current_file = ""
        self.is_enhanced = False

        # VLC Инициализация
        self.instance = vlc.Instance()
        self.media_player = self.instance.media_player_new()

        # Таймер слайдера времени
        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.update_time_slider)

        self.init_ui()
        self.load_recent_history()

        # Фильтр событий для отслеживания клавиши Escape (выход из Full Screen)
        self.installEventFilter(self)

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(self.splitter)

        # ================= 1. ЛЕВАЯ ПАНЕЛЬ =================
        self.left_panel = QFrame()
        self.left_panel.setObjectName("LeftPanel")
        left_layout = QVBoxLayout(self.left_panel)

        lbl_app_title = QLabel("🔮 Universal Video Player")
        lbl_app_title.setStyleSheet("font-size: 18px; font-weight: bold; padding: 10px 0;")
        left_layout.addWidget(lbl_app_title)

        btn_open = QPushButton("📁 Открыть файл")
        btn_open.setObjectName("BtnOpen")
        btn_open.clicked.connect(self.open_file)
        left_layout.addWidget(btn_open)

        left_layout.addWidget(QPushButton("⏱ Недавние"))
        left_layout.addWidget(QPushButton("⭐ Избранное"))
        left_layout.addWidget(QPushButton("⚙ Настройки"))

        lbl_recent = QLabel("Недавно открытые")
        lbl_recent.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; margin-top: 15px; font-weight: bold;")
        left_layout.addWidget(lbl_recent)

        self.list_recent = QListWidget()
        self.list_recent.itemDoubleClicked.connect(self.play_from_list)
        left_layout.addWidget(self.list_recent)

        btn_clear = QPushButton("🗑 Очистить список")
        btn_clear.setStyleSheet(f"color: {TEXT_MUTED}; text-align: center;")
        btn_clear.clicked.connect(self.clear_history)
        left_layout.addWidget(btn_clear)

        # ================= 2. ПРАВАЯ ПАНЕЛЬ =================
        self.right_panel = QWidget()
        self.right_layout = QVBoxLayout(self.right_panel)
        self.right_layout.setContentsMargins(0, 0, 0, 0)

        # Окно видео (используем кастомный кликабельный фрейм)
        self.video_frame = VideoFrame(self.toggle_fullscreen)
        self.right_layout.addWidget(self.video_frame, stretch=4)

        # Нижний блок управления и инфо (объединяем для скрытия в полноэкранном режиме)
        self.controls_block = QWidget()
        cb_layout = QVBoxLayout(self.controls_block)
        cb_layout.setContentsMargins(0, 0, 0, 0)

        timeline_layout = QHBoxLayout()
        self.lbl_time_current = QLabel("00:00:00")
        self.lbl_time_total = QLabel("00:00:00")
        self.slider_time = QSlider(Qt.Orientation.Horizontal)
        self.slider_time.setRange(0, 1000)
        self.slider_time.sliderMoved.connect(self.set_video_position)

        timeline_layout.addWidget(self.lbl_time_current)
        timeline_layout.addWidget(self.slider_time)
        timeline_layout.addWidget(self.lbl_time_total)
        cb_layout.addLayout(timeline_layout)

        controls_layout = QHBoxLayout()
        btn_shuffle = QPushButton("🔀")
        btn_prev = QPushButton("⏮")
        btn_back_10 = QPushButton("⏪")
        btn_back_10.clicked.connect(lambda: self.skip_seconds(-10))

        self.btn_play_pause = QPushButton("⏸")
        self.btn_play_pause.setStyleSheet(
            f"background-color: {ACCENT_PURPLE}; border-radius: 20px; font-size: 18px; min-width: 40px; max-width: 40px; min-height: 40px; max-height: 40px; text-align: center; padding:0;")
        self.btn_play_pause.clicked.connect(self.toggle_play_pause)

        btn_forward_10 = QPushButton("⏩")
        btn_forward_10.clicked.connect(lambda: self.skip_seconds(10))
        btn_stop = QPushButton("⏹")
        btn_stop.clicked.connect(self.stop_video)

        controls_layout.addWidget(btn_shuffle)
        controls_layout.addWidget(btn_prev)
        controls_layout.addWidget(btn_back_10)
        controls_layout.addWidget(self.btn_play_pause)
        controls_layout.addWidget(btn_forward_10)
        controls_layout.addWidget(btn_stop)
        controls_layout.addSpacing(20)

        lbl_vol_icon = QLabel("🔊")
        self.slider_volume = QSlider(Qt.Orientation.Horizontal)
        self.slider_volume.setRange(0, 100)
        self.slider_volume.setValue(70)
        self.slider_volume.setFixedWidth(100)
        self.slider_volume.valueChanged.connect(self.media_player.audio_set_volume)
        controls_layout.addWidget(lbl_vol_icon)
        controls_layout.addWidget(self.slider_volume)

        controls_layout.addStretch()

        btn_fullscreen = QPushButton("📺")
        btn_fullscreen.clicked.connect(self.toggle_fullscreen)
        controls_layout.addWidget(btn_fullscreen)
        cb_layout.addLayout(controls_layout)

        # ================= 3. ИНФОРМАЦИОННАЯ ПАНЕЛЬ =================
        self.bottom_panel = QFrame()
        self.bottom_panel.setObjectName("BottomPanel")
        bottom_layout = QHBoxLayout(self.bottom_panel)

        info_layout = QHBoxLayout()
        self.col1 = QLabel("Название: -\nФормат: -\nРазрешение: -")
        self.col2 = QLabel("Длительность: -\nРазмер: -\nЧастота кадров: -")
        self.col1.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; line-height: 15px;")
        self.col2.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 12px; line-height: 15px;")
        info_layout.addWidget(self.col1)
        info_layout.addWidget(self.col2)
        bottom_layout.addLayout(info_layout, stretch=2)

        right_controls = QVBoxLayout()
        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("Скорость:"))
        self.speed_buttons = []
        for rate in ["0.25x", "0.5x", "1.0x", "1.5x", "2.0x"]:
            btn = QPushButton(rate)
            btn.setObjectName("SpeedBtn")
            btn.setProperty("active", "true" if rate == "1.0x" else "false")
            btn.clicked.connect(lambda ch, r=rate: self.change_speed(r))
            speed_layout.addWidget(btn)
            self.speed_buttons.append(btn)
        right_controls.addLayout(speed_layout)

        self.btn_enhance = QPushButton("✨ Улучшить качество видео: ВЫКЛ")
        self.btn_enhance.setObjectName("EnhanceBtn")
        self.btn_enhance.setProperty("active", "false")
        self.btn_enhance.clicked.connect(self.toggle_enhancement)
        right_controls.addWidget(self.btn_enhance)

        bottom_layout.addLayout(right_controls, stretch=1)
        cb_layout.addWidget(self.bottom_panel)

        self.right_layout.addWidget(self.controls_block)

        self.splitter.addWidget(self.left_panel)
        self.splitter.addWidget(self.right_panel)
        self.splitter.setSizes([300, 850])

    # ================= ЛОГИКА ПОЛНОЭКРАННОГО РЕЖИМА =================

    def toggle_fullscreen(self):
        if self.isFullScreen():
            # Возвращаемся в обычный режим
            self.showNormal()
            self.left_panel.setVisible(True)
            self.bottom_panel.setVisible(True)
            # Возвращаем рамки фрейма обратно
            self.video_frame.setStyleSheet("background-color: #000000; border-radius: 12px;")
        else:
            # Переходим в Full Screen
            self.left_panel.setVisible(False)
            self.bottom_panel.setVisible(False)
            self.video_frame.setStyleSheet("background-color: #000000; border-radius: 0px;")
            self.showFullScreen()

    def eventFilter(self, obj, event):
        # Отлавливаем нажатие Escape для выхода из полноэкранного режима
        if event.type() == QEvent.Type.KeyPress:
            key_event = QKeyEvent(event)
            if key_event.key() == Qt.Key.Key_Escape and self.isFullScreen():
                self.toggle_fullscreen()
                return True
        return super().eventFilter(obj, event)

    # ================= ОСТАЛЬНАЯ ЛОГИКА =================

    def open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Открыть видео", "", "Видео файлы (*.mp4 *.mkv *.avi *.mov *.flv *.wmv)"
        )
        if file_path:
            self.load_video(file_path)

    def load_video(self, file_path):
        self.current_file = file_path
        media = self.instance.media_new(file_path)
        self.media_player.set_media(media)

        if sys.platform.startswith('linux'):
            self.media_player.set_xwindow(self.video_frame.winId())
        elif sys.platform == "win32":
            self.media_player.set_hwnd(self.video_frame.winId())
        elif sys.platform == "darwin":
            self.media_player.set_nsobject(self.video_frame.winId())

        self.media_player.play()
        self.timer.start()
        self.btn_play_pause.setText("⏸")

        self.apply_video_filters()
        self.process_video_metadata(file_path)
        self.save_recent_history(file_path)

    def process_video_metadata(self, file_path):
        name = os.path.basename(file_path)
        ext = os.path.splitext(name)[1].upper().replace('.', '')
        size_mb = os.path.getsize(file_path) / (1024 * 1024)

        dur_str = "00:00:00"
        thumb_path = None

        if OPENCV_AVAILABLE:
            try:
                cap = cv2.VideoCapture(file_path)
                fps = cap.get(cv2.CAP_PROP_FPS)
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

                duration_sec = frame_count / fps if fps > 0 else 0
                dur_str = str(timedelta(seconds=int(duration_sec)))

                self.col1.setText(f"Название: {name}\nФормат: {ext}\nРазрешение: {width}x{height}")
                self.col2.setText(f"Длительность: {dur_str}\nРазмер: {size_mb:.1f} МБ\nЧастота кадров: {int(fps)} fps")

                thumb_name = f"thumb_{hash(file_path)}.jpg"
                thumb_path = os.path.join("cache_thumbnails", thumb_name)

                if not os.path.exists(thumb_path):
                    cap.set(cv2.CAP_PROP_POS_FRAMES, min(100, frame_count // 2))
                    ret, frame = cap.read()
                    if ret:
                        cv2.imwrite(thumb_path, frame)
                cap.release()
            except Exception as e:
                print(f"Ошибка чтения метаданных: {e}")
        else:
            self.col1.setText(f"Название: {name}\nФормат: {ext}\nРазрешение: Авто")
            self.col2.setText(f"Длительность: -\nРазмер: {size_mb:.1f} МБ\nЧастота кадров: -")

        self.add_to_recent_widget(name, dur_str, thumb_path, file_path)

    def add_to_recent_widget(self, name, duration, thumb_path, file_path):
        for i in range(self.list_recent.count()):
            if self.list_recent.item(i).toolTip() == file_path:
                self.list_recent.takeItem(i)
                break

        item = QListWidgetItem()
        item.setToolTip(file_path)
        custom_widget = VideoItemWidget(name, duration, thumb_path)
        item.setSizeHint(custom_widget.sizeHint())
        self.list_recent.insertItem(0, item)
        self.list_recent.setItemWidget(item, custom_widget)

    def save_recent_history(self, new_path):
        history = self.settings.value("recent_files", [])
        if not isinstance(history, list):
            history = [history]

        if new_path in history:
            history.remove(new_path)
        history.insert(0, new_path)
        self.settings.setValue("recent_files", history[:20])

    def load_recent_history(self):
        history = self.settings.value("recent_files", [])
        if not isinstance(history, list):
            history = [history]

        for file_path in reversed(history):
            if os.path.exists(file_path):
                name = os.path.basename(file_path)
                thumb_name = f"thumb_{hash(file_path)}.jpg"
                thumb_path = os.path.join("cache_thumbnails", thumb_name)
                self.add_to_recent_widget(name, "--:--:--", thumb_path, file_path)

    def clear_history(self):
        self.list_recent.clear()
        self.settings.remove("recent_files")

    def toggle_enhancement(self):
        self.is_enhanced = not self.is_enhanced
        if self.is_enhanced:
            self.btn_enhance.setText("✨ Улучшить качество видео: ВКЛ")
            self.btn_enhance.setProperty("active", "true")
        else:
            self.btn_enhance.setText("✨ Улучшить качество видео: ВЫКЛ")
            self.btn_enhance.setProperty("active", "false")

        self.btn_enhance.style().unpolish(self.btn_enhance)
        self.btn_enhance.style().polish(self.btn_enhance)
        self.apply_video_filters()

    def apply_video_filters(self):
        if self.is_enhanced:
            self.media_player.video_set_deinterlace("yadif")
        else:
            self.media_player.video_set_deinterlace(None)

    def play_from_list(self, item):
        self.load_video(item.toolTip())

    def toggle_play_pause(self):
        if self.media_player.is_playing():
            self.media_player.pause()
            self.btn_play_pause.setText("▶")
        else:
            self.media_player.play()
            self.btn_play_pause.setText("⏸")

    def stop_video(self):
        self.media_player.stop()
        self.timer.stop()
        self.lbl_time_current.setText("00:00:00")
        self.slider_time.setValue(0)

    def skip_seconds(self, seconds):
        curr_time = self.media_player.get_time()
        self.media_player.set_time(curr_time + (seconds * 1000))

    def set_video_position(self, position):
        self.media_player.set_position(position / 1000.0)

    def update_time_slider(self):
        if not self.media_player.is_playing():
            return

        pos = self.media_player.get_position()
        self.slider_time.setValue(int(pos * 1000))

        curr_ms = self.media_player.get_time()
        total_ms = self.media_player.get_length()

        if curr_ms > 0:
            self.lbl_time_current.setText(str(timedelta(milliseconds=curr_ms))[:-3])
        if total_ms > 0:
            self.lbl_time_total.setText(str(timedelta(milliseconds=total_ms))[:-3])

    def change_speed(self, rate_str):
        rate = float(rate_str.replace('x', ''))
        self.media_player.set_rate(rate)

        for btn in self.speed_buttons:
            if btn.text() == rate_str:
                btn.setProperty("active", "true")
            else:
                btn.setProperty("active", "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def closeEvent(self, event):
        self.media_player.stop()
        self.instance.release()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    player = VideoPlayer()
    player.show()
    sys.exit(app.exec())

