"""
Video Input component for YouTube Master application.
"""
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, 
    QPushButton, QButtonGroup, QLabel, QComboBox
)
from PyQt6.QtCore import pyqtSignal, Qt, pyqtSlot
from PyQt6.QtGui import QColor

from music_player.models import YoutubeModel, SiteModel, YtDlpModel
from qt_base_app.theme.theme_manager import ThemeManager
from qt_base_app.models.settings_manager import SettingsManager, SettingType
from music_player.models.settings_defs import (
    YT_ACTIVE_RESOLUTION_KEY, YT_HTTPS_ENABLED_KEY, YT_M4A_ENABLED_KEY,
    YT_SUBTITLES_ENABLED_KEY, YT_SUBTITLES_LANG_KEY, YT_COOKIES_ENABLED_KEY
)

class ToggleButton(QPushButton):
    """Custom toggle button that can be toggled on/off with clear visual state.
    State persistence is handled via SettingsManager using the provided setting_key.
    """
    
    def __init__(self, text, setting_key: str, parent=None, exclusive=False):
        """Initialize the toggle button."""
        super().__init__(text, parent)
        self.setCheckable(True)
        self._exclusive = exclusive
        self.setting_key = setting_key
        self._settings = SettingsManager.instance() # Cache instance

        initial_checked = False # Default to unchecked
        # --- Only load from settings if a valid key is provided --- 
        if self.setting_key: 
            loaded_state = self._settings.get(self.setting_key, None, SettingType.BOOL)
            if loaded_state is not None:
                initial_checked = loaded_state
            else:
                # Key provided, but not found in settings - log this maybe?
                # For now, just defaults to False as initialized above.
                # print(f"Debug: Setting key '{self.setting_key}' not found. Using default False.")
                pass # Keep initial_checked as False
        # ---------------------------------------------------------

        self.setChecked(initial_checked)

        if not self._exclusive:
            # Connect save state only if NOT exclusive AND key exists
            if self.setting_key:
                 self.toggled.connect(self._save_state)
        
        self.setMinimumWidth(50)
        self.setStyleSheet(self._get_toggle_button_style())
        self.setFixedHeight(22)
    
    def _get_toggle_button_style(self):
        """Get the stylesheet for toggle buttons using qt_base_app ThemeManager."""
        tm = ThemeManager.instance()
        
        accent_color = tm.get_color('background', 'accent')  
        background_color = tm.get_color('background', 'tertiary')
        hover_color = tm.get_color('background', 'hover')
        text_color = tm.get_color('text', 'primary')
        checked_text_color = tm.get_color('text', 'primary') 
        border_color = tm.get_color('border', 'primary')

        return f"""
            QPushButton {{
                background-color: {background_color};
                color: {text_color};
                border: 1px solid {border_color};
                padding: 3px;
                border-radius: 4px;
                font-size: 10px; /* Keep small font from original */
            }}
            
            QPushButton:hover {{
                background-color: {hover_color};
            }}
            
            QPushButton:checked {{
                background-color: {accent_color};
                border: 1px solid {accent_color};
                color: {checked_text_color};
            }}
            
            QPushButton:checked:hover {{
                background-color: {accent_color}; /* Or a slightly different shade */
                border: 1px solid {text_color}; /* Highlight border on hover when checked */
            }}
        """
    
    @pyqtSlot(bool)
    def _save_state(self, checked):
        """Save the button's state to settings using self.setting_key."""
        if not self._exclusive and self.setting_key:
            # print(f"DEBUG: Saving state for {self.setting_key}: {checked}")
            self._settings.set(self.setting_key, checked, SettingType.BOOL)
    
    def toggle(self):
        """Toggle the button state."""
        if self._exclusive or not self.isChecked():
            self.setChecked(not self.isChecked())

class VideoInput(QWidget):
    """
    Video input component with URL entry and format selection.
    
    Emits:
        format_changed: When the selected format changes
        enter_pressed: When Enter is pressed in the URL field
        add_clicked: When the Add button is clicked
    """
    
    format_changed = pyqtSignal(dict)
    enter_pressed = pyqtSignal()
    add_clicked = pyqtSignal()
    
    def __init__(self, parent=None):
        """Initialize the video input component."""
        super().__init__(parent)
        self._settings = SettingsManager.instance() # Cache instance
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        url_row = QHBoxLayout()
        url_label = QLabel("Video URL:")
        url_row.addWidget(url_label)
        
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter YouTube or Bilibili URL or Video ID...")
        self.url_input.returnPressed.connect(self.on_enter_pressed)
        url_row.addWidget(self.url_input)
        
        self.add_button = QPushButton("Add")
        self.add_button.clicked.connect(self.on_add_clicked)
        self.add_button.setFixedWidth(80)
        url_row.addWidget(self.add_button)
        
        self.layout.addLayout(url_row)
        
        self.create_format_row()
        self._load_initial_resolution_state()
        self.update_format()
    
    def create_format_row(self):
        """Create the format selection row."""
        format_layout = QHBoxLayout()
        format_layout.setSpacing(5)
        
        self.resolution_group = QButtonGroup(self)
        self.resolution_group.setExclusive(False)
        
        self.btn_best = ToggleButton("Best", setting_key=None, exclusive=True)
        self.btn_1080p = ToggleButton("1080p", setting_key=None, exclusive=True)
        self.btn_720p = ToggleButton("720p", setting_key=None, exclusive=True)
        self.btn_480p = ToggleButton("480p", setting_key=None, exclusive=True)
        self.btn_audio = ToggleButton("Audio", setting_key=None, exclusive=True)
        
        format_layout.addWidget(self.btn_best)
        format_layout.addWidget(self.btn_1080p)
        format_layout.addWidget(self.btn_720p)
        format_layout.addWidget(self.btn_480p)
        format_layout.addWidget(self.btn_audio)
        
        self.resolution_group.addButton(self.btn_best)
        self.resolution_group.addButton(self.btn_1080p)
        self.resolution_group.addButton(self.btn_720p)
        self.resolution_group.addButton(self.btn_480p)
        self.resolution_group.addButton(self.btn_audio)
        
        self.btn_https = ToggleButton("HTTPS", setting_key=YT_HTTPS_ENABLED_KEY)
        format_layout.addWidget(self.btn_https)
        self.btn_m4a = ToggleButton("M4A", setting_key=YT_M4A_ENABLED_KEY)
        format_layout.addWidget(self.btn_m4a)
        self.btn_cookies = ToggleButton("Cookies", setting_key=YT_COOKIES_ENABLED_KEY)
        format_layout.addWidget(self.btn_cookies)
        self.btn_subtitles = ToggleButton("Subtitles", setting_key=YT_SUBTITLES_ENABLED_KEY)
        format_layout.addWidget(self.btn_subtitles)

        self.subtitle_lang_combo = QComboBox()
        self.subtitle_lang_combo.setFixedWidth(120)
        self.subtitle_lang_combo.setEditable(True)
        self.subtitle_lang_combo.setToolTip("Select subtitle language (e.g., 'en' for English, 'zh' for Chinese)")
        
        self.subtitle_lang_combo.view().setMinimumWidth(200)
        
        language_options = [
            ("en", "English"),
            ("zh", "中文"),
            ("ja", "日本語"),
            ("es", "Español"),
            ("fr", "Français"),
            ("de", "Deutsch"),
            ("ko", "한국어"),
            ("ru", "Русский"),
            ("pt", "Português"),
            ("ar", "العربية"),
            ("hi", "हिन्दी"),
            ("all", "All Languages")
        ]
        
        for code, name in language_options:
            self.subtitle_lang_combo.addItem(name, code)
        
        current_lang = self._settings.get(YT_SUBTITLES_LANG_KEY, None, SettingType.STRING)
        if current_lang is None: current_lang = "en"
        index = self.subtitle_lang_combo.findData(current_lang)
        if index >= 0:
            self.subtitle_lang_combo.setCurrentIndex(index)
        else:
            self.subtitle_lang_combo.addItem(current_lang, current_lang)
            self.subtitle_lang_combo.setCurrentText(current_lang)
        
        self.subtitle_lang_combo.currentTextChanged.connect(self.on_subtitle_lang_changed)
        format_layout.addWidget(self.subtitle_lang_combo)
        
        format_layout.addStretch()
        
        self.btn_best.clicked.connect(self.on_resolution_clicked)
        self.btn_1080p.clicked.connect(self.on_resolution_clicked)
        self.btn_720p.clicked.connect(self.on_resolution_clicked)
        self.btn_480p.clicked.connect(self.on_resolution_clicked)
        self.btn_audio.clicked.connect(self.on_resolution_clicked)

        self.btn_https.toggled.connect(self.update_format)
        self.btn_m4a.toggled.connect(self.update_format)
        self.btn_cookies.toggled.connect(self.update_format)
        self.btn_subtitles.toggled.connect(self.update_format)

        self.layout.addLayout(format_layout)

    def _load_initial_resolution_state(self):
        """Load the active resolution from settings and update buttons."""
        active_res_text = self._settings.get(YT_ACTIVE_RESOLUTION_KEY, None, SettingType.STRING)
        if active_res_text is None:
             print(f"Warning: Setting key '{YT_ACTIVE_RESOLUTION_KEY}' not found. Check set_defaults. Defaulting to 720p.")
             active_res_text = "720p"
             self._settings.set(YT_ACTIVE_RESOLUTION_KEY, active_res_text, SettingType.STRING)

        # print(f"DEBUG: Loading active resolution: {active_res_text}")
        found_button = False
        for button in self.resolution_group.buttons():
            if button.text() == active_res_text:
                button.setChecked(True)
                found_button = True
                # print(f"DEBUG: Setting initial resolution to {button.text()}")
            else:
                button.setChecked(False)
        if not found_button:
            # print(f"DEBUG: Active resolution '{active_res_text}' not found, defaulting to 720p")
            self.btn_720p.setChecked(True)
            self._settings.set(YT_ACTIVE_RESOLUTION_KEY, "720p", SettingType.STRING)

    def on_resolution_clicked(self):
        """Handle resolution button clicks, enforce exclusivity, save active state."""
        sender = self.sender()
        if not sender.isChecked():
            sender.setChecked(True)
            return
        active_button_text = ""
        for button in self.resolution_group.buttons():
            if button == sender:
                button.setChecked(True)
                active_button_text = button.text()
            else:
                button.setChecked(False)
        
        if active_button_text:
            # print(f"DEBUG: Saving active resolution: {active_button_text}")
            self._settings.set(YT_ACTIVE_RESOLUTION_KEY, active_button_text, SettingType.STRING)

        if sender == self.btn_audio:
            # print("DEBUG: Audio button selected, turning off M4A by default")
            self.btn_m4a.setChecked(False)
        
        self.update_format()
    
    def update_format(self):
        """Update the format selection based on button states and emit signal."""
        format_dict = self.get_format_options()
        
        self.format_changed.emit(format_dict)
    
    def on_enter_pressed(self):
        """Handle enter key in URL field."""
        self.enter_pressed.emit()
    
    def on_add_clicked(self):
        """Handle Add button click."""
        self.add_clicked.emit()
    
    def get_url(self):
        """Get the entered URL and clean it from unnecessary parameters."""
        url = self.url_input.text().strip()
        
        return SiteModel.get_clean_url(url)
    
    def set_url(self, url):
        """Set the URL input text."""
        self.url_input.setText(url)
        self.url_input.selectAll()
    
    def get_format_options(self):
        """Get the selected format options using YtDlpModel."""
        active_button_text = self._settings.get(YT_ACTIVE_RESOLUTION_KEY, None, SettingType.STRING)
        resolution = None
        prefer_best_video = False
        
        if active_button_text == "Best":
            resolution = None  # No resolution constraint
            prefer_best_video = True  # Enable best video quality mode
        elif active_button_text == "1080p": 
            resolution = 1080
        elif active_button_text == "720p": 
            resolution = 720
        elif active_button_text == "480p": 
            resolution = 480
        elif active_button_text == "Audio": 
            resolution = None
        else: 
            resolution = None
        
        subtitle_enabled = self.btn_subtitles.isChecked()
        cookies_enabled = self.btn_cookies.isChecked()
        use_https = self.btn_https.isChecked()
        use_m4a = self.btn_m4a.isChecked()
        
        subtitle_lang = None
        if subtitle_enabled:
            current_lang = self._settings.get(YT_SUBTITLES_LANG_KEY, None, SettingType.STRING)
            index = self.subtitle_lang_combo.currentIndex()
            if index >= 0:
                subtitle_lang = self.subtitle_lang_combo.itemData(index)
                if subtitle_lang == 'zh': subtitle_lang = ['zh-CN', 'zh-TW', 'zh-HK']
            else: subtitle_lang = self.subtitle_lang_combo.currentText().strip()
        
        # print(f"DEBUG: Generating format options with resolution={resolution}, prefer_best_video={prefer_best_video}, https={use_https}, m4a={use_m4a}, subtitle_lang={subtitle_lang}, cookies={cookies_enabled}")
        
        # Direct call to YtDlpModel since we know the signature matches
        options = YtDlpModel.generate_format_string(
            resolution=resolution,
            use_https=use_https,
            use_m4a=use_m4a,
            subtitle_lang=subtitle_lang,
            use_cookies=cookies_enabled,
            prefer_best_video=prefer_best_video,
            prefer_avc=(resolution is not None and not prefer_best_video)  # Use AVC only for specific resolutions
        )
        
        # print(f"DEBUG: Generated format options: {options}")
        return options

    def set_format_audio_only(self):
        """Set format selection to audio only"""
        self.btn_best.setChecked(False)
        self.btn_1080p.setChecked(False)
        self.btn_720p.setChecked(False)
        self.btn_480p.setChecked(False)
        
        self.btn_audio.setChecked(True)
        
        self.update_format()

    def set_format_video_720p(self):
        """Set format selection to 720p video"""
        self.btn_best.setChecked(False)
        self.btn_1080p.setChecked(False)
        self.btn_480p.setChecked(False)
        self.btn_audio.setChecked(False)
        
        self.btn_720p.setChecked(True)
        
        self.update_format()
        
    def set_format_best_video(self):
        """Set format selection to best quality video"""
        self.btn_1080p.setChecked(False)
        self.btn_720p.setChecked(False)
        self.btn_480p.setChecked(False)
        self.btn_audio.setChecked(False)
        
        self.btn_best.setChecked(True)
        
        self.update_format()

    def on_subtitle_lang_changed(self, text):
        """Handle subtitle language changes, save to settings, update format."""
        index = self.subtitle_lang_combo.findText(text)
        lang_code = self.subtitle_lang_combo.itemData(index) if index >= 0 else text
        
        # print(f"DEBUG: Subtitle language changed to: {lang_code}")
        self._settings.set(YT_SUBTITLES_LANG_KEY, lang_code, SettingType.STRING)
        self.update_format()