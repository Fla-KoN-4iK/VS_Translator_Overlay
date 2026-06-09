import json
import asyncio
import logging
import os
import re
import sys
import threading
import traceback
import shutil
from dataclasses import dataclass
from html import escape, unescape
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QRect, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPen, QPixmap, QTextDocument
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizeGrip,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

try:
    import keyboard
except Exception:
    keyboard = None

try:
    import pyperclip
except Exception:
    pyperclip = None

try:
    import pyautogui
except Exception:
    pyautogui = None

try:
    from deep_translator import GoogleTranslator
except Exception:
    GoogleTranslator = None

try:
    import mss
    from PIL import Image
except Exception:
    mss = None
    Image = None

try:
    from winrtocr import WinRTOCR
except Exception as exc:
    WinRTOCR = None
    WINRTOCR_IMPORT_ERROR = exc
else:
    WINRTOCR_IMPORT_ERROR = None


APP_NAME = "VS Translator Overlay"
APP_DIR = Path(__file__).resolve().parent
APP_DATA_DIR = Path(os.environ["APPDATA"]) / "VS Translator Overlay"
LEGACY_CONFIG_PATH = APP_DIR / "config.json"
CONFIG_PATH = APP_DATA_DIR / "config.json"
ERROR_LOG_PATH = APP_DATA_DIR / "error.log"
OCR_DEBUG_CAPTURE_PATH = APP_DATA_DIR / "ocr_debug_capture.png"
OCR_DEBUG_PROCESSED_PATH = APP_DATA_DIR / "ocr_debug_processed.png"
DEFAULT_CONFIG = {
    "chat_log_path": r"C:\Users\flako\AppData\Roaming\VintagestoryData\Logs\client-chat.log",
    "max_messages": 3,
    "overlay_opacity": 0.82,
    "poll_interval_ms": 700,
    "show_language_status_in_normal_mode": False,
    "enable_language_cycle_hotkeys": False,
    "user_language": "ru",
    "user_language_presets": ["ru", "en", "de", "fr", "no", "sv", "es"],
    "translation_language_presets": [
        "auto", "en", "ru", "de", "fr", "es", "it", "pt",
        "no", "sv", "da", "fi", "nl", "pl", "cs",
        "tr", "uk", "ja", "ko", "zh-CN",
    ],
    "outgoing_source_language": "auto",
    "current_outgoing_language": "en",
    "outgoing_language_presets": ["en", "ru", "de", "fr", "es", "it", "pt", "no", "sv", "da", "fi", "nl", "pl", "cs", "tr", "uk", "ja", "ko", "zh-CN"],
    "server_chat_language": "en",
    "incoming_source_language": "auto",
    "ocr_source_mode": "auto",
    "ocr_translation_source_language": "auto",
    "show_system_messages": False,
    "translate_cyrillic_messages": False,
    "type_into_game_delay_ms": 3000,
    "switch_to_english_before_paste": True,
    "layout_switch_hotkey": "alt+shift",
    "font_family": "Segoe UI",
    "font_size": 18,
    "font_size_min": 12,
    "font_size_max": 22,
    "auto_fit_font": True,
    "message_spacing": 4,
    "overlay_padding": 8,
    "use_player_colors_from_log": True,
    "default_player_name_color": "FEC500",
    "original_text_color": "FFFFFF",
    "translation_text_color": "D6D6D6",
    "translation_prefix": "",
    "ocr_center_width": 760,
    "ocr_center_height": 420,
    "ocr_backend": "windows",
    "ocr_language": "en-US",
    "ocr_language_presets": ["auto", "en-US", "de-DE", "sv-SE", "nb-NO", "fr-FR", "ru-RU"],
    "ocr_toast_width": 520,
    "ocr_toast_timeout_ms": 7000,
    "ocr_region_padding": 16,
    "ocr_capture_delay_ms": 180,
    "hide_toasts_before_ocr": True,
    "ocr_debug_save_images": True,
    "ocr_join_lines_for_translation": True,
    "enable_translation_glossary": True,
    "ocr_region_x": None,
    "ocr_region_y": None,
    "ocr_region_width": None,
    "ocr_region_height": None,
    "overlay_x": None,
    "overlay_y": None,
    "overlay_width": None,
    "overlay_height": None,
}

TAG_RE = re.compile(r"<[^>]+>")
CHAT_RE = re.compile(r"\[Chat\]\s*(.*)", re.IGNORECASE)
PLAYER_CHAT_RE = re.compile(r"^\s*([A-Za-z0-9_-]{2,32})\s*:\s*(.+)$")
FONT_COLOR_BLOCK_RE = re.compile(
    r"<font[^>]*\bcolor\s*=\s*[\"']?#?([0-9A-Fa-f]{6})[\"']?[^>]*>(.*?)</font>",
    re.IGNORECASE | re.DOTALL,
)
FONT_COLOR_NEAR_NAME_RE = re.compile(
    r"<font[^>]*\bcolor\s*=\s*[\"']?#?([0-9A-Fa-f]{6})[\"']?[^>]*>.*?([A-Za-z0-9_-]{2,32})\s*:?",
    re.IGNORECASE | re.DOTALL,
)
TRAILING_SUFFIX_RE = re.compile(r"\s+@\s*\d+\s*$")
CYRILLIC_RE = re.compile(r"[\u0400-\u04ff]")


def setup_runtime_paths():
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if LEGACY_CONFIG_PATH.exists() and not CONFIG_PATH.exists():
        try:
            shutil.copy2(LEGACY_CONFIG_PATH, CONFIG_PATH)
            return True
        except Exception as exc:
            log_exception(f"Failed to migrate config to AppData: {LEGACY_CONFIG_PATH} -> {CONFIG_PATH}", exc)
    return False


def setup_logging():
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=ERROR_LOG_PATH,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )


def log_exception(message, exc=None):
    if exc is None:
        logging.error(message)
    else:
        logging.error(
            "%s\n%s",
            message,
            "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        )


def install_exception_hooks():
    def handle_uncaught(exc_type, exc_value, exc_traceback):
        logging.error(
            "Uncaught exception\n%s",
            "".join(traceback.format_exception(exc_type, exc_value, exc_traceback)),
        )
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = handle_uncaught

    if hasattr(threading, "excepthook"):
        original_threading_hook = threading.excepthook

        def handle_thread_exception(args):
            logging.error(
                "Uncaught thread exception\n%s",
                "".join(
                    traceback.format_exception(
                        args.exc_type,
                        args.exc_value,
                        args.exc_traceback,
                    )
                ),
            )
            original_threading_hook(args)

        threading.excepthook = handle_thread_exception


def load_config():
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG.copy()
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return DEFAULT_CONFIG.copy()
    out = DEFAULT_CONFIG.copy()
    out.update({k: v for k, v in cfg.items() if k in out})
    if "current_outgoing_language" not in cfg and cfg.get("server_chat_language"):
        out["current_outgoing_language"] = cfg["server_chat_language"]
    out["server_chat_language"] = out.get("current_outgoing_language", out.get("server_chat_language", "en"))
    return out


def save_config(config):
    try:
        APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
        with CONFIG_PATH.open("w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except Exception as exc:
        log_exception("Failed to save config", exc)


def default_vintagestory_chat_log_path():
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    return Path(appdata) / "VintagestoryData" / "Logs" / "client-chat.log"


def strip_chat_html(text):
    text = TAG_RE.sub("", text)
    text = unescape(text)
    return " ".join(text.split())


def clean_chat_text(text):
    return TRAILING_SUFFIX_RE.sub("", text).strip()


def has_cyrillic(text):
    return CYRILLIC_RE.search(text) is not None


def clean_ocr_text(text):
    cleaned_lines = []
    previous_blank = False
    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = " ".join(raw_line.strip().split())
        if not line:
            if cleaned_lines and not previous_blank:
                cleaned_lines.append("")
            previous_blank = True
            continue
        if not re.search(r"[A-Za-zА-Яа-я0-9]", line):
            continue
        cleaned_lines.append(line)
        previous_blank = False
    while cleaned_lines and not cleaned_lines[-1]:
        cleaned_lines.pop()
    return "\n".join(cleaned_lines).strip()


def config_list(config, key, default):
    value = config.get(key, default)
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return items or list(default)
    if isinstance(value, str):
        items = [item.strip() for item in re.split(r"[,\s]+", value) if item.strip()]
        return items or list(default)
    return list(default)


def cycle_config_value(config, value_key, presets_key, default_presets):
    presets = config_list(config, presets_key, default_presets)
    current = str(config.get(value_key, presets[0]))
    try:
        index = presets.index(current)
    except ValueError:
        index = -1
    next_value = presets[(index + 1) % len(presets)]
    config[value_key] = next_value
    return next_value


TRANSLATION_LANGUAGE_NAMES = {
    "auto": "Auto",
    "en": "English",
    "ru": "Russian",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "no": "Norwegian",
    "sv": "Swedish",
    "da": "Danish",
    "fi": "Finnish",
    "nl": "Dutch",
    "pl": "Polish",
    "cs": "Czech",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "ja": "Japanese",
    "ko": "Korean",
    "zh-CN": "Chinese",
}

OCR_LANGUAGE_NAMES = {
    "auto": "Auto",
    "en-US": "English",
    "de-DE": "German",
    "sv-SE": "Swedish",
    "nb-NO": "Norwegian",
    "fr-FR": "French",
    "ru-RU": "Russian",
}


def translation_presets(config, include_auto):
    presets = config_list(config, "translation_language_presets", DEFAULT_CONFIG["translation_language_presets"])
    if include_auto:
        return presets
    return [code for code in presets if str(code).lower() != "auto"]


def translation_combo_label(code):
    code = str(code)
    if code.lower() == "auto":
        return "Auto"
    return f"{TRANSLATION_LANGUAGE_NAMES.get(code, code)}/{code}"


def ocr_combo_label(code):
    code = str(code)
    if code.lower() == "auto":
        return "Auto"
    return f"{OCR_LANGUAGE_NAMES.get(code, code)}/{code}"


def set_combo_to_data(combo, value):
    value = str(value)
    for index in range(combo.count()):
        if str(combo.itemData(index)) == value:
            combo.blockSignals(True)
            combo.setCurrentIndex(index)
            combo.blockSignals(False)
            return True
    return False


def language_label(value):
    return str(value or "").upper()


def ocr_status_label(config):
    if str(config.get("ocr_source_mode", "auto")).lower() == "auto":
        return "AUTO"
    return language_label(config.get("ocr_language", "en-US"))


def language_status_text(config):
    return (
        f"CHAT  {language_label(config.get('user_language', 'ru'))}  "
        f"SIGNS  {ocr_status_label(config)}  "
        f"SEND  {language_label(config.get('current_outgoing_language', config.get('server_chat_language', 'en')))}"
    )


def ocr_text_score(text):
    if not text:
        return -100000
    letters = len(re.findall(r"[A-Za-zА-Яа-я]", text))
    digits = len(re.findall(r"\d", text))
    useful_words = len(re.findall(r"[A-Za-zА-Яа-я0-9]{3,}", text))
    weird = len(re.findall(r"[�_=~`^|\\{}\[\]<>]", text))
    non_space = sum(1 for ch in text if not ch.isspace())
    symbols = sum(1 for ch in text if not ch.isalnum() and not ch.isspace() and ch not in ".,:;!?/'\"()-")
    if letters + digits == 0:
        return -100000
    return letters * 2 + digits + useful_words * 10 - weird * 25 - symbols * 8 - max(0, non_space - 400) // 4


PROTECTED_TOKEN_RE = re.compile(
    r"(?i)\b(?:https?://)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s]*)?\b|(?<!\S)/[A-Za-z][A-Za-z0-9_-]*"
)
HEADER_LINE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 ,/'\"()!?-]{0,40}:$")
SENTENCE_END_RE = re.compile(r"[.!?)]$")


def is_short_title_line(line):
    words = re.findall(r"[A-Za-z]+", line)
    return 1 <= len(words) <= 4 and all(word[:1].isupper() for word in words)


def should_join_ocr_lines(current, next_line):
    if HEADER_LINE_RE.match(current):
        return True
    if SENTENCE_END_RE.search(current):
        return False
    if is_short_title_line(current) and re.match(r"^\d", next_line):
        return False
    return True


def prepare_ocr_text_for_translation(text, join_lines=True):
    original = clean_ocr_text(text)
    if not join_lines:
        return original

    paragraphs = []
    for block in re.split(r"\n\s*\n", original):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue

        sentences = []
        current = ""
        for line in lines:
            if not current:
                current = line
                continue
            if should_join_ocr_lines(current, line):
                current = f"{current} {line}"
            else:
                sentences.append(current)
                current = line
        if current:
            sentences.append(current)

        paragraph = ". ".join(sentence.strip() for sentence in sentences if sentence.strip())
        if paragraph and not SENTENCE_END_RE.search(paragraph):
            paragraph += "."
        paragraphs.append(paragraph)
    return "\n\n".join(paragraphs).strip()


def protect_translation_tokens(text):
    tokens = {}

    def replace(match):
        key = f"__VSTOKEN{len(tokens)}__"
        tokens[key] = match.group(0)
        return key

    return PROTECTED_TOKEN_RE.sub(replace, text), tokens


def restore_translation_tokens(text, tokens):
    restored = text
    for key, value in tokens.items():
        restored = restored.replace(key, value)
        restored = restored.replace(key.lower(), value)
        restored = restored.replace(key.title(), value)
    return restored


def translate_ocr_text(translator, text, source, target):
    protected_text, tokens = protect_translation_tokens(text)
    translated = translator.translate(protected_text, source=source, target=target)
    return translated, restore_translation_tokens(translated, tokens)


def apply_translation_glossary(text):
    replacements = [
        (r"\bкормиться свободно\b", "свободно собирать ресурсы"),
        (r"\bсвободно добывать корм\b", "свободно собирать ресурсы"),
        (r"\bкорм\b", "сбор ресурсов"),
        (r"\bфураж\b", "сбор ресурсов"),
        (r"\bягодные кустарники\b", "ягодные кусты"),
        (r"\bреспаун\b", "возрождение"),
        (r"\bреспавн\b", "возрождение"),
        (r"\bвозрождаться\b", "возродиться"),
        (r"\bмирогенерация\b", "сгенерированный миром"),
        (r"\bгенерация мира\b", "сгенерированный миром"),
        (r"\bрезин\b", "смола"),
    ]
    out = text
    for pattern, replacement in replacements:
        out = re.sub(pattern, replacement, out, flags=re.IGNORECASE)
    return out


def flatten_winrt_ocr_result(result):
    if result is None:
        return None
    if isinstance(result, str):
        return result

    lines = []
    for item in result:
        if isinstance(item, tuple) and item:
            line = str(item[0]).strip()
        else:
            line = str(item).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


async def run_windows_ocr_async(image, language):
    ocr = WinRTOCR()
    return await ocr.ocr(image, language, detail_level="line")


def run_windows_ocr(image, language):
    return asyncio.run(run_windows_ocr_async(image, language))


def normalize_hex_color(value, default):
    text = str(value or default).strip().lstrip("#")
    if re.fullmatch(r"[0-9A-Fa-f]{6}", text):
        return text.upper()
    return str(default).strip().lstrip("#").upper()


def extract_player_color(raw_chat_html, player_name):
    if not player_name:
        return None
    for color, content in FONT_COLOR_BLOCK_RE.findall(raw_chat_html):
        visible = strip_chat_html(content)
        if visible.startswith(player_name):
            return color.upper()

    for color, name in FONT_COLOR_NEAR_NAME_RE.findall(raw_chat_html):
        if name == player_name:
            return color.upper()
    return None


def parse_chat_line(line, config=None):
    config = config or DEFAULT_CONFIG
    match = CHAT_RE.search(line)
    if not match:
        return None

    raw_body = match.group(1)
    body = clean_chat_text(strip_chat_html(raw_body))
    if not body:
        return None

    name_match = PLAYER_CHAT_RE.match(body)
    if name_match:
        name = name_match.group(1)
        message = clean_chat_text(name_match.group(2))
        if not message:
            return None
        color = None
        if config.get("use_player_colors_from_log", True):
            color = extract_player_color(raw_body, name)
        return name, message, color

    if config.get("show_system_messages", False):
        return None, body, None
    return None


class Translator:
    def __init__(self):
        self.available = GoogleTranslator is not None

    def translate(self, text, source=None, target=None):
        if not text.strip():
            return ""
        if not self.available:
            return "Translation package is not installed."
        try:
            source = source or DEFAULT_CONFIG["incoming_source_language"]
            target = target or DEFAULT_CONFIG["user_language"]
            return GoogleTranslator(source=source, target=target).translate(text)
        except Exception as exc:
            return f"Translation failed: {exc}"


class ChatTailer(QObject):
    message_ready = Signal(object, str, object, object)

    def __init__(self, path, translator, poll_interval_ms, config):
        super().__init__()
        self.config = config
        self.path = self._normalize_path(path)
        self.translator = translator
        self.offset = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        self.timer.start(poll_interval_ms)

    def _normalize_path(self, path):
        text = str(path or "").strip()
        if not text:
            return None
        return Path(os.path.expandvars(text)).expanduser()

    def set_path(self, path):
        self.path = self._normalize_path(path)
        self.offset = 0

    def poll(self):
        if not self.path or not self.path.is_file():
            return

        try:
            size = self.path.stat().st_size
            if size < self.offset:
                self.offset = 0
            if self.offset == 0:
                self.offset = size
                return

            with self.path.open("r", encoding="utf-8", errors="ignore") as f:
                f.seek(self.offset)
                lines = f.readlines()
                self.offset = f.tell()
        except Exception:
            log_exception(f"Failed to read chat log: {self.path}", sys.exception())
            return

        for line in lines:
            parsed = parse_chat_line(line, self.config)
            if not parsed:
                continue
            name, original, player_color = parsed
            threading.Thread(
                target=self._translate_emit,
                args=(name, original, player_color),
                daemon=True,
            ).start()

    def _translate_emit(self, name, original, player_color):
        if has_cyrillic(original) and not self.config.get("translate_cyrillic_messages", False):
            self.message_ready.emit(name, original, None, player_color)
            return
        source = str(self.config.get("incoming_source_language", "auto"))
        target = str(self.config.get("user_language", "ru"))
        logging.info("Incoming chat translation source=%s target=%s", source, target)
        translated = self.translator.translate(original, source=source, target=target)
        self.message_ready.emit(name, original, translated, player_color)


@dataclass
class ChatMessage:
    name: str | None
    original: str
    translated: str | None
    player_color: str | None


class ChatOverlay(QWidget):
    cycle_user_language_requested = Signal()
    cycle_ocr_language_requested = Signal()
    cycle_outgoing_language_requested = Signal()
    settings_requested = Signal()
    user_language_changed = Signal(str)
    ocr_language_changed = Signal(str)
    outgoing_language_changed = Signal(str)

    def __init__(self, config, save_geometry_callback, max_messages=3, opacity=0.82):
        super().__init__()
        self.config = config
        self.save_geometry_callback = save_geometry_callback
        self.max_messages = max_messages
        self.messages = []
        self.edit_mode = False
        self.drag_start = None
        self.user_width = self._config_int("overlay_width") or 640
        self.user_height = self._config_int("overlay_height") or 190
        self.using_saved_geometry = self._has_saved_geometry()
        self.status_label = None
        self.header_label = None
        self.size_grip = None
        self.current_font_size = self._clamped_font_size()
        self.setWindowTitle(APP_NAME)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowOpacity(opacity)
        self.apply_normal_flags()

        self.frame = QFrame(self)
        self.frame.setObjectName("overlayFrame")
        self.frame.setStyleSheet(
            """
            QFrame#overlayFrame {
                background: rgba(18, 24, 31, 178);
                border: 1px solid rgba(150, 164, 181, 72);
                border-radius: 2px;
            }
            QLabel {
                background: transparent;
                color: #f4f4f4;
                padding: 0;
                margin: 0;
            }
            """
        )
        self.layout = QVBoxLayout(self.frame)
        padding = self._config_int("overlay_padding") or 8
        self.layout.setContentsMargins(padding, padding, padding, padding)
        self.layout.setSpacing(self._config_int("message_spacing") or 4)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.frame)
        self.setMinimumWidth(260)
        self.refresh()

    def _config_int(self, key):
        value = self.config.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    def _config_text(self, key, default):
        value = self.config.get(key, default)
        return str(value if value is not None else default)

    def _clamped_font_size(self):
        low = self._config_int("font_size_min") or 12
        high = self._config_int("font_size_max") or 22
        base = self._config_int("font_size") or 18
        return max(low, min(high, base))

    def _font_family(self):
        return self._config_text("font_family", "Segoe UI")

    def _color(self, key, default):
        return normalize_hex_color(self.config.get(key), default)

    def _has_saved_geometry(self):
        return all(self._config_int(k) is not None for k in ("overlay_x", "overlay_y", "overlay_width", "overlay_height"))

    def apply_normal_flags(self):
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

    def apply_edit_flags(self):
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)

    def restore_or_position(self):
        if self.using_saved_geometry:
            self.setGeometry(
                self.config["overlay_x"],
                self.config["overlay_y"],
                max(260, self.config["overlay_width"]),
                max(80, self.config["overlay_height"]),
            )
            self.user_width = max(260, self.width())
            self.user_height = max(80, self.height())
            self.refresh()
        else:
            self.position_bottom_left()

    def add_message(self, name, original, translated, player_color):
        self.messages.append(ChatMessage(name, original, translated, player_color))
        self.messages = self.messages[-self.max_messages :]
        self.refresh()
        if self.isHidden():
            return
        if not self.using_saved_geometry:
            self.position_bottom_left()
        self.show()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            child_layout = item.layout()
            widget = item.widget()
            if child_layout:
                self._clear_layout(child_layout)
                child_layout.deleteLater()
            elif widget:
                widget.deleteLater()

    def _message_html(self, msg, font_size):
        family = escape(self._font_family())
        original_color = self._color("original_text_color", "FFFFFF")
        translation_color = self._color("translation_text_color", "D6D6D6")
        default_name_color = self._color("default_player_name_color", "FEC500")
        name_color = normalize_hex_color(msg.player_color, default_name_color)
        prefix = self._config_text("translation_prefix", "")

        if msg.name:
            first_line = (
                f'<span style="font-weight:600; color:#{name_color};">'
                f'{escape(msg.name)}:</span> '
                f'<span style="color:#{original_color};">{escape(msg.original)}</span>'
            )
        else:
            first_line = f'<span style="color:#{original_color};">{escape(msg.original)}</span>'

        translation = ""
        if msg.translated:
            shown_translation = f"{prefix}{msg.translated}" if prefix else msg.translated
            translation = (
                f'<br><span style="color:#{translation_color};">'
                f'{escape(shown_translation)}</span>'
            )

        return (
            f'<div style="font-family:\'{family}\'; font-size:{font_size}px; '
            f'line-height:1.16;">{first_line}{translation}</div>'
        )

    def _message_height_for_font(self, font_size):
        margins = self.layout.contentsMargins()
        spacing = self.layout.spacing()
        width = max(120, (self.width() or self.user_width) - margins.left() - margins.right())
        total = 0
        items = self.messages or [ChatMessage(None, "Waiting for Vintage Story chat...", None, None)]
        for msg in items:
            doc = QTextDocument()
            doc.setDefaultFont(QFont(self._font_family(), font_size))
            doc.setTextWidth(width)
            doc.setHtml(self._message_html(msg, font_size))
            total += doc.size().height()
        total += max(0, len(items) - 1) * spacing
        if self.edit_mode:
            total += (font_size + spacing + 22) * 2
        elif self.config.get("show_language_status_in_normal_mode", False):
            total += max(12, font_size - 5) + spacing + 4
        return total

    def _fit_font_size(self):
        base = self._clamped_font_size()
        if not self.config.get("auto_fit_font", True):
            return base
        low = self._config_int("font_size_min") or 12
        high = min(self._config_int("font_size_max") or 22, base)
        margins = self.layout.contentsMargins()
        target_height = self.height() if (self.using_saved_geometry or self.edit_mode) else self.user_height
        available = max(40, target_height - margins.top() - margins.bottom())
        for size in range(high, low - 1, -1):
            if self._message_height_for_font(size) <= available:
                return size
        return low

    def _make_label(self, html):
        label = QLabel()
        label.setTextFormat(Qt.RichText)
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.NoTextInteraction)
        label.setFont(QFont(self._font_family(), self.current_font_size))
        label.setText(html)
        return label

    def _make_status_button(self, text, callback):
        button = QPushButton(text)
        button.setFont(QFont(self._font_family(), max(10, self.current_font_size - 5)))
        button.setCursor(Qt.PointingHandCursor)
        button.clicked.connect(callback)
        button.setStyleSheet(
            """
            QPushButton {
                color: rgba(244, 244, 244, 220);
                background: rgba(42, 50, 60, 150);
                border: 1px solid rgba(150, 164, 181, 90);
                border-radius: 2px;
                padding: 2px 6px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(70, 82, 96, 170);
            }
            """
        )
        return button

    def _make_combo(self, values, current, label_func, callback):
        combo = QComboBox()
        combo.setFont(QFont(self._font_family(), max(10, self.current_font_size - 5)))
        combo.setCursor(Qt.PointingHandCursor)
        for value in values:
            combo.addItem(label_func(value), value)
        set_combo_to_data(combo, current)
        combo.currentIndexChanged.connect(lambda index: callback(str(combo.itemData(index))) if index >= 0 else None)
        combo.setStyleSheet(
            """
            QComboBox {
                color: rgba(244, 244, 244, 230);
                background: rgba(42, 50, 60, 165);
                border: 1px solid rgba(150, 164, 181, 90);
                border-radius: 2px;
                padding: 2px 6px;
                min-width: 104px;
            }
            QComboBox:hover {
                background: rgba(70, 82, 96, 180);
            }
            """
        )
        return combo

    def _make_small_text_label(self, text):
        label = QLabel(text)
        label.setFont(QFont(self._font_family(), max(10, self.current_font_size - 5)))
        label.setStyleSheet("color: rgba(214, 214, 214, 210); background: transparent;")
        return label

    def _add_status_controls(self):
        if not self.edit_mode:
            if not self.config.get("show_language_status_in_normal_mode", False):
                return
            self.status_label = QLabel(language_status_text(self.config))
            self.status_label.setFont(QFont(self._font_family(), max(10, self.current_font_size - 5)))
            self.status_label.setStyleSheet("color: rgba(214, 214, 214, 190); font-weight: 600; background: transparent;")
            self.layout.addWidget(self.status_label)
            return

        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(self._make_small_text_label("Read chat/signs in:"))
        row.addWidget(
            self._make_combo(
                translation_presets(self.config, include_auto=False),
                self.config.get("user_language", "ru"),
                translation_combo_label,
                self.user_language_changed.emit,
            )
        )
        row.addWidget(self._make_small_text_label("Read signs text as:"))
        current_ocr = "auto" if str(self.config.get("ocr_source_mode", "auto")).lower() == "auto" else self.config.get("ocr_language", "en-US")
        row.addWidget(
            self._make_combo(
                config_list(self.config, "ocr_language_presets", DEFAULT_CONFIG["ocr_language_presets"]),
                current_ocr,
                ocr_combo_label,
                self.ocr_language_changed.emit,
            )
        )
        row.addWidget(self._make_small_text_label("Send messages to:"))
        row.addWidget(
            self._make_combo(
                translation_presets(self.config, include_auto=False),
                self.config.get("current_outgoing_language", self.config.get("server_chat_language", "en")),
                translation_combo_label,
                self.outgoing_language_changed.emit,
            )
        )
        row.addWidget(self._make_status_button("Settings", self.settings_requested.emit))
        row.addStretch(1)
        self.layout.addLayout(row)

    def refresh(self):
        self._clear_layout(self.layout)

        self.current_font_size = self._fit_font_size()
        self._add_status_controls()

        if self.edit_mode:
            self.header_label = QLabel("Drag/resize overlay. Change languages with dropdowns. Alt+M save. Alt+X quit.")
            self.header_label.setFont(QFont(self._font_family(), max(12, self.current_font_size - 2)))
            self.header_label.setStyleSheet("color: #ffd166; font-weight: 600; background: transparent;")
            self.layout.addWidget(self.header_label)

        if not self.messages:
            msg = ChatMessage(None, "Waiting for Vintage Story chat...", None, None)
            self.layout.addWidget(self._make_label(self._message_html(msg, self.current_font_size)))
        else:
            for msg in self.messages:
                self.layout.addWidget(self._make_label(self._message_html(msg, self.current_font_size)))

        if self.edit_mode:
            grip_row = QHBoxLayout()
            grip_row.addStretch(1)
            self.size_grip = QSizeGrip(self)
            grip_row.addWidget(self.size_grip)
            self.layout.addLayout(grip_row)

        width = max(260, self.user_width)
        if self.edit_mode:
            self.resize(max(width, self.width()), max(90, self.height() or self.user_height))
        elif self.using_saved_geometry:
            self.resize(width, max(80, self.user_height))
        else:
            self.resize(width, max(90, min(240, self.sizeHint().height())))

    def position_bottom_left(self):
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return
        area = screen.availableGeometry()
        self.user_width = max(260, self.user_width)
        self.user_height = max(90, min(240, self.sizeHint().height()))
        self.resize(self.user_width, self.user_height)
        self.move(area.left() + 22, area.bottom() - self.height() - 90)

    def toggle_visible(self):
        if self.isVisible():
            self.hide()
        else:
            if not self.using_saved_geometry:
                self.position_bottom_left()
            self.show()

    def toggle_edit_mode(self):
        was_visible = self.isVisible()
        if self.edit_mode:
            self.user_width = max(260, self.width())
            self.user_height = max(80, self.height())
            self.config["overlay_x"] = self.x()
            self.config["overlay_y"] = self.y()
            self.config["overlay_width"] = self.width()
            self.config["overlay_height"] = self.height()
            self.using_saved_geometry = True
            self.save_geometry_callback()
            self.edit_mode = False
            self.apply_normal_flags()
            self.refresh()
            self.show()
            return

        self.edit_mode = True
        self.apply_edit_flags()
        self.refresh()
        if was_visible:
            self.show()
            self.raise_()
            self.activateWindow()

    def mousePressEvent(self, event):
        if self.edit_mode and event.button() == Qt.LeftButton:
            self.drag_start = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.edit_mode and self.drag_start is not None:
            self.move(event.globalPosition().toPoint() - self.drag_start)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.edit_mode and event.button() == Qt.LeftButton:
            self.drag_start = None
            self.user_width = max(260, self.width())
            self.user_height = max(80, self.height())
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        if self.edit_mode:
            self.user_width = max(260, self.width())
            self.user_height = max(80, self.height())
        super().resizeEvent(event)


class Toast(QWidget):
    def __init__(self, config=None):
        super().__init__()
        self.config = config or DEFAULT_CONFIG
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowOpacity(0.9)

        self.label = QLabel("")
        self.label.setWordWrap(True)
        font_family = str(self.config.get("font_family", "Segoe UI"))
        font_size = max(12, min(16, int(self.config.get("font_size", 18))))
        padding = max(6, int(self.config.get("overlay_padding", 8)))
        self.label.setStyleSheet(
            f"""
            QLabel {{
                background: rgba(18, 24, 31, 190);
                color: #f4f4f4;
                border: 1px solid rgba(150, 164, 181, 78);
                border-radius: 2px;
                padding: {padding}px {padding + 2}px;
                font-family: "{font_family}";
                font-size: {font_size}px;
            }}
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)

    def show_text(self, text, timeout_ms=4500, width=None):
        self.label.setText(text)
        self.label.setFixedWidth(width or 520)
        self.adjustSize()
        screen = QGuiApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            self.move(area.center().x() - self.width() // 2, area.bottom() - self.height() - 140)
        self.show()
        self.timer.start(timeout_ms)


class InputDialog(QDialog):
    toast_signal = Signal(str)
    language_changed = Signal()

    def __init__(
        self,
        translator,
        toast,
        config,
        type_delay_ms,
        switch_to_english_before_paste,
        layout_switch_hotkey,
    ):
        super().__init__()
        self.translator = translator
        self.toast = toast
        self.config = config
        self.type_delay_ms = type_delay_ms
        self.switch_to_english_before_paste = switch_to_english_before_paste
        self.layout_switch_hotkey = layout_switch_hotkey
        self.toast_signal.connect(self.toast.show_text)
        self.setWindowTitle("Translate message")
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.resize(620, 260)

        self.input = QTextEdit()
        self.input.setPlaceholderText("Your message")
        self.input.setAcceptRichText(False)
        self.input.setMinimumHeight(76)

        self.output = QTextEdit()
        self.output.setPlaceholderText("Translated server message")
        self.output.setAcceptRichText(False)
        self.output.setMinimumHeight(76)

        self.source_combo = QComboBox()
        for value in translation_presets(self.config, include_auto=True):
            self.source_combo.addItem(translation_combo_label(value), value)
        self.source_combo.currentIndexChanged.connect(self.change_source_language)

        self.target_combo = QComboBox()
        for value in translation_presets(self.config, include_auto=False):
            self.target_combo.addItem(translation_combo_label(value), value)
        self.target_combo.currentIndexChanged.connect(self.change_target_language)

        translate_button = QPushButton("Translate")
        translate_button.clicked.connect(self.translate_message)

        copy_button = QPushButton("Copy")
        copy_button.clicked.connect(self.copy_translation)

        paste_button = QPushButton("Paste into game")
        paste_button.clicked.connect(self.paste_into_game)

        buttons = QHBoxLayout()
        buttons.addWidget(QLabel("From:"))
        buttons.addWidget(self.source_combo)
        buttons.addWidget(QLabel("To:"))
        buttons.addWidget(self.target_combo)
        buttons.addWidget(translate_button)
        buttons.addWidget(copy_button)
        buttons.addWidget(paste_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.input)
        layout.addWidget(self.output)
        layout.addLayout(buttons)

    def showEvent(self, event):
        super().showEvent(event)
        self.sync_language_ui()
        self.input.clear()
        self.output.clear()
        self.input.setFocus()

    def user_language(self):
        return str(self.config.get("user_language", "ru"))

    def source_language(self):
        return str(self.config.get("outgoing_source_language", "auto"))

    def server_language(self):
        return str(self.config.get("current_outgoing_language", self.config.get("server_chat_language", "en")))

    def sync_language_ui(self):
        self.setWindowTitle("Translate message")
        set_combo_to_data(self.source_combo, self.source_language())
        set_combo_to_data(self.target_combo, self.server_language())

    def change_source_language(self, index):
        value = self.source_combo.itemData(index)
        if value is None:
            return
        self.config["outgoing_source_language"] = str(value)
        save_config(self.config)
        logging.info("Outgoing source language changed in dialog to %s", value)
        self.language_changed.emit()

    def change_target_language(self, index):
        value = self.target_combo.itemData(index)
        if value is None:
            return
        self.config["current_outgoing_language"] = str(value)
        self.config["server_chat_language"] = str(value)
        save_config(self.config)
        self.sync_language_ui()
        logging.info("Outgoing language changed in dialog to %s", value)
        self.language_changed.emit()

    def input_text(self):
        return self.input.toPlainText().strip()

    def translated_output(self):
        return self.output.toPlainText().strip()

    def translate_message(self):
        text = self.input_text()
        if not text:
            return None
        source = self.source_language()
        target = self.server_language()
        logging.info("Outgoing chat translation source=%s target=%s", source, target)
        translated = self.translator.translate(text, source=source, target=target)
        self.output.setPlainText(translated)
        return translated

    def copy_to_clipboard(self, translated):
        if pyperclip is None:
            return False
        try:
            pyperclip.copy(translated)
            return True
        except Exception as exc:
            log_exception("Clipboard copy failed", exc)
            return False

    def copy_translation(self):
        translated = self.translated_output()
        if not translated:
            self.toast.show_text("Translate first.")
            return
        if self.copy_to_clipboard(translated):
            self.toast.show_text(
                f"Copied: {translated}\nSwitch layout if needed, then T  Ctrl+V  Enter.",
                6500,
            )
            self.accept()
        else:
            self.toast.show_text("Clipboard copy failed.")

    def paste_into_game(self):
        translated = self.translated_output()
        if not translated:
            self.toast.show_text("Translate first.")
            return
        copied = self.copy_to_clipboard(translated)
        if not copied:
            self.toast.show_text("Clipboard copy failed.")
            return
        self.hide()
        seconds = max(1, round(max(0, self.type_delay_ms) / 1000))
        self.toast.show_text(f"Click/focus Vintage Story now. Pasting in {seconds}...", self.type_delay_ms + 1200)
        threading.Thread(target=self._paste_worker, args=(translated,), daemon=True).start()

    def _paste_worker(self, translated):
        threading.Event().wait(max(0, self.type_delay_ms) / 1000)
        keyboard_exc = None
        pyautogui_exc = None

        try:
            logging.info("Attempting outgoing paste with keyboard library")
            self._paste_with_keyboard()
            logging.info("Outgoing paste succeeded with keyboard library")
            self.toast_signal.emit(f"Pasted: {translated}")
            return
        except Exception as exc:
            keyboard_exc = exc
            log_exception("Outgoing paste failed with keyboard library", exc)

        try:
            logging.info("Attempting outgoing paste with pyautogui")
            self._paste_with_pyautogui()
            logging.info("Outgoing paste succeeded with pyautogui")
            self.toast_signal.emit(f"Pasted: {translated}")
            return
        except Exception as exc:
            pyautogui_exc = exc
            log_exception("Outgoing paste failed with pyautogui", exc)

        logging.error(
            "Auto paste failed after keyboard and pyautogui attempts. keyboard=%r pyautogui=%r",
            keyboard_exc,
            pyautogui_exc,
        )
        self.toast_signal.emit("Auto paste failed. Translated text copied. Try layout switch, T, Ctrl+V, Enter.")

    def _paste_with_keyboard(self):
        if keyboard is None:
            raise RuntimeError("keyboard package is not installed")
        if self.switch_to_english_before_paste and self.layout_switch_hotkey:
            keyboard.press_and_release(self.layout_switch_hotkey)
            threading.Event().wait(0.2)
        keyboard.press_and_release("t")
        threading.Event().wait(0.15)
        keyboard.press_and_release("ctrl+v")
        threading.Event().wait(0.1)
        keyboard.press_and_release("enter")

    def _paste_with_pyautogui(self):
        if pyautogui is None:
            raise RuntimeError("pyautogui package is not installed")
        if self.switch_to_english_before_paste and self.layout_switch_hotkey:
            keys = self._pyautogui_hotkey_keys(self.layout_switch_hotkey)
            if not keys:
                raise RuntimeError(f"layout_switch_hotkey is not simple enough for pyautogui: {self.layout_switch_hotkey}")
            pyautogui.hotkey(*keys)
            threading.Event().wait(0.2)
        pyautogui.press("t")
        threading.Event().wait(0.15)
        pyautogui.hotkey("ctrl", "v")
        threading.Event().wait(0.1)
        pyautogui.press("enter")

    def _pyautogui_hotkey_keys(self, hotkey):
        key_map = {
            "control": "ctrl",
            "cmd": "win",
            "windows": "win",
        }
        keys = []
        for part in hotkey.lower().replace(" ", "").split("+"):
            if not part:
                continue
            keys.append(key_map.get(part, part))
        return keys


class SettingsDialog(QDialog):
    settings_saved = Signal()
    reset_overlay_requested = Signal()

    def __init__(self, translator, config):
        super().__init__()
        self.translator = translator
        self.config = config
        self.setWindowTitle("VS Translator Overlay Settings")
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        self.resize(720, 360)

        self.chat_path_input = QLineEdit()

        self.user_language_combo = self._make_combo(
            translation_presets(self.config, include_auto=False),
            translation_combo_label,
        )
        self.ocr_language_combo = self._make_combo(
            config_list(self.config, "ocr_language_presets", DEFAULT_CONFIG["ocr_language_presets"]),
            ocr_combo_label,
        )
        self.outgoing_language_combo = self._make_combo(
            translation_presets(self.config, include_auto=False),
            translation_combo_label,
        )
        self.outgoing_source_combo = self._make_combo(
            translation_presets(self.config, include_auto=True),
            translation_combo_label,
        )

        self.opacity_spin = QDoubleSpinBox()
        self.opacity_spin.setRange(0.2, 1.0)
        self.opacity_spin.setSingleStep(0.05)
        self.opacity_spin.setDecimals(2)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 48)

        self.max_messages_spin = QSpinBox()
        self.max_messages_spin.setRange(1, 20)

        form = QFormLayout()
        form.addRow("Vintage Story chat log path", self.chat_path_input)
        form.addRow("Read chat/signs in", self.user_language_combo)
        form.addRow("Read signs text as", self.ocr_language_combo)
        form.addRow("Send messages to", self.outgoing_language_combo)
        form.addRow("From language for outgoing messages", self.outgoing_source_combo)
        form.addRow("Overlay opacity", self.opacity_spin)
        form.addRow("Font size", self.font_size_spin)
        form.addRow("Max messages", self.max_messages_spin)

        auto_detect_button = QPushButton("Auto-detect Vintage Story log")
        auto_detect_button.clicked.connect(self.auto_detect_chat_log)

        browse_button = QPushButton("Browse chat log file")
        browse_button.clicked.connect(self.browse_chat_log)

        test_translation_button = QPushButton("Test translation")
        test_translation_button.clicked.connect(self.test_translation)

        test_ocr_button = QPushButton("Test Windows OCR")
        test_ocr_button.clicked.connect(self.test_windows_ocr)

        reset_button = QPushButton("Reset overlay position")
        reset_button.clicked.connect(self.reset_overlay_position)

        open_folder_button = QPushButton("Open app folder")
        open_folder_button.clicked.connect(self.open_app_folder)

        open_data_folder_button = QPushButton("Open settings/log folder")
        open_data_folder_button.clicked.connect(self.open_data_folder)

        open_log_button = QPushButton("Open error.log if exists")
        open_log_button.clicked.connect(self.open_error_log)

        save_button = QPushButton("Save")
        save_button.clicked.connect(self.save_settings)

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)

        action_row = QHBoxLayout()
        action_row.addWidget(auto_detect_button)
        action_row.addWidget(browse_button)
        action_row.addWidget(test_translation_button)
        action_row.addWidget(test_ocr_button)

        utility_row = QHBoxLayout()
        utility_row.addWidget(reset_button)
        utility_row.addWidget(open_folder_button)
        utility_row.addWidget(open_data_folder_button)
        utility_row.addWidget(open_log_button)
        utility_row.addStretch(1)

        save_row = QHBoxLayout()
        save_row.addStretch(1)
        save_row.addWidget(save_button)
        save_row.addWidget(cancel_button)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(action_row)
        layout.addLayout(utility_row)
        layout.addWidget(self.status_label)
        layout.addLayout(save_row)

    def _make_combo(self, values, label_func):
        combo = QComboBox()
        for value in values:
            combo.addItem(label_func(value), value)
        return combo

    def showEvent(self, event):
        super().showEvent(event)
        self.sync_from_config()

    def sync_from_config(self):
        self.chat_path_input.setText(str(self.config.get("chat_log_path", "")))
        set_combo_to_data(self.user_language_combo, self.config.get("user_language", "ru"))
        current_ocr = "auto" if str(self.config.get("ocr_source_mode", "auto")).lower() == "auto" else self.config.get("ocr_language", "en-US")
        set_combo_to_data(self.ocr_language_combo, current_ocr)
        set_combo_to_data(
            self.outgoing_language_combo,
            self.config.get("current_outgoing_language", self.config.get("server_chat_language", "en")),
        )
        set_combo_to_data(self.outgoing_source_combo, self.config.get("outgoing_source_language", "auto"))
        self.opacity_spin.setValue(float(self.config.get("overlay_opacity", DEFAULT_CONFIG["overlay_opacity"])))
        self.font_size_spin.setValue(int(self.config.get("font_size", DEFAULT_CONFIG["font_size"])))
        self.max_messages_spin.setValue(int(self.config.get("max_messages", DEFAULT_CONFIG["max_messages"])))

    def set_status(self, text):
        self.status_label.setText(text)

    def auto_detect_chat_log(self):
        path = default_vintagestory_chat_log_path()
        if path and path.exists():
            self.chat_path_input.setText(str(path))
            self.set_status(f"Found: {path}")
            return
        self.set_status("Vintage Story client-chat.log was not found in %APPDATA%.")

    def browse_chat_log(self):
        start_path = self.chat_path_input.text().strip()
        start_dir = str(Path(start_path).expanduser().parent) if start_path else str(Path.home())
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select Vintage Story client-chat.log",
            start_dir,
            "Log files (*.log);;All files (*)",
        )
        if filename:
            self.chat_path_input.setText(filename)
            self.set_status(f"Selected: {filename}")

    def test_translation(self):
        target = str(self.user_language_combo.currentData() or self.config.get("user_language", "ru"))
        try:
            result = self.translator.translate("hello", source="auto", target=target)
        except Exception as exc:
            log_exception("Settings translation test failed", exc)
            self.set_status(f"Translation failed: {exc}")
            return
        if str(result).lower().startswith("translation failed"):
            logging.error("Settings translation test failed: %s", result)
        self.set_status(f'Test translation: "hello" -> {result}')

    def test_windows_ocr(self):
        if WinRTOCR is None:
            log_exception("Settings Windows OCR test failed: import unavailable", WINRTOCR_IMPORT_ERROR)
            self.set_status("Windows OCR unavailable. Check Python environment / Windows OCR language pack.")
            return
        try:
            WinRTOCR()
        except Exception as exc:
            log_exception("Settings Windows OCR test failed", exc)
            self.set_status("Windows OCR unavailable. Check Python environment / Windows OCR language pack.")
            return
        self.set_status("Windows OCR: OK")

    def open_app_folder(self):
        try:
            os.startfile(str(APP_DIR))
        except Exception as exc:
            log_exception("Failed to open app folder", exc)
            self.set_status(f"Could not open app folder: {exc}")

    def open_data_folder(self):
        try:
            APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
            os.startfile(str(APP_DATA_DIR))
        except Exception as exc:
            log_exception("Failed to open settings/log folder", exc)
            self.set_status(f"Could not open settings/log folder: {exc}")

    def open_error_log(self):
        if not ERROR_LOG_PATH.exists():
            self.set_status("No error.log yet.")
            return
        try:
            os.startfile(str(ERROR_LOG_PATH))
        except Exception as exc:
            log_exception("Failed to open error.log", exc)
            self.set_status(f"Could not open error.log: {exc}")

    def reset_overlay_position(self):
        self.reset_overlay_requested.emit()
        self.set_status("Overlay position reset.")

    def save_settings(self):
        self.config["chat_log_path"] = self.chat_path_input.text().strip()
        self.config["user_language"] = str(self.user_language_combo.currentData())
        ocr_value = str(self.ocr_language_combo.currentData())
        if ocr_value.lower() == "auto":
            self.config["ocr_source_mode"] = "auto"
        else:
            self.config["ocr_source_mode"] = "manual"
            self.config["ocr_language"] = ocr_value
        outgoing_value = str(self.outgoing_language_combo.currentData())
        self.config["current_outgoing_language"] = outgoing_value
        self.config["server_chat_language"] = outgoing_value
        self.config["outgoing_source_language"] = str(self.outgoing_source_combo.currentData())
        self.config["overlay_opacity"] = round(float(self.opacity_spin.value()), 2)
        self.config["font_size"] = int(self.font_size_spin.value())
        self.config["max_messages"] = int(self.max_messages_spin.value())
        save_config(self.config)
        logging.info("Settings saved. Status: %s", language_status_text(self.config))
        self.settings_saved.emit()
        self.accept()


class OcrSelectionOverlay(QWidget):
    region_selected = Signal(object)

    def __init__(self):
        super().__init__()
        self.start_pos = None
        self.current_pos = None
        self.frozen_image = None
        self.frozen_pixmap = None
        self.physical_bounds = None
        self.padding = 0
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)

    def begin(self, frozen_image, physical_bounds, padding):
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return
        self.frozen_image = frozen_image
        self.frozen_pixmap = self.image_to_pixmap(frozen_image)
        self.physical_bounds = physical_bounds
        self.padding = max(0, int(padding))
        self.setGeometry(screen.geometry())
        self.start_pos = None
        self.current_pos = None
        self.showFullScreen()
        self.raise_()
        self.activateWindow()

    def image_to_pixmap(self, image):
        rgba = image.convert("RGBA")
        data = rgba.tobytes("raw", "RGBA")
        qimage = QImage(data, rgba.width, rgba.height, rgba.width * 4, QImage.Format_RGBA8888).copy()
        return QPixmap.fromImage(qimage)

    def paintEvent(self, event):
        painter = QPainter(self)
        if self.frozen_pixmap:
            painter.drawPixmap(self.rect(), self.frozen_pixmap)
            painter.fillRect(self.rect(), QColor(5, 8, 12, 86))
        else:
            painter.fillRect(self.rect(), QColor(5, 8, 12, 105))
        if self.start_pos is None or self.current_pos is None:
            return

        rect = QRect(self.start_pos, self.current_pos).normalized()
        painter.fillRect(rect, QColor(80, 130, 180, 42))
        painter.setPen(QPen(QColor(245, 214, 126, 230), 2))
        painter.drawRect(rect)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_pos = event.position().toPoint()
            self.current_pos = self.start_pos
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.start_pos is not None:
            self.current_pos = event.position().toPoint()
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.start_pos is not None:
            self.current_pos = event.position().toPoint()
            rect = QRect(self.start_pos, self.current_pos).normalized()
            self.hide()
            if not self.frozen_image or not self.physical_bounds:
                self.region_selected.emit({"too_small": True})
                event.accept()
                return

            if rect.width() < 30 or rect.height() < 20:
                self.region_selected.emit({"too_small": True})
                event.accept()
                return

            image_width, image_height = self.frozen_image.size
            widget_width = max(1, self.width())
            widget_height = max(1, self.height())
            x = round(rect.x() * image_width / widget_width)
            y = round(rect.y() * image_height / widget_height)
            width = round(rect.width() * image_width / widget_width)
            height = round(rect.height() * image_height / widget_height)

            padded_x = max(0, x - self.padding)
            padded_y = max(0, y - self.padding)
            padded_right = min(image_width, x + width + self.padding)
            padded_bottom = min(image_height, y + height + self.padding)
            crop_width = max(0, padded_right - padded_x)
            crop_height = max(0, padded_bottom - padded_y)
            if crop_width < 8 or crop_height < 8:
                self.region_selected.emit({"too_small": True})
                event.accept()
                return

            crop = self.frozen_image.crop((padded_x, padded_y, padded_right, padded_bottom))
            physical_left, physical_top, _, _ = self.physical_bounds
            self.region_selected.emit(
                {
                    "logical_rect": (rect.x(), rect.y(), rect.width(), rect.height()),
                    "image_rect": (padded_x, padded_y, crop_width, crop_height),
                    "physical_region": (
                        int(physical_left + padded_x),
                        int(physical_top + padded_y),
                        int(crop_width),
                        int(crop_height),
                    ),
                    "crop": crop,
                    "screenshot_size": (image_width, image_height),
                }
            )
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
            event.accept()
            return
        super().keyPressEvent(event)


class AppController(QObject):
    show_input_signal = Signal()
    show_settings_signal = Signal()
    toggle_overlay_signal = Signal()
    toggle_edit_signal = Signal()
    ocr_signal = Signal()
    select_ocr_region_signal = Signal()
    last_ocr_region_signal = Signal()
    quit_signal = Signal()
    cycle_user_language_signal = Signal()
    cycle_outgoing_language_signal = Signal()
    cycle_ocr_language_signal = Signal()
    toast_signal = Signal(str)
    ocr_toast_signal = Signal(str)

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.config = load_config()
        self.translator = Translator()
        self.overlay = ChatOverlay(
            self.config,
            self.save_config,
            max_messages=int(self.config["max_messages"]),
            opacity=float(self.config["overlay_opacity"]),
        )
        self.toast = Toast(self.config)
        self.ocr_selection = OcrSelectionOverlay()
        self.input_dialog = InputDialog(
            self.translator,
            self.toast,
            self.config,
            int(self.config["type_into_game_delay_ms"]),
            bool(self.config["switch_to_english_before_paste"]),
            str(self.config["layout_switch_hotkey"]),
        )
        self.settings_dialog = SettingsDialog(self.translator, self.config)
        self.tailer = ChatTailer(
            self.config["chat_log_path"],
            self.translator,
            int(self.config["poll_interval_ms"]),
            self.config,
        )

        self.tailer.message_ready.connect(self.overlay.add_message)
        self.show_input_signal.connect(self.show_input)
        self.show_settings_signal.connect(self.show_settings)
        self.toggle_overlay_signal.connect(self.overlay.toggle_visible)
        self.toggle_edit_signal.connect(self.overlay.toggle_edit_mode)
        self.ocr_signal.connect(self.run_ocr)
        self.select_ocr_region_signal.connect(self.select_ocr_region)
        self.last_ocr_region_signal.connect(self.run_last_ocr_region)
        self.quit_signal.connect(self.quit_app)
        self.cycle_user_language_signal.connect(self.cycle_user_language)
        self.cycle_outgoing_language_signal.connect(self.cycle_outgoing_language)
        self.cycle_ocr_language_signal.connect(self.cycle_ocr_language)
        self.toast_signal.connect(self.toast.show_text)
        self.ocr_toast_signal.connect(self.show_ocr_toast)
        self.ocr_selection.region_selected.connect(self.handle_ocr_region_selected)
        self.input_dialog.language_changed.connect(self.refresh_language_ui)
        self.settings_dialog.settings_saved.connect(self.apply_settings)
        self.settings_dialog.reset_overlay_requested.connect(self.reset_overlay_position)
        self.overlay.cycle_user_language_requested.connect(self.cycle_user_language)
        self.overlay.cycle_ocr_language_requested.connect(self.cycle_ocr_language)
        self.overlay.cycle_outgoing_language_requested.connect(self.cycle_outgoing_language)
        self.overlay.settings_requested.connect(self.show_settings)
        self.overlay.user_language_changed.connect(self.set_user_language)
        self.overlay.ocr_language_changed.connect(self.set_ocr_language)
        self.overlay.outgoing_language_changed.connect(self.set_outgoing_language)

        self.overlay.restore_or_position()
        self.overlay.show()
        logging.info("Language status on startup: %s", language_status_text(self.config))
        self.register_hotkeys()
        QTimer.singleShot(500, self.show_first_run_settings_if_needed)

    def save_config(self):
        save_config(self.config)

    def refresh_language_ui(self):
        self.config["server_chat_language"] = self.config.get("current_outgoing_language", self.config.get("server_chat_language", "en"))
        self.overlay.refresh()
        self.input_dialog.sync_language_ui()

    def apply_settings(self):
        self.config["server_chat_language"] = self.config.get("current_outgoing_language", self.config.get("server_chat_language", "en"))
        self.tailer.set_path(self.config.get("chat_log_path", ""))
        self.overlay.max_messages = int(self.config.get("max_messages", DEFAULT_CONFIG["max_messages"]))
        self.overlay.messages = self.overlay.messages[-self.overlay.max_messages :]
        self.overlay.setWindowOpacity(float(self.config.get("overlay_opacity", DEFAULT_CONFIG["overlay_opacity"])))
        self.refresh_language_ui()
        if not self.chat_log_exists():
            self.toast.show_text("Setup needed: select Vintage Story client-chat.log", 7000)

    def chat_log_exists(self):
        path = str(self.config.get("chat_log_path", "")).strip()
        if not path:
            return False
        return Path(os.path.expandvars(path)).expanduser().is_file()

    def show_first_run_settings_if_needed(self):
        if self.chat_log_exists():
            return
        self.toast.show_text("Setup needed: select Vintage Story client-chat.log", 7000)
        self.show_settings()

    def reset_overlay_position(self):
        for key in ("overlay_x", "overlay_y", "overlay_width", "overlay_height"):
            self.config[key] = None
        self.overlay.using_saved_geometry = False
        self.overlay.user_width = 640
        self.overlay.user_height = 190
        self.overlay.refresh()
        self.overlay.position_bottom_left()
        self.overlay.show()
        self.save_config()

    def set_user_language(self, value):
        if not value:
            return
        self.config["user_language"] = str(value)
        logging.info("User language changed to %s. Status: %s", value, language_status_text(self.config))
        self.save_config()
        self.refresh_language_ui()
        self.toast.show_text(f"CHAT target: {language_label(value)}")

    def set_outgoing_language(self, value):
        if not value:
            return
        self.config["current_outgoing_language"] = str(value)
        self.config["server_chat_language"] = str(value)
        logging.info("Outgoing language changed to %s. Status: %s", value, language_status_text(self.config))
        self.save_config()
        self.refresh_language_ui()
        self.toast.show_text(f"SEND target: {language_label(value)}")

    def set_ocr_language(self, value):
        if not value:
            return
        if str(value).lower() == "auto":
            self.config["ocr_source_mode"] = "auto"
        else:
            self.config["ocr_source_mode"] = "manual"
            self.config["ocr_language"] = str(value)
        logging.info("OCR source changed to %s. Status: %s", value, language_status_text(self.config))
        self.save_config()
        self.refresh_language_ui()
        self.toast.show_text(f"Read signs text as: {ocr_status_label(self.config)}")

    def cycle_user_language(self):
        presets = translation_presets(self.config, include_auto=False)
        current = str(self.config.get("user_language", "ru"))
        try:
            index = presets.index(current)
        except ValueError:
            index = -1
        self.set_user_language(presets[(index + 1) % len(presets)])

    def cycle_outgoing_language(self):
        presets = translation_presets(self.config, include_auto=False)
        current = str(self.config.get("current_outgoing_language", self.config.get("server_chat_language", "en")))
        try:
            index = presets.index(current)
        except ValueError:
            index = -1
        self.set_outgoing_language(presets[(index + 1) % len(presets)])

    def cycle_ocr_language(self):
        presets = config_list(self.config, "ocr_language_presets", DEFAULT_CONFIG["ocr_language_presets"])
        current = "auto" if str(self.config.get("ocr_source_mode", "auto")).lower() == "auto" else str(self.config.get("ocr_language", "en-US"))
        try:
            index = presets.index(current)
        except ValueError:
            index = -1
        self.set_ocr_language(presets[(index + 1) % len(presets)])

    def register_hotkeys(self):
        if keyboard is None:
            message = "keyboard package is not installed. Hotkeys are unavailable."
            logging.error(message)
            self.toast.show_text(message, 7000)
            return
        try:
            keyboard.add_hotkey("alt+t", lambda: self.toggle_overlay_signal.emit())
            keyboard.add_hotkey("alt+r", lambda: self.show_input_signal.emit())
            keyboard.add_hotkey("alt+p", lambda: self.show_settings_signal.emit())
            keyboard.add_hotkey("alt+q", lambda: self.ocr_signal.emit())
            keyboard.add_hotkey("alt+s", lambda: self.select_ocr_region_signal.emit())
            keyboard.add_hotkey("alt+shift+q", lambda: self.last_ocr_region_signal.emit())
            keyboard.add_hotkey("alt+m", lambda: self.toggle_edit_signal.emit())
            if self.config.get("enable_language_cycle_hotkeys", False):
                keyboard.add_hotkey("alt+u", lambda: self.cycle_user_language_signal.emit())
                keyboard.add_hotkey("alt+l", lambda: self.cycle_outgoing_language_signal.emit())
                keyboard.add_hotkey("alt+o", lambda: self.cycle_ocr_language_signal.emit())
            keyboard.add_hotkey("alt+x", lambda: self.quit_signal.emit())
        except Exception as exc:
            log_exception("Hotkey registration failed", exc)
            self.toast.show_text(f"Hotkeys unavailable: {exc}", 7000)

    def show_input(self):
        self.input_dialog.show()
        self.input_dialog.raise_()
        self.input_dialog.activateWindow()

    def show_settings(self):
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def quit_app(self):
        logging.info("Clean quit requested with Alt+X")
        self.toast.show_text("Quitting...", 300)
        QTimer.singleShot(250, self.app.quit)

    def run_ocr(self):
        region = self.center_ocr_region()
        if region:
            self.run_ocr_region(region, "center")

    def select_ocr_region(self):
        if self.config.get("hide_toasts_before_ocr", True):
            self.toast.hide()
        delay = max(0, int(self.config.get("ocr_capture_delay_ms", 180)))
        QTimer.singleShot(delay, self.begin_frozen_ocr_selection)

    def begin_frozen_ocr_selection(self):
        try:
            frozen = self.capture_primary_screen_image()
            if not frozen:
                self.toast_signal.emit("OCR failed.")
                return
            image, bounds = frozen
            logging.info(
                "Alt+S frozen screenshot size=%sx%s physical_bounds=%s",
                image.width,
                image.height,
                bounds,
            )
            self.ocr_selection.begin(image, bounds, int(self.config.get("ocr_region_padding", 16)))
        except Exception as exc:
            log_exception("Failed to start frozen OCR selection", exc)
            self.toast_signal.emit("OCR failed.")

    def capture_primary_screen_image(self):
        if mss is None or Image is None:
            logging.error("OCR screenshot packages are missing")
            return None
        mss_factory = mss.MSS if hasattr(mss, "MSS") else mss.mss
        with mss_factory() as shot:
            monitor = shot.monitors[1]
            raw = shot.grab(monitor)
            image = Image.frombytes("RGB", raw.size, raw.rgb)
            bounds = (
                int(monitor["left"]),
                int(monitor["top"]),
                int(monitor["width"]),
                int(monitor["height"]),
            )
        return image, bounds

    def handle_ocr_region_selected(self, selection):
        if selection.get("too_small"):
            self.toast_signal.emit("OCR region too small.")
            return

        region = selection["physical_region"]
        logging.info(
            "Alt+S selected logical_rect=%s mapped_image_rect=%s screenshot_size=%s physical_region=%s",
            selection["logical_rect"],
            selection["image_rect"],
            selection["screenshot_size"],
            region,
        )

        self.config["ocr_region_x"] = region[0]
        self.config["ocr_region_y"] = region[1]
        self.config["ocr_region_width"] = region[2]
        self.config["ocr_region_height"] = region[3]
        self.save_config()
        self.run_ocr_image(selection["crop"], "selected-frozen", region)

    def run_last_ocr_region(self):
        region = self.saved_ocr_region()
        if not region:
            self.toast_signal.emit("No OCR region selected. Press Alt+S first.")
            return
        self.run_ocr_region(region, "saved")

    def saved_ocr_region(self):
        keys = ("ocr_region_x", "ocr_region_y", "ocr_region_width", "ocr_region_height")
        values = [self.config.get(key) for key in keys]
        if not all(isinstance(value, int) and value > 0 for value in values[2:]):
            return None
        if not all(isinstance(value, int) for value in values):
            return None
        return tuple(values)

    def center_ocr_region(self):
        screen = QGuiApplication.primaryScreen()
        if not screen:
            self.toast_signal.emit("Cannot find a screen for OCR.")
            return None
        geo = screen.geometry()
        width = min(int(self.config.get("ocr_center_width", 760)), int(geo.width() * 0.95))
        height = min(int(self.config.get("ocr_center_height", 420)), int(geo.height() * 0.9))
        left = geo.left() + (geo.width() - width) // 2
        top = geo.top() + (geo.height() - height) // 2
        return self.logical_region_to_physical_capture((left, top, width, height), apply_padding=False)

    def primary_physical_bounds(self):
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return None

        if mss is not None:
            try:
                mss_factory = mss.MSS if hasattr(mss, "MSS") else mss.mss
                with mss_factory() as shot:
                    monitor = shot.monitors[1]
                    return (
                        int(monitor["left"]),
                        int(monitor["top"]),
                        int(monitor["width"]),
                        int(monitor["height"]),
                    )
            except Exception as exc:
                log_exception("Failed to read primary physical monitor bounds from mss", exc)

        geo = screen.geometry()
        dpr = screen.devicePixelRatio()
        return (
            round(geo.left() * dpr),
            round(geo.top() * dpr),
            round(geo.width() * dpr),
            round(geo.height() * dpr),
        )

    def logical_region_to_physical_capture(self, region, apply_padding):
        screen = QGuiApplication.primaryScreen()
        bounds = self.primary_physical_bounds()
        if not screen or not bounds:
            return None

        logical_x, logical_y, logical_width, logical_height = region
        geo = screen.geometry()
        dpr = screen.devicePixelRatio()
        physical_left, physical_top, physical_width, physical_height = bounds

        x = round(physical_left + (logical_x - geo.left()) * dpr)
        y = round(physical_top + (logical_y - geo.top()) * dpr)
        width = round(logical_width * dpr)
        height = round(logical_height * dpr)

        if apply_padding:
            padding = max(0, int(self.config.get("ocr_region_padding", 16)))
            x -= padding
            y -= padding
            width += padding * 2
            height += padding * 2

        max_right = physical_left + physical_width
        max_bottom = physical_top + physical_height
        right = min(max_right, x + width)
        bottom = min(max_bottom, y + height)
        x = max(physical_left, x)
        y = max(physical_top, y)
        width = max(0, right - x)
        height = max(0, bottom - y)
        if width < 8 or height < 8:
            return None
        return int(x), int(y), int(width), int(height)

    def run_ocr_region(self, region, region_type):
        if self.config.get("hide_toasts_before_ocr", True):
            self.toast.hide()
        threading.Thread(target=self._ocr_worker, args=(region, region_type), daemon=True).start()

    def run_ocr_image(self, image, region_type, region):
        threading.Thread(target=self._ocr_image_worker, args=(image, region_type, region), daemon=True).start()

    def show_ocr_toast(self, text):
        self.toast.show_text(
            text,
            int(self.config.get("ocr_toast_timeout_ms", 7000)),
            int(self.config.get("ocr_toast_width", 520)),
        )

    def _ocr_image_worker(self, image, region_type, region):
        if WinRTOCR is None:
            log_exception("Windows OCR package import failed", WINRTOCR_IMPORT_ERROR)
            self.toast_signal.emit("Windows OCR package is not installed.")
            return
        try:
            self.process_ocr_image(image, region_type, region)
        except Exception as exc:
            log_exception("OCR failed", exc)
            self.toast_signal.emit("OCR failed.")

    def recognize_ocr_text(self, image, region_type, region):
        mode = str(self.config.get("ocr_source_mode", "auto")).lower()
        if mode != "auto":
            language = str(self.config.get("ocr_language", "en-US"))
            raw_result = run_windows_ocr(image, language)
            raw_text = flatten_winrt_ocr_result(raw_result)
            text = clean_ocr_text(raw_text or "")
            logging.info(
                "Windows OCR manual language=%s score=%s region_type=%s region=%s raw=%r cleaned=%r",
                language,
                ocr_text_score(text),
                region_type,
                region,
                raw_text,
                text,
            )
            return language, raw_text, text

        best = None
        languages = [
            language
            for language in config_list(self.config, "ocr_language_presets", DEFAULT_CONFIG["ocr_language_presets"])
            if str(language).lower() != "auto"
        ]
        for language in languages:
            try:
                raw_result = run_windows_ocr(image, language)
            except Exception as exc:
                logging.info("OCR auto language failed language=%s error=%r", language, exc)
                continue
            raw_text = flatten_winrt_ocr_result(raw_result)
            text = clean_ocr_text(raw_text or "")
            score = ocr_text_score(text)
            logging.info(
                "Windows OCR auto language=%s score=%s region_type=%s region=%s raw=%r cleaned=%r",
                language,
                score,
                region_type,
                region,
                raw_text,
                text,
            )
            result = {"language": language, "raw": raw_text, "text": text, "score": score}
            if best is None or result["score"] > best["score"]:
                best = result

        if not best or not best["text"]:
            return None
        logging.info("OCR auto chosen language=%s score=%s text=%r", best["language"], best["score"], best["text"])
        return best["language"], best["raw"], best["text"]

    def process_ocr_image(self, image, region_type, region):
        if self.config.get("ocr_debug_save_images", True):
            image.save(OCR_DEBUG_CAPTURE_PATH)
            image.save(OCR_DEBUG_PROCESSED_PATH)

        backend = str(self.config.get("ocr_backend", "windows")).lower()
        logging.info(
            "OCR backend=%s mode=%s language=%s region_type=%s region=%s",
            backend,
            self.config.get("ocr_source_mode", "auto"),
            self.config.get("ocr_language", "en-US"),
            region_type,
            region,
        )
        if backend != "windows":
            logging.error("Unsupported OCR backend configured: %s", backend)
            self.toast_signal.emit("OCR backend is not supported.")
            return

        try:
            recognized = self.recognize_ocr_text(image, region_type, region)
        except OSError as exc:
            log_exception("Windows OCR failed; language pack may be missing", exc)
            self.toast_signal.emit("Windows OCR language is not available. Install English OCR language pack.")
            return
        except Exception as exc:
            message = str(exc).lower()
            log_exception("Windows OCR failed", exc)
            if "language" in message or "ocrengine" in message or "ocr engine" in message:
                self.toast_signal.emit("Windows OCR language is not available. Install English OCR language pack.")
            else:
                self.toast_signal.emit("OCR failed.")
            return

        if not recognized:
            self.toast_signal.emit("No OCR language worked.")
            return

        chosen_language, raw_text, text = recognized
        logging.info(
            "Windows OCR result type=%s chosen_language=%s region=%s raw=%r cleaned=%r",
            region_type,
            chosen_language,
            region,
            raw_text,
            text,
        )

        if not text:
            self.toast_signal.emit("OCR found no readable text.")
            return

        translation_input = prepare_ocr_text_for_translation(
            text,
            bool(self.config.get("ocr_join_lines_for_translation", True)),
        )
        logging.info("OCR original text=%r", text)
        logging.info("OCR translation_input=%r", translation_input)

        source = str(self.config.get("ocr_translation_source_language", "auto"))
        target = str(self.config.get("user_language", "ru"))
        logging.info("OCR translation source=%s target=%s", source, target)
        translated_raw, translated = translate_ocr_text(self.translator, translation_input, source, target)
        logging.info("OCR translated raw text=%r", translated_raw)
        if self.config.get("enable_translation_glossary", True):
            translated = apply_translation_glossary(translated)
        logging.info("OCR final translated text=%r", translated)
        self.ocr_toast_signal.emit(f"{text}\n\n{translated}")

    def _ocr_worker(self, region, region_type):
        if mss is None or Image is None:
            logging.error("OCR screenshot packages are missing")
            self.toast_signal.emit("OCR screenshot package is not installed.")
            return
        if WinRTOCR is None:
            log_exception("Windows OCR package import failed", WINRTOCR_IMPORT_ERROR)
            self.toast_signal.emit("Windows OCR package is not installed.")
            return

        try:
            threading.Event().wait(max(0, int(self.config.get("ocr_capture_delay_ms", 180))) / 1000)
            left, top, width, height = region
            width = max(1, int(width))
            height = max(1, int(height))
            logging.info(
                "OCR capture region type=%s x=%s y=%s width=%s height=%s",
                region_type,
                int(left),
                int(top),
                width,
                height,
            )
            mss_factory = mss.MSS if hasattr(mss, "MSS") else mss.mss
            with mss_factory() as shot:
                raw = shot.grab({"left": int(left), "top": int(top), "width": width, "height": height})
                image = Image.frombytes("RGB", raw.size, raw.rgb)

            self.process_ocr_image(image, region_type, (int(left), int(top), width, height))
        except Exception as exc:
            log_exception("OCR failed", exc)
            self.toast_signal.emit("OCR failed.")


def main():
    migrated_config = setup_runtime_paths()
    setup_logging()
    if migrated_config:
        logging.info("Migrated config from %s to %s", LEGACY_CONFIG_PATH, CONFIG_PATH)
    install_exception_hooks()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(APP_NAME)
    controller = AppController(app)
    app.aboutToQuit.connect(lambda: keyboard.unhook_all() if keyboard else None)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
