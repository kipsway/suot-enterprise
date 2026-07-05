import sys
import os
import json
import shutil
import webbrowser
import csv
import sqlite3
import random
from datetime import datetime, timedelta

# ==============================================================================
# ЗАЩИТА ОТ КИРИЛЛИЦЫ В ПУТЯХ К ПЛАГИНАМ QT
# ==============================================================================
def resolve_qt_plugin_path():
    try:
        import PyQt5
        base_path = os.path.dirname(PyQt5.__file__)
        plugin_path = None
        for sub_dir in ["Qt5/plugins", "Qt/plugins", "Qt5", "Qt"]:
            p = os.path.join(base_path, sub_dir if "plugins" in sub_dir else os.path.join(sub_dir, "plugins"))
            if os.path.exists(p):
                plugin_path = p
                break
        if plugin_path and sys.platform == "win32":
            import ctypes
            buf = ctypes.create_unicode_buffer(512)
            needed = ctypes.windll.kernel32.GetShortPathNameW(plugin_path, buf, 512)
            if 0 < needed < 512:
                plugin_path = buf.value
        if plugin_path:
            os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = plugin_path
    except Exception:
        pass

resolve_qt_plugin_path()
# ==============================================================================

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QTabWidget, QTableWidget, QTableWidgetItem, QPushButton, QLabel,
    QLineEdit, QComboBox, QDialog, QFormLayout, QTextEdit, QFileDialog,
    QMessageBox, QInputDialog, QHeaderView, QFrame, QProgressBar, QListWidget, 
    QListWidgetItem, QMenu, QScrollArea, QRadioButton, QButtonGroup
)
from PyQt5.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QColor, QPixmap

# ---------- Системные Константы Накопителя ----------
DATA_DIR = "data"
PHOTO_DIR = os.path.join(DATA_DIR, "photos")
DB_FILE = os.path.join(DATA_DIR, "suot_database.db")
BACKUP_DIR = "backups"
KNOWLEDGE_FILE = os.path.join(DATA_DIR, "knowledge.txt")

for path in [DATA_DIR, PHOTO_DIR, BACKUP_DIR]:
    os.makedirs(path, exist_ok=True)

# ---------- Шаблоны типовых нарушений для автозаполнения ----------
VIOLATION_TEMPLATES = [
    {"title": "Custom (Ручной ввод)", "desc": "", "cat": "Общее", "fine": "0"},
    {"title": "🚨 Отсутствие защитных ограждений", "desc": "Отсутствует защитное ограждение на перепадах высот в месте производства работ.", "cat": "Работа на высоте", "fine": "200000"},
    {"title": "🪖 Неприменение СИЗ (Каски/Спецодежда)", "desc": "Работники на строительном объекте не применяют средства индивидуаческой защиты (каски, спецобувь, спецодежду).", "cat": "Охрана труда", "fine": "50000"},
    {"title": "🔥 Нарушение требований огневых работ", "desc": "В месте производства огневых работ присутствуют легковоспламеняющиеся материалы (ЛВМ).", "cat": "Пожарная безопасность", "fine": "50000"},
    {"title": "🏗 Нарушение схемы строповки грузов", "desc": "Нарушена схема строповки, не проводится регулярный осмотр СГЗП, применяется неинвентарная тара.", "cat": "Промышленная безопасность", "fine": "50000"},
]

# ==============================================================================
# ДВИЖОК ИНИЦИАЛИЗАЦИИ И МИГРАЦИИ БАЗЫ ДАННЫХ SQLITE
# ==============================================================================
def init_sqlite_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS columns_config (category TEXT, name TEXT, type TEXT, position INTEGER)")
    cursor.execute("CREATE TABLE IF NOT EXISTS employees (id INTEGER PRIMARY KEY AUTOINCREMENT, data_json TEXT, photo_path TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS violations (id INTEGER PRIMARY KEY AUTOINCREMENT, data_json TEXT, photo_path TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS custom_templates (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, desc TEXT, cat TEXT, fine TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, action TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS textbook (short_txt TEXT PRIMARY KEY, long_txt TEXT)")
    
    # Заполнение учебника базовыми значениями автозамены
    cursor.execute("SELECT COUNT(*) FROM textbook")
    if cursor.fetchone()[0] == 0:
        default_textbook = [
            ("сиз", "Работники выполняют обязанности без обязательных средств индивидуальной защиты (каски, защитные очки, перчатки, спецобувь). Нарушение требований статьи 221 ТК РФ."),
            ("ограждение", "Отсутствуют защитные инвентарные ограждения в зонах перепада высот более 1.8м. Высокий риск падения персонала со строительных горизонтов."),
            ("инструктаж", "Персонал допущен к самостоятельной работе на опасном производственном объекте без фиксации даты проведения повторного инструктажа по охране труда."),
            ("заземление", "Обнаружено отсутствие видимого заземления корпусов распределительных электрощитов механизированного инструмента. Риск поражения током.")
        ]
        cursor.executemany("INSERT INTO textbook VALUES (?, ?)", default_textbook)
    
    cursor.execute("SELECT COUNT(*) FROM columns_config WHERE category='staff'")
    if cursor.fetchone()[0] == 0:
        default_staff = [
            ("ФИО сотрудника", "Текст", 0), ("Организация", "Текст", 1),
            ("Должность", "Текст", 2), ("Подразделение", "Текст", 3),
            ("Медосмотр", "Дата", 4), ("Инструктаж", "Дата", 5),
            ("Описание / Примечание", "Текст", 6)
        ]
        cursor.executemany("INSERT INTO columns_config VALUES ('staff', ?, ?, ?)", default_staff)
        
    cursor.execute("SELECT COUNT(*) FROM columns_config WHERE category='viol'")
    if cursor.fetchone()[0] == 0:
        default_viol = [
            ("Категория", "Текст", 0), ("Организация", "Текст", 1),
            ("Ответственное лицо", "Текст", 2), ("Суть нарушения", "Текст", 3),
            ("Штраф (руб)", "Число", 4), ("Срок", "Дата", 5), ("Статус", "Статус", 6),
            ("Дополнительное описание", "Текст", 7)
        ]
        cursor.executemany("INSERT INTO columns_config VALUES ('viol', ?, ?, ?)", default_viol)
        
    cursor.execute("INSERT OR IGNORE INTO settings VALUES ('app_name', 'Программа СУОТ и Контроля Предписаний (Pro Ultra Engine)')")
    
    conn.commit()
    conn.close()

init_sqlite_db()

# ---------- Парсинг и нормализация любых форматов дат ----------
def parse_date_safely(date_str):
    if not date_str or str(date_str).strip() in ["", "—", "None"]:
        return None
    s = str(date_str).split(" (")[0].replace(".", "-").replace("/", "-").strip()
    parts = s.split("-")
    try:
        if len(parts) == 3:
            if len(parts[0]) == 2 and len(parts[2]) == 4: # DD-MM-YYYY
                return datetime(int(parts[2]), int(parts[1]), int(parts[0]))
            if len(parts[0]) == 4 and len(parts[2]) == 2: # YYYY-MM-DD
                return datetime(int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        pass
    return None

def format_date_to_display(date_str):
    dt = parse_date_safely(date_str)
    if dt:
        return dt.strftime("%d-%m-%Y")
    return str(date_str).strip()

def get_date_status_colors(date_str, is_dark, date_mode="Действует до"):
    dt = parse_date_safely(date_str)
    if not dt:
        return ("#313244", "#a6adc8") if is_dark else ("#ffffff", "#7f8c8d")
    
    # Если дата — день проведения, то она актуальна ровно 1 год (365 дней)
    if date_mode == "Дата проведения":
        dt = dt + timedelta(days=365)
        
    today = datetime.now()
    if dt < today:
        return ("#582525", "#f38ba8") if is_dark else ("#f8d7da", "#721c24")
    elif dt <= today + timedelta(days=30):
        return ("#614d17", "#f9e2af") if is_dark else ("#fff3cd", "#856404")
    else:
        return ("#254b32", "#a6e3a1") if is_dark else ("#d4edda", "#155724")

def get_violation_status_colors(status_str, is_dark):
    status_str = str(status_str).strip()
    if status_str in ["Устранено", "Resolved"]:
        return ("#254b32", "#a6e3a1") if is_dark else ("#d4edda", "#155724")
    elif status_str in ["Активно", "Active"]:
        return ("#614d17", "#f9e2af") if is_dark else ("#fff3cd", "#856404")
    elif status_str in ["Просрочено", "Expired"]:
        return ("#582525", "#f38ba8") if is_dark else ("#f8d7da", "#721c24")
    return ("#313244", "#cdd6f4") if is_dark else ("#ffffff", "#1e1e2e")

def make_db_backup(tag="manual"):
    if os.path.exists(DB_FILE):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = os.path.join(BACKUP_DIR, f"database_backup_{tag}_{ts}.db")
        try:
            shutil.copy(DB_FILE, dst)
            backups = [os.path.join(BACKUP_DIR, f) for f in os.listdir(BACKUP_DIR) if f.endswith(".db")]
            backups.sort(key=os.path.getmtime)
            while len(backups) > 15:
                oldest = backups.pop(0)
                try: os.remove(oldest)
                except: pass
            return dst
        except Exception:
            return None
    return None

# ==============================================================================
# ОКНО СПРАВОЧНИКА ФОРМУЛИРОВОК (УЧЕБНИК АВТОЗАМЕНЫ)
# ==============================================================================
class TextbookManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Справочник автозамены формулировок ТБ")
        self.resize(700, 500)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Инструкция:</b> Введите короткое слово-триггер в первую колонку и длинный текст во вторую.\nПри вводе триггера в карточках нарушений программа автоматически подставит развернутую формулировку."))
        
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Краткая фраза (Триггер)", "Развернутая формулировка нарушения ТБ"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.table)
        
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("➕ Добавить фразу")
        add_btn.clicked.connect(self.add_row)
        del_btn = QPushButton("➖ Удалить выбранную")
        del_btn.clicked.connect(self.delete_row)
        save_btn = QPushButton("💾 Сохранить базу")
        save_btn.clicked.connect(self.save_data)
        
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(del_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)
        
        self.load_data()
        
    def load_data(self):
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT short_txt, long_txt FROM textbook ORDER BY short_txt")
        rows = c.fetchall()
        conn.close()
        
        self.table.setRowCount(len(rows))
        for idx, (short, long) in enumerate(rows):
            self.table.setItem(idx, 0, QTableWidgetItem(short))
            self.table.setItem(idx, 1, QTableWidgetItem(long))
            
    def add_row(self):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem("новый_триггер"))
        self.table.setItem(r, 1, QTableWidgetItem("Полное описание..."))
        
    def delete_row(self):
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)
            
    def save_data(self):
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("DELETE FROM textbook")
        for idx in range(self.table.rowCount()):
            short = self.table.item(idx, 0)
            long = self.table.item(idx, 1)
            if short and long and short.text().strip():
                c.execute("INSERT OR REPLACE INTO textbook VALUES (?, ?)", (short.text().strip().lower(), long.text().strip()))
        conn.commit()
        conn.close()
        QMessageBox.information(self, "Успех", "Справочник автозамены успешно обновлен!")
        self.accept()

# ==============================================================================
# ДИАЛОГИ И КАЛЬКУЛЯТОРЫ
# ==============================================================================
class FineKinneyCalculator(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowTitle("Экспресс-анализ риска по методу Файн-Кинни")
        self.resize(500, 420)
        
        main_layout = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QFormLayout(container)
        
        self.prob_cb = QComboBox()
        self.prob_cb.addItems([
            "10.0 - Ожидаемо / Очевидно", "6.0 - Вполне возможно",
            "3.0 - Необычно / Редко", "1.0 - Маловероятно",
            "0.5 - Очень маловероятно", "0.1 - Почти невозможно"
        ])
        
        self.exp_cb = QComboBox()
        self.exp_cb.addItems([
            "10.0 - Постоянно (ежедневно)", "6.0 - Часто (еженедельно)",
            "3.0 - Периодически (ежемесячно)", "2.0 - Временами",
            "1.0 - Редко", "0.5 - Очень редко"
        ])
        
        self.cons_cb = QComboBox()
        self.cons_cb.addItems([
            "100.0 - Катастрофические (несколько смертей)", "40.0 - Тяжелые (один смертельный случай)",
            "15.0 - Серьезные (стойкая утрата трудоспособности)", "7.0 - Средней тяжести (длительный больничный)",
            "3.0 - Легкие последствия (первая помощь)", "1.0 - Незначительные микротравмы"
        ])
        
        layout.addRow("Вероятность наступления (П):", self.prob_cb)
        layout.addRow("Частота воздействия опасности (Э):", self.exp_cb)
        layout.addRow("Тяжесть возможных последствий (С):", self.cons_cb)
        
        calc_btn = QPushButton("🔥 Рассчитать индекс опасности")
        calc_btn.clicked.connect(self.calculate_risk)
        layout.addRow(calc_btn)
        
        self.res_lbl = QLabel("Индекс риска (R): -")
        self.res_lbl.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addRow(self.res_lbl)
        
        self.desc_lbl = QLabel("Классификация риска: -")
        self.desc_lbl.setWordWrap(True)
        layout.addRow(self.desc_lbl)
        
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.accept)
        layout.addRow(close_btn)
        
        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def calculate_risk(self):
        p = float(self.prob_cb.currentText().split(" ")[0])
        e = float(self.exp_cb.currentText().split(" ")[0])
        c = float(self.cons_cb.currentText().split(" ")[0])
        r = p * e * c
        
        self.res_lbl.setText(f"Индекс риска (R): {r:.1f}")
        if r < 20: text, color = "Малый риск. Особых мер не требуется.", "green"
        elif r < 70: text, color = "Умеренный риск. Требуется плановый контроль.", "#f1c40f"
        elif r < 200: text, color = "Существенный риск. Нужны корректирующие действия.", "#e67e22"
        elif r < 400: text, color = "Высокий риск. Требуется немедленное вмешательство.", "red"
        else: text, color = "Критический риск! Работы должны быть остановлены!", "darkred"
        
        self.desc_lbl.setText(f"Классификация риска: <font color='{color}'><b>{text}</b></font>")


class ReorderColumnsDialog(QDialog):
    def __init__(self, columns, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowTitle("Порядок отображения колонок")
        self.resize(350, 450)
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Используйте кнопки для изменения порядка столбцов:"))
        
        self.list_widget = QListWidget()
        self.list_widget.addItems(columns)
        layout.addWidget(self.list_widget)
        
        btn_lay = QHBoxLayout()
        up_btn = QPushButton("🔼 Вверх")
        up_btn.clicked.connect(self.move_up)
        down_btn = QPushButton("🔽 Вниз")
        down_btn.clicked.connect(self.move_down)
        btn_lay.addWidget(up_btn)
        btn_lay.addWidget(down_btn)
        layout.addLayout(btn_lay)
        
        actions = QHBoxLayout()
        save = QPushButton("Применить")
        save.clicked.connect(self.accept)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        actions.addWidget(save)
        actions.addWidget(cancel)
        layout.addLayout(actions)

    def move_up(self):
        row = self.list_widget.currentRow()
        if row > 0:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(row - 1, item)
            self.list_widget.setCurrentRow(row - 1)

    def move_down(self):
        row = self.list_widget.currentRow()
        if row < self.list_widget.count() - 1 and row >= 0:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(row + 1, item)
            self.list_widget.setCurrentRow(row + 1)

    def get_result(self):
        return [self.list_widget.item(i).text() for i in range(self.list_widget.count())]


class AddColumnDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowTitle("Добавление нового параметра")
        self.resize(320, 200)
        layout = QFormLayout(self)
        
        self.name_edit = QLineEdit()
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Текст", "Дата", "Число", "Статус"])
        
        layout.addRow("Название колонки:", self.name_edit)
        layout.addRow("Тип параметра:", self.type_combo)
        
        btns = QHBoxLayout()
        ok = QPushButton("Добавить")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        layout.addRow(btns)

    def get_data(self):
        return self.name_edit.text().strip(), self.type_combo.currentText()


class DynamicEntityDialog(QDialog):
    def __init__(self, title, columns, types, current_data=None, is_violation=False, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowTitle(title)
        self.resize(600, 650)
        
        # Плавное появление диалогового окна
        self.setWindowOpacity(0.0)
        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(250)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()
        
        self.columns = columns
        self.types = types
        self.is_violation = is_violation
        self.photo_path = current_data.get("photo", "") if current_data else ""
        
        # Загрузка локального словаря учебника автозамены
        self.textbook_dict = {}
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT short_txt, long_txt FROM textbook")
            self.textbook_dict = {row[0].lower().strip(): row[1] for row in c.fetchall()}
            conn.close()
        except Exception:
            pass

        self.main_layout = QVBoxLayout(self)
        
        # Интеграция контейнера прокрутки QScrollArea для 100% читаемости без урезаний текста
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_widget = QWidget()
        self.form_layout = QFormLayout(self.scroll_widget)
        self.fields = {}
        self.date_selectors = {}

        if self.is_violation:
            self.template_combo = QComboBox()
            self.all_templates = list(VIOLATION_TEMPLATES)
            try:
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("SELECT title, desc, cat, fine FROM custom_templates")
                for r in c.fetchall():
                    self.all_templates.append({"title": r[0], "desc": r[1], "cat": r[2], "fine": r[3]})
                conn.close()
            except Exception:
                pass
                
            for t in self.all_templates:
                self.template_combo.addItem(t["title"])
            self.template_combo.currentIndexChanged.connect(self.apply_violation_template)
            self.form_layout.addRow("📋 Использовать шаблон:", self.template_combo)

        for col in self.columns:
            col_type = self.types.get(col, "Текст")
            
            if "суть" in col.lower() or "описание" in col.lower() or "примечание" in col.lower():
                widget = QTextEdit()
                widget.setText(str(current_data.get(col, "") if current_data else ""))
                widget.setMaximumHeight(90)
                widget.textChanged.connect(lambda w=widget: self.handle_live_text_replacement(w))
                self.fields[col] = widget
                self.form_layout.addRow(f"<b>{col}:</b>", widget)
                
            elif col_type == "Статус":
                widget = QComboBox()
                widget.addItems(["Активно", "Устранено", "Просрочено"])
                if current_data:
                    widget.setCurrentText(str(current_data.get(col, "Активно")))
                self.fields[col] = widget
                self.form_layout.addRow(f"<b>{col}:</b>", widget)
                
            elif col_type == "Дата":
                v_box = QVBoxLayout()
                widget = QLineEdit()
                raw_val = current_data.get(col, "") if current_data else ""
                if raw_val:
                    raw_val = format_date_to_display(str(raw_val))
                widget.setText(str(raw_val))
                widget.setPlaceholderText("ДД-ММ-ГГГГ или ГГГГ.ММ.ДД")
                widget.textChanged.connect(lambda txt, w=widget: self.handle_live_date_formatting(txt, w))
                v_box.addWidget(widget)
                
                # Селектор режима работы даты (Инструктаж / Действует до)
                radio_container = QWidget()
                r_lay = QHBoxLayout(radio_container)
                r_lay.setContentsMargins(0,0,0,0)
                rb1 = QRadioButton("Действует до")
                rb2 = QRadioButton("Дата проведения")
                
                saved_mode = current_data.get(f"{col}_mode", "Действует до") if current_data else "Действует до"
                if saved_mode == "Дата проведения": rb2.setChecked(True)
                else: rb1.setChecked(True)
                
                r_lay.addWidget(rb1)
                r_lay.addWidget(rb2)
                v_box.addWidget(radio_container)
                
                self.date_selectors[col] = (rb1, rb2)
                self.fields[col] = widget
                self.form_layout.addRow(f"<b>{col}:</b>", v_box)
            else:
                widget = QLineEdit()
                raw_val = current_data.get(col, "") if current_data else ""
                widget.setText(str(raw_val))
                if col_type == "Число":
                    widget.setPlaceholderText("Только цифры")
                self.fields[col] = widget
                self.form_layout.addRow(f"<b>{col}:</b>", widget)

        self.scroll_area.setWidget(self.scroll_widget)
        self.main_layout.addWidget(self.scroll_area)

        # Секция вложений медиа
        photo_layout = QHBoxLayout()
        photo_btn = QPushButton("📷 Прикрепить фото/доказательство")
        photo_btn.clicked.connect(self.choose_photo)
        self.photo_preview = QLabel("Нет вложений")
        self.photo_preview.setFixedSize(120, 90)
        self.photo_preview.setAlignment(Qt.AlignCenter)
        self.photo_preview.setStyleSheet("border: 1px solid #45475a; background-color: rgba(0,0,0,0.2); text-align: center;")
        photo_layout.addWidget(photo_btn)
        photo_layout.addWidget(self.photo_preview)
        self.form_layout.addRow("<b>Медиа-доказательство:</b>", photo_layout)
        self.update_photo_preview()

        btns = QHBoxLayout()
        ok = QPushButton("💾 Сохранить карточку")
        ok.clicked.connect(self.validate_and_accept)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        self.main_layout.addLayout(btns)

    def handle_live_text_replacement(self, widget):
        # Движок мгновенной автозамены слов из Кнопки Учебника
        txt = widget.toPlainText()
        words = txt.split()
        if not words: return
        last_word = words[-1].lower().strip().replace(",", "").replace(".", "")
        if last_word in self.textbook_dict:
            widget.blockSignals(True)
            expanded = self.textbook_dict[last_word]
            new_text = txt[:-len(words[-1])] + expanded
            widget.setText(new_text)
            # Перемещение курсора в конец текста
            cursor = widget.textCursor()
            cursor.movePosition(cursor.End)
            widget.setTextCursor(cursor)
            widget.blockSignals(False)

    def handle_live_date_formatting(self, text, widget):
        # Мгновенная трансформация дат вида YYYY.MM.DD или YYYY/MM/DD в пользовательский DD-MM-YYYY
        if len(text) == 10 and ("." in text or "/" in text):
            cleaned = text.replace(".", "-").replace("/", "-")
            parts = cleaned.split("-")
            if len(parts) == 3 and len(parts[0]) == 4: # Поймали формат YYYY-MM-DD
                widget.blockSignals(True)
                widget.setText(f"{parts[2]}-{parts[1]}-{parts[0]}")
                widget.blockSignals(False)

    def apply_violation_template(self, index):
        if index == 0: return
        tmpl = self.all_templates[index]
        for col in self.columns:
            widget = self.fields[col]
            if "суть" in col.lower() or "наруш" in col.lower():
                if isinstance(widget, QTextEdit): widget.setText(tmpl["desc"])
            elif "катег" in col.lower():
                if isinstance(widget, QLineEdit): widget.setText(tmpl["cat"])
            elif "штр" in col.lower():
                if isinstance(widget, QLineEdit): widget.setText(tmpl["fine"])

    def choose_photo(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выбрать вложение", "", "Изображения (*.png *.jpg *.jpeg *.pdf)")
        if path:
            if not os.path.abspath(path).startswith(os.path.abspath(PHOTO_DIR)):
                ext = os.path.splitext(path)[1]
                filename = f"att_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
                dest = os.path.join(PHOTO_DIR, filename)
                try:
                    shutil.copy(path, dest)
                    self.photo_path = dest
                except Exception:
                    self.photo_path = path
            else:
                self.photo_path = path
            self.update_photo_preview()

    def update_photo_preview(self):
        if self.photo_path and os.path.exists(self.photo_path) and self.photo_path.lower().endswith(('.png', '.jpg', '.jpeg')):
            pix = QPixmap(self.photo_path)
            if not pix.isNull():
                self.photo_preview.setPixmap(pix.scaled(120, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                return
        self.photo_preview.setText("Файл добавлен" if self.photo_path else "Нет вложений")

    def validate_and_accept(self):
        # Жесткая и безопасная валидация без падений приложения
        for col, widget in self.fields.items():
            col_type = self.types.get(col, "Текст")
            
            if isinstance(widget, QComboBox):
                text_val = widget.currentText().strip()
            elif isinstance(widget, QTextEdit):
                text_val = widget.toPlainText().strip()
            else:
                text_val = widget.text().strip()
            
            if col_type == "Дата" and text_val and text_val != "—":
                dt = parse_date_safely(text_val)
                if not dt:
                    QMessageBox.warning(self, "Ошибка валидации даты", f"Поле '{col}' требует корректную дату в формате ДД-ММ-ГГГГ")
                    return
            elif col_type == "Число" and text_val:
                try:
                    cleaned_num = "".join(x for x in text_val if x.isdigit() or x in ['.', ',']).replace(',', '.')
                    if cleaned_num: float(cleaned_num)
                except ValueError:
                    QMessageBox.warning(self, "Ошибка валидации чисел", f"Поле '{col}' должно содержать только числовые значения.")
                    return
        self.accept()

    def get_data(self):
        res = {}
        for col, widget in self.fields.items():
            if isinstance(widget, QComboBox): 
                res[col] = widget.currentText()
            elif isinstance(widget, QTextEdit): 
                res[col] = widget.toPlainText().strip()
            else: 
                val = widget.text().strip()
                if self.types.get(col) == "Дата":
                    val = format_date_to_display(val)
                res[col] = val
                
            # Сохранение режимов дат
            if col in self.date_selectors:
                rb1, rb2 = self.date_selectors[col]
                res[f"{col}_mode"] = "Дата проведения" if rb2.isChecked() else "Действует до"
                
        res["photo"] = self.photo_path
        return res

# ==============================================================================
# ГЛАВНОЕ ОКНО ПРИЛОЖЕНИЯ СУОТ (ЯДРО И ИНТЕРФЕЙС)
# ==============================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        make_db_backup("startup")
        
        self.dark = True
        self.staff_filter_mode = "Все"
        self.viol_filter_mode = "Все"
        
        self.staff_sort_col = 0
        self.staff_sort_asc = True
        self.viol_sort_col = 0
        self.viol_sort_asc = True

        self.resize(1600, 950)
        
        # Эффект плавного появления главного окна
        self.setWindowOpacity(0.0)
        self.main_anim = QPropertyAnimation(self, b"windowOpacity")
        self.main_anim.setDuration(400)
        self.main_anim.setStartValue(0.0)
        self.main_anim.setEndValue(1.0)
        self.main_anim.start()

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # Конвейер панелей инструментов
        toolbar = QHBoxLayout()
        for text, fn in [
            ("🌓 Тема", self.toggle_theme),
            ("📚 Справочник Автозамены", self.open_textbook_manager),
            ("🏢 Аудит Подрядчиков", self.global_contractor_analytics),
            ("📊 Категории Рисков", self.global_category_analytics),
            ("📋 Создать Шаблон", self.register_custom_violation_template),
            ("💾 Выгрузить .LOG", self.export_audit_log_to_file),
            ("🧮 Файн-Кинни", self.open_fine_kinney_calculator),
            ("🔄 Точки отката", self.global_restore_from_backup),
            ("🔍 Сквозной Поиск", self.global_cross_search),
            ("📊 Генеральный Отчет", self.generate_global_report),
            ("📚 База Нормативов", self.open_knowledge),
            ("⚙️ Имя ПО", self.open_settings),
            ("🛡️ Создать Бэкап", lambda: [make_db_backup("manual_click"), QMessageBox.information(self, "Бэкап", "Резервная копия успешно создана в папке backups!")])
        ]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            toolbar.addWidget(b)
        toolbar.addStretch()
        main_layout.addLayout(toolbar)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        self.dashboard_tab = QWidget()
        self.staff_tab = QWidget()
        self.violation_tab = QWidget()

        self.tabs.addTab(self.dashboard_tab, "📊 Информационная Панель")
        self.tabs.addTab(self.staff_tab, "👥 Управление Персоналом")
        self.tabs.addTab(self.violation_tab, "⚠️ Реестр Предписаний")

        self.build_dashboard()
        self.build_staff()
        self.build_violations()

        self.apply_theme()
        self.refresh_all()
        self.run_startup_analyzer()

    def log_action(self, text):
        ts = datetime.now().strftime('%d.%m.%Y %H:%M:%S')
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("INSERT INTO audit_log (timestamp, action) VALUES (?, ?)", (ts, text))
            conn.commit()
            conn.close()
        except Exception:
            pass
        self.update_audit_viewer_ui()

    def update_audit_viewer_ui(self):
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT timestamp, action FROM audit_log ORDER BY id DESC LIMIT 300")
            logs = [f"[{r[0]}] {r[1]}" for r in c.fetchall()]
            conn.close()
            self.audit_viewer.setText("\n".join(logs))
        except Exception:
            pass

    def open_fine_kinney_calculator(self):
        FineKinneyCalculator(self).exec_()
        
    def open_textbook_manager(self):
        TextbookManagerDialog(self).exec_()
        self.refresh_all()

    # ===== ТАБ 1: Панель мониторинга структуры =====
    def build_dashboard(self):
        layout = QVBoxLayout(self.dashboard_tab)
        grid = QGridLayout()
        
        self.card_emps = self.make_card("Сотрудников в базе SQLite", "0", "#3498db")
        self.card_expired = self.make_card("Просроченные документы", "0", "#e74c3c")
        self.card_viols = self.make_card("Действующие предписания", "0", "#9b59b6")
        self.card_fines = self.make_card("Накопленные штрафы", "0.00 руб", "#e67e22")
        
        grid.addWidget(self.card_emps, 0, 0)
        grid.addWidget(self.card_expired, 0, 1)
        grid.addWidget(self.card_viols, 1, 0)
        grid.addWidget(self.card_fines, 1, 1)
        layout.addLayout(grid)

        p_lay = QHBoxLayout()
        self.p1 = QProgressBar()
        self.p1.setFormat("Легитимность допусков и медосмотров: %p%")
        self.p2 = QProgressBar()
        self.p2.setFormat("Процент устраненных предписаний ТБ: %p%")
        p_lay.addWidget(self.p1)
        p_lay.addWidget(self.p2)
        layout.addLayout(p_lay)

        split_layout = QHBoxLayout()
        
        left_vbox = QVBoxLayout()
        left_vbox.addWidget(QLabel("<b>🚨 Панель оперативного внимания (Критические риски - Клик для изменения):</b>"))
        self.critical_tasks_list = QListWidget()
        self.critical_tasks_list.itemDoubleClicked.connect(self.on_critical_task_double_clicked)
        left_vbox.addWidget(self.critical_tasks_list)
        
        right_vbox = QVBoxLayout()
        right_vbox.addWidget(QLabel("<b>🕒 Системный Журнал Действий (Audit Trail из SQLite):</b>"))
        self.audit_viewer = QTextEdit()
        self.audit_viewer.setReadOnly(True)
        self.audit_viewer.setStyleSheet("font-family: 'Consolas', monospace; font-size: 11px;")
        right_vbox.addWidget(self.audit_viewer)
        
        split_layout.addLayout(left_vbox, 1)
        split_layout.addLayout(right_vbox, 1)
        layout.addLayout(split_layout)

    def make_card(self, title, val, color):
        f = QFrame()
        f.setObjectName("CardFrame")
        f.setMinimumHeight(100)
        v = QVBoxLayout(f)
        t_lbl = QLabel(title)
        v_lbl = QLabel(val)
        v_lbl.setStyleSheet(f"font-size: 26px; font-weight: bold; color: {color};")
        v.addWidget(t_lbl)
        v.addWidget(v_lbl, 0, Qt.AlignLeft)
        f.v_lbl = v_lbl
        return f

    def get_columns_metadata(self, category):
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT name, type FROM columns_config WHERE category=? ORDER BY position", (category,))
        rows = c.fetchall()
        conn.close()
        cols = [r[0] for r in rows]
        types = {r[0]: r[1] for r in rows}
        return cols, types

    def run_startup_analyzer(self):
        crit_docs = 0
        crit_viols = 0
        today = datetime.now()
        
        staff_cols, staff_types = self.get_columns_metadata("staff")
        viol_cols, viol_types = self.get_columns_metadata("viol")
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        c.execute("SELECT data_json FROM employees")
        for row in c.fetchall():
            item = json.loads(row[0])
            for col in staff_cols:
                if staff_types.get(col) == "Дата" and item.get(col):
                    dt = parse_date_safely(item[col])
                    if dt:
                        mode = item.get(f"{col}_mode", "Действует до")
                        if mode == "Дата проведения": dt += timedelta(days=365)
                        if dt < today: crit_docs += 1
                    
        status_col = next((col for col in viol_cols if "стат" in col.lower()), "Статус")
        c.execute("SELECT data_json FROM violations")
        for row in c.fetchall():
            item = json.loads(row[0])
            if item.get(status_col) in ["Активно", "Просрочено"]: 
                crit_viols += 1
                
        conn.close()
        
        if crit_docs > 0 or crit_viols > 0:
            QMessageBox.warning(self, "🔔 Экспресс-Анализатор СУОТ", 
                f"Внимание! Обнаружены критические индикаторы рисков:\n\n"
                f"🛑 Истекшие документы сотрудников: {crit_docs} шт.\n"
                f"🚨 Открытые предписания надзора: {crit_viols} шт.\n\n"
                f"Используйте 'Панель оперативного внимания' для быстрого исправления.")

    def update_dashboard(self):
        staff_cols, staff_types = self.get_columns_metadata("staff")
        viol_cols, viol_types = self.get_columns_metadata("viol")
        
        status_col = next((c for c in viol_cols if "стат" in c.lower()), "Статус")
        term_col = next((c for c in viol_cols if "срок" in c.lower() or "дата" in c.lower()), None)
        fine_col = next((c for c in viol_cols if "штр" in c.lower()), None)
        today = datetime.now()

        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        c.execute("SELECT id, data_json FROM violations")
        for r_id, d_json in c.fetchall():
            v = json.loads(d_json)
            if v.get(status_col) == "Активно" and term_col and v.get(term_col):
                dt = parse_date_safely(v[term_col])
                if dt:
                    mode = v.get(f"{term_col}_mode", "Действует до")
                    if mode == "Дата проведения": dt += timedelta(days=365)
                    if dt < today:
                        v[status_col] = "Просрочено"
                        c.execute("UPDATE violations SET data_json=? WHERE id=?", (json.dumps(v, ensure_ascii=False), r_id))
        conn.commit()

        c.execute("SELECT COUNT(*) FROM employees")
        self.card_emps.v_lbl.setText(str(c.fetchone()[0]))
        
        self.critical_tasks_list.clear()
        
        exp_docs = total_dates = valid_dates = 0
        c.execute("SELECT id, data_json FROM employees")
        for r_id, row in c.fetchall():
            e = json.loads(row)
            name_val = list(e.values())[0] if e else "Неизвестный"
            for col in staff_cols:
                if staff_types.get(col) == "Дата" and e.get(col):
                    total_dates += 1
                    dt = parse_date_safely(e[col])
                    if dt:
                        mode = e.get(f"{col}_mode", "Действует до")
                        if mode == "Дата проведения": dt += timedelta(days=365)
                        
                        if dt < today: 
                            exp_docs += 1
                            lit = QListWidgetItem(f"👤 [Персонал] Просрочен '{col}' у {name_val} (Срок до: {dt.strftime('%d-%m-%Y')})")
                            lit.setData(Qt.UserRole, r_id)
                            lit.setData(Qt.UserRole + 1, "staff")
                            lit.setForeground(QColor("#f38ba8" if self.dark else "#721c24"))
                            self.critical_tasks_list.addItem(lit)
                        else: 
                            valid_dates += 1
        self.card_expired.v_lbl.setText(str(exp_docs))

        act_viols = res_viols = 0
        total_fines = 0.0
        c.execute("SELECT id, data_json FROM violations")
        for r_id, row in c.fetchall():
            v = json.loads(row)
            st = v.get(status_col, "Активно")
            org_val = v.get("Организация", "Подрядчик")
            desc_val = v.get("Суть нарушения", "Замечание")
            
            if st in ["Активно", "Просрочено"]: 
                act_viols += 1
                lit = QListWidgetItem(f"🚨 [Предписание №{r_id}] {st} | {org_val}: {desc_val[:40]}...")
                lit.setData(Qt.UserRole, r_id)
                lit.setData(Qt.UserRole + 1, "viol")
                lit.setForeground(QColor("#f9e2af" if st == "Активно" else "#f38ba8"))
                self.critical_tasks_list.addItem(lit)
                
            if st == "Устранено": res_viols += 1
            if fine_col and v.get(fine_col):
                try:
                    cleaned = "".join(x for x in str(v[fine_col]) if x.isdigit() or x == '.')
                    if cleaned: total_fines += float(cleaned)
                except ValueError: pass

        conn.close()

        self.card_viols.v_lbl.setText(str(act_viols))
        self.card_fines.v_lbl.setText(f"{total_fines:,.2f} руб".replace(",", " "))
        self.p1.setValue(int((valid_dates / total_dates * 100)) if total_dates > 0 else 100)
        
        total_v_records = act_viols + res_viols
        self.p2.setValue(int((res_viols / total_v_records * 100)) if total_v_records > 0 else 100)
        
        if self.critical_tasks_list.count() == 0:
            self.critical_tasks_list.addItem("🟢 Критических рисков и просроченных документов не обнаружено.")
            
        self.update_audit_viewer_ui()

        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT value FROM settings WHERE key='app_name'")
            res = c.fetchone()
            if res: self.setWindowTitle(res[0])
            conn.close()
        except Exception: pass

    def on_critical_task_double_clicked(self, item):
        db_id = item.data(Qt.UserRole)
        mode = item.data(Qt.UserRole + 1)
        if not db_id or not mode: return
        
        if mode == "staff":
            self.tabs.setCurrentIndex(1)
            self.open_edit_staff_by_id(db_id)
        elif mode == "viol":
            self.tabs.setCurrentIndex(2)
            self.open_edit_viol_by_id(db_id)

    def open_edit_staff_by_id(self, db_id):
        cols, types = self.get_columns_metadata("staff")
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT data_json, photo_path FROM employees WHERE id=?", (db_id,))
        res = c.fetchone()
        conn.close()
        if not res: return
        curr_data = json.loads(res[0])
        curr_data["photo"] = res[1]
        
        dlg = DynamicEntityDialog("Редактирование профиля (Диспетчер)", cols, types, curr_data, parent=self)
        if dlg.exec_():
            updated = dlg.get_data()
            photo = updated.pop("photo", "")
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("UPDATE employees SET data_json=?, photo_path=? WHERE id=?", (json.dumps(updated, ensure_ascii=False), photo, db_id))
            conn.commit()
            conn.close()
            self.log_action(f"Изменен сотрудник ID: {db_id} через Диспетчер")
            self.refresh_all()

    def open_edit_viol_by_id(self, db_id):
        cols, types = self.get_columns_metadata("viol")
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT data_json, photo_path FROM violations WHERE id=?", (db_id,))
        res = c.fetchone()
        conn.close()
        if not res: return
        curr_data = json.loads(res[0])
        curr_data["photo"] = res[1]
        
        dlg = DynamicEntityDialog("Материалы дела (Диспетчер)", cols, types, curr_data, is_violation=True, parent=self)
        if dlg.exec_():
            updated = dlg.get_data()
            photo = updated.pop("photo", "")
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("UPDATE violations SET data_json=?, photo_path=? WHERE id=?", (json.dumps(updated, ensure_ascii=False), photo, db_id))
            conn.commit()
            conn.close()
            self.log_action(f"Обновлено предписание №{db_id} через Диспетчер")
            self.refresh_all()

    # ===== ТАБ 2: Персонал =====
    def build_staff(self):
        layout = QVBoxLayout(self.staff_tab)
        
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("<b>🚦 Фильтр и Сортировка Допусков:</b>"))
        
        self.staff_filter_combo = QComboBox()
        self.staff_filter_combo.addItems([
            "Все сотрудники", 
            "Только с просроченными допусками", 
            "Допуски истекают в ближайшие 30 дней",
            "Все документы в норме (Зеленые)",
            "Сортировка: ФИО по алфавиту"
        ])
        self.staff_filter_combo.currentIndexChanged.connect(self.handle_staff_filter_combo_change)
        filter_layout.addWidget(self.staff_filter_combo)
        
        filter_layout.addWidget(QLabel(" <b>🏢 Компания:</b>"))
        self.staff_org_filter = QComboBox()
        self.staff_org_filter.currentIndexChanged.connect(self.refresh_staff_table)
        filter_layout.addWidget(self.staff_org_filter)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        ctrl = QHBoxLayout()
        self.staff_search = QLineEdit()
        self.staff_search.setPlaceholderText("🔍 Живой мгновенный поиск сотрудников по всем полям на лету...")
        self.staff_search.textChanged.connect(self.refresh_staff_table)
        ctrl.addWidget(self.staff_search)

        for text, fn in [
            ("➕ Добавить", self.add_employee),
            ("🖼 Файл до допуска", self.view_staff_photo),
            ("🪪 Паспорт ТБ (.DOC)", self.export_single_employee_passport),
            ("➖ Исключить", self.delete_employee),
            ("➕ Колонку", lambda: self.add_column_logic("staff")),
            ("🔀 Порядок", lambda: self.reorder_columns_logic("staff")),
            ("❌ Удалить параметр", lambda: self.delete_column_logic("staff")),
            ("📥 Импорт Excel", lambda: self.import_excel_logic("staff")),
            ("⬇️ Экспорт Excel", self.export_staff_excel),
            ("📊 В CSV файл", lambda: self.export_to_csv_logic("staff", "Реестр_Персонала.csv")),
        ]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            ctrl.addWidget(b)
        layout.addLayout(ctrl)

        self.staff_table = QTableWidget()
        self.staff_table.verticalHeader().setVisible(False)
        self.staff_table.horizontalHeader().sectionClicked.connect(self.handle_staff_header_click)
        self.staff_table.cellDoubleClicked.connect(self.edit_employee)
        self.staff_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.staff_table.customContextMenuRequested.connect(self.show_staff_context_menu)
        layout.addWidget(self.staff_table)

    def handle_staff_filter_combo_change(self, index):
        modes = {0: "Все", 1: "Просрочен", 2: "Истекает30", 3: "Норма", 4: "Алфавит"}
        self.staff_filter_mode = modes.get(index, "Все")
        self.refresh_staff_table()

    def show_staff_context_menu(self, pos):
        row = self.staff_table.rowAt(pos.y())
        if row < 0: return
        item_zero = self.staff_table.item(row, 0)
        if item_zero is None: return
        db_id = item_zero.data(Qt.UserRole)
        if db_id is None: return
        
        menu = QMenu(self)
        edit_card = menu.addAction("📝 Карточка редактирования")
        gen_pass = menu.addAction("🔑 Сгенерировать ПИН доступа ТБ")
        menu.addSeparator()
        
        cols, types = self.get_columns_metadata("staff")
        date_actions = {}
        for col in cols:
            if types.get(col) == "Дата":
                act = menu.addAction(f"📅 Обновить '{col}'")
                date_actions[act] = col
                
        menu.addSeparator()
        passport_act = menu.addAction("🪪 Сформировать Паспорт ТБ (.doc)")
        delete_act = menu.addAction("➖ Быстрое удаление")
        
        action = menu.exec_(self.staff_table.viewport().mapToGlobal(pos))
        if not action: return
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        if action == edit_card:
            self.staff_table.setCurrentCell(row, 0)
            self.edit_employee()
            conn.close()
            return
        elif action == gen_pass:
            pin = random.randint(100000, 999999)
            QMessageBox.information(self, "Ключ сгенерирован", f"Персональный цифровой ПИН-код сотрудника для терминала самопроверки: {pin}")
            self.log_action(f"Сгенерирован ПИН безопасности для ID {db_id}")
        elif action in date_actions:
            col_name = date_actions[action]
            c.execute("SELECT data_json FROM employees WHERE id=?", (db_id,))
            curr_data = json.loads(c.fetchone()[0])
            old_date = format_date_to_display(str(curr_data.get(col_name, datetime.now().strftime("%d-%m-%Y"))))
            
            new_val, ok = QInputDialog.getText(self, "Дата", f"Новая дата для '{col_name}' (ДД-ММ-ГГГГ):", text=old_date)
            if ok and new_val.strip():
                dt = parse_date_safely(new_val)
                if dt:
                    curr_data[col_name] = dt.strftime("%d-%m-%Y")
                    c.execute("UPDATE employees SET data_json=? WHERE id=?", (json.dumps(curr_data, ensure_ascii=False), db_id))
                    conn.commit()
                    self.log_action(f"[ПКМ] Сдвинут срок '{col_name}' сотруднику ID {db_id}: {new_val.strip()}")
                else:
                    QMessageBox.warning(self, "Ошибка", "Неверный формат даты.")
        elif action == passport_act:
            self.staff_table.setCurrentCell(row, 0)
            self.export_single_employee_passport()
        elif action == delete_act:
            self.staff_table.setCurrentCell(row, 0)
            self.delete_employee()
            
        conn.close()
        self.refresh_all()

    def handle_staff_header_click(self, logical_index):
        if self.staff_sort_col == logical_index: self.staff_sort_asc = not self.staff_sort_asc
        else:
            self.staff_sort_col = logical_index
            self.staff_sort_asc = True
        self.refresh_staff_table()

    def refresh_staff_table(self):
        cols, types = self.get_columns_metadata("staff")
        display_headers = ["№"] + cols
        
        if 0 <= self.staff_sort_col < len(display_headers):
            c_name = display_headers[self.staff_sort_col]
            display_headers[self.staff_sort_col] = c_name + (" ▲" if self.staff_sort_asc else " ▼")
            
        self.staff_table.setColumnCount(len(display_headers))
        self.staff_table.setHorizontalHeaderLabels(display_headers)

        search = self.staff_search.text().lower()
        org_col = next((c for c in cols if "орг" in c.lower() or "комп" in c.lower()), None)
        selected_org = self.staff_org_filter.currentText()
        today = datetime.now()
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, data_json, photo_path FROM employees")
        
        rows = []
        for db_id, d_json, p_path in c.fetchall():
            e = json.loads(d_json)
            e["photo"] = p_path
            
            if org_col and selected_org != "" and selected_org != "Все организации":
                if str(e.get(org_col, "")).strip() != selected_org: continue

            full_text = " ".join([str(v) for v in e.values()]).lower()
            if search and search not in full_text: continue
            
            has_expired = False
            has_warning30 = False
            has_date_fields = False
            
            for col in cols:
                if types.get(col) == "Дата" and e.get(col):
                    has_date_fields = True
                    dt = parse_date_safely(e[col])
                    if dt:
                        mode = e.get(f"{col}_mode", "Действует до")
                        if mode == "Дата проведения": dt += timedelta(days=365)
                        
                        if dt < today: has_expired = True
                        elif dt <= today + timedelta(days=30): has_warning30 = True
                    
            if self.staff_filter_mode == "Просрочен" and not has_expired: continue
            if self.staff_filter_mode == "Истекает30" and not has_warning30: continue
            if self.staff_filter_mode == "Норма" and (has_expired or has_warning30): continue
            
            rows.append((db_id, e))
        conn.close()

        # Движки сложной интеллектуальной сортировки
        if self.staff_filter_mode == "Алфавит":
            rows.sort(key=lambda x: str(list(x[1].values())[0]).lower())
        elif self.staff_sort_col == 0:
            rows.sort(key=lambda x: x[0], reverse=not self.staff_sort_asc)
        else:
            col_target = cols[self.staff_sort_col - 1]
            c_type = types.get(col_target, "Текст")
            
            def staff_sort_engine(item):
                v = item[1].get(col_target, "")
                if not v: return (1, "") if self.staff_sort_asc else (-1, "")
                if c_type == "Число":
                    try: return (0, float(str(v).replace(" ", "").replace(",", ".")))
                    except: return (0, 0.0)
                return (0, str(v).lower())
            rows.sort(key=staff_sort_engine, reverse=not self.staff_sort_asc)

        self.staff_table.setRowCount(len(rows))
        for r_idx, (db_id, e) in enumerate(rows):
            num_item = QTableWidgetItem(str(r_idx + 1))
            num_item.setData(Qt.UserRole, db_id)
            self.staff_table.setItem(r_idx, 0, num_item)
            
            for c_idx, col in enumerate(cols):
                val = e.get(col, "")
                disp_text = format_date_to_display(str(val)) if types.get(col) == "Дата" else str(val)
                item = QTableWidgetItem(disp_text if val else "—")
                
                if types.get(col) == "Дата":
                    mode = e.get(f"{col}_mode", "Действует до")
                    colors = get_date_status_colors(str(val), self.dark, mode)
                    item.setBackground(QColor(colors[0]))
                    item.setForeground(QColor(colors[1]))
                else:
                    item.setForeground(QColor("#cdd6f4" if self.dark else "#1e1e2e"))
                self.staff_table.setItem(r_idx, 1 + c_idx, item)
                
        self.staff_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

    def add_employee(self):
        cols, types = self.get_columns_metadata("staff")
        dlg = DynamicEntityDialog("Создание сотрудника в СУОТ", cols, types, parent=self)
        if dlg.exec_():
            res = dlg.get_data()
            photo = res.pop("photo", "")
            try:
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("INSERT INTO employees (data_json, photo_path) VALUES (?, ?)", (json.dumps(res, ensure_ascii=False), photo))
                conn.commit()
                conn.close()
                self.log_action(f"Добавлен работник: {list(res.values())[0]}")
            except Exception as ex:
                QMessageBox.critical(self, "Ошибка БД", str(ex))
            self.refresh_all()

    def edit_employee(self):
        row = self.staff_table.currentRow()
        if row < 0: return
        item_zero = self.staff_table.item(row, 0)
        if item_zero is None: return
        db_id = item_zero.data(Qt.UserRole)
        
        cols, types = self.get_columns_metadata("staff")
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT data_json, photo_path FROM employees WHERE id=?", (db_id,))
        res = c.fetchone()
        conn.close()
        
        if not res: return
        curr_data = json.loads(res[0])
        curr_data["photo"] = res[1]
        
        dlg = DynamicEntityDialog("Редактирование профиля", cols, types, curr_data, parent=self)
        if dlg.exec_():
            updated = dlg.get_data()
            photo = updated.pop("photo", "")
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("UPDATE employees SET data_json=?, photo_path=? WHERE id=?", (json.dumps(updated, ensure_ascii=False), photo, db_id))
            conn.commit()
            conn.close()
            self.log_action(f"Изменены данные сотрудника ID: {db_id}")
            self.refresh_all()

    def view_staff_photo(self):
        row = self.staff_table.currentRow()
        if row < 0: return
        item_zero = self.staff_table.item(row, 0)
        if item_zero is None: return
        db_id = item_zero.data(Qt.UserRole)
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT photo_path FROM employees WHERE id=?", (db_id,))
        p = c.fetchone()[0]
        conn.close()
        
        if p and os.path.exists(p): webbrowser.open(p)
        else: QMessageBox.information(self, "Уведомление", "Медиафайлы отсутствуют.")

    def export_single_employee_passport(self):
        row = self.staff_table.currentRow()
        if row < 0: return
        item_zero = self.staff_table.item(row, 0)
        if item_zero is None: return
        db_id = item_zero.data(Qt.UserRole)
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT data_json FROM employees WHERE id=?", (db_id,))
        emp = json.loads(c.fetchone()[0])
        conn.close()
        
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить Паспорт ТБ", f"Паспорт_ТБ_ID_{db_id}.doc", "MS Word (*.doc)")
        if not path: return
        
        rows_html = "".join([f"<tr><td style='background-color:#f2f2f2; font-weight:bold; width:35%; border:1px solid #000; padding:8px;'>{k}</td><td style='border:1px solid #000; padding:8px;'>{v}</td></tr>" for k, v in emp.items() if not k.endswith("_mode")])
        
        word_html = f"""
        <html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word' xmlns='http://www.w3.org/TR/REC-html40'>
        <head><meta charset='utf-8'><title>Паспорт Безопасности</title>
        <style>body {{ font-family: Arial, sans-serif; }} table {{ width: 100%; border-collapse: collapse; }}</style>
        </head>
        <body>
            <h2 style='text-align: center; color: #1a365d;'>ЛИЧНЫЙ ПАСПОРТ БЕЗОПАСНОСТИ РАБОТНИКА</h2>
            <p style='text-align: right; font-size:12px;'>Система СУОТ SQLite Engine | Дата: {datetime.now().strftime('%d.%m.%Y')}</p>
            <hr/>
            <table style='border:1px solid #000;'>{rows_html}</table>
            <br/><br/>
            <p><b>Служба Охраны Труда и Производственной Безопасности:</b> ___________ / ___________</p>
        </body></html>
        """
        try:
            with open(path, "w", encoding="utf-8") as f: f.write(word_html)
            self.log_action(f"Сгенерирован редактируемый Word документ для сотрудника ID: {db_id}")
            QMessageBox.information(self, "Успех", "Документ успешно экспортирован и готов к редактированию в MS Word!")
        except Exception as ex:
            QMessageBox.critical(self, "Ошибка сохранения", str(ex))

    def delete_employee(self):
        row = self.staff_table.currentRow()
        if row < 0: return
        item_zero = self.staff_table.item(row, 0)
        if item_zero is None: return
        db_id = item_zero.data(Qt.UserRole)
        
        if QMessageBox.question(self, "Удаление", "Исключить сотрудника из базы данных?") == QMessageBox.Yes:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("DELETE FROM employees WHERE id=?", (db_id,))
            conn.commit()
            conn.close()
            self.log_action(f"Исключен работник ID: {db_id}")
            self.refresh_all()

    # ===== ТАБ 3: Реестр Предписаний Надзора =====
    def build_violations(self):
        layout = QVBoxLayout(self.violation_tab)
        
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("<b>🚦 Сводный Селектор Статусов:</b>"))
        
        self.viol_filter_combo = QComboBox()
        self.viol_filter_combo.addItems(["Все предписания", "Только Активно", "Только Устранено", "Только Просрочено"])
        self.viol_filter_combo.currentIndexChanged.connect(self.handle_viol_filter_combo_change)
        filter_layout.addWidget(self.viol_filter_combo)
        
        filter_layout.addWidget(QLabel(" <b>🏢 Компания:</b>"))
        self.viol_org_filter = QComboBox()
        self.viol_org_filter.currentIndexChanged.connect(self.refresh_viol_table)
        filter_layout.addWidget(self.viol_org_filter)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        ctrl = QHBoxLayout()
        self.viol_search = QLineEdit()
        self.viol_search.setPlaceholderText("🔍 Умный мгновенный поиск предписаний (по контексту, подрядчику, суммам, датам)...")
        self.viol_search.textChanged.connect(self.refresh_viol_table)
        ctrl.addWidget(self.viol_search)

        for text, fn in [
            ("➕ Выдать Предписание", self.add_violation),
            ("🖼 Фотофиксация", self.view_viol_photo),
            ("🗄 Архивировать устраненные", self.archive_resolved_violations),
            ("➖ Исключить пункт", self.delete_violation),
            ("➕ Колонку", lambda: self.add_column_logic("viol")),
            ("🔀 Порядок", lambda: self.reorder_columns_logic("viol")),
            ("❌ Удалить параметр", lambda: self.delete_column_logic("viol")),
            ("📥 Импорт Excel", lambda: self.import_excel_logic("viol")),
            ("🖨 Печать Бланка (.DOC)", self.print_violation_report_word),
        ]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            ctrl.addWidget(b)
        layout.addLayout(ctrl)

        self.viol_table = QTableWidget()
        self.viol_table.verticalHeader().setVisible(False)
        self.viol_table.horizontalHeader().sectionClicked.connect(self.handle_viol_header_click)
        self.viol_table.cellDoubleClicked.connect(self.edit_violation)
        self.viol_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.viol_table.customContextMenuRequested.connect(self.show_viol_context_menu)
        layout.addWidget(self.viol_table)

    def handle_viol_filter_combo_change(self, index):
        mapping = {0: "Все", 1: "Actively", 2: "Устранено", 3: "Просрочено"}
        self.viol_filter_mode = mapping.get(index, "Все")
        # Синхронизация строк локализации
        if index == 1: self.viol_filter_mode = "Активно"
        self.refresh_viol_table()

    def show_viol_context_menu(self, pos):
        row = self.viol_table.rowAt(pos.y())
        if row < 0: return
        item_zero = self.viol_table.item(row, 0)
        if item_zero is None: return
        db_id = item_zero.data(Qt.UserRole)
        if db_id is None: return
        
        menu = QMenu(self)
        status_menu = menu.addMenu("🔄 Изменить текущий статус")
        act_active = status_menu.addAction("🔘 Активно")
        act_resolved = status_menu.addAction("🟢 Устранено")
        act_expired = status_menu.addAction("🔴 Просрочено")
        
        edit_fine = menu.addAction("💰 Скорректировать штраф")
        edit_term = menu.addAction("📅 Сдвинуть дедлайн")
        menu.addSeparator()
        print_blank = menu.addAction("🖨 Сформировать предписание Word")
        delete_item = menu.addAction("➖ Удалить из архива БД")
        
        action = menu.exec_(self.viol_table.viewport().mapToGlobal(pos))
        if not action: return
        
        cols, _ = self.get_columns_metadata("viol")
        status_col = next((c for c in cols if "стат" in c.lower()), "Статус")
        fine_col = next((c for c in cols if "штр" in c.lower()), None)
        term_col = next((c for c in cols if "срок" in c.lower() or "дата" in c.lower()), None)
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT data_json FROM violations WHERE id=?", (db_id,))
        item_data = json.loads(c.fetchone()[0])
        
        if action == act_active:
            item_data[status_col] = "Alternating"
            item_data[status_col] = "Активно"
            self.log_action(f"[ПКМ] Предписание ID {db_id} -> Активно")
        elif action == act_resolved:
            item_data[status_col] = "Устранено"
            self.log_action(f"[ПКМ] Предписание ID {db_id} -> Устранено")
        elif action == act_expired:
            item_data[status_col] = "Просрочено"
            self.log_action(f"[ПКМ] Предписание ID {db_id} -> Просрочено")
        elif action == edit_fine and fine_col:
            new_f, ok = QInputDialog.getText(self, "Штраф", "Сумма штрафа (руб):", text=str(item_data.get(fine_col, "0")))
            if ok: item_data[fine_col] = new_f.strip()
        elif action == edit_term and term_col:
            new_t, ok = QInputDialog.getText(self, "Срок", "Дедлайн (ДД-ММ-ГГГГ):", text=str(item_data.get(term_col, "")))
            if ok and new_t.strip():
                dt = parse_date_safely(new_t)
                if dt: item_data[term_col] = dt.strftime("%d-%m-%Y")
                
        c.execute("UPDATE violations SET data_json=? WHERE id=?", (json.dumps(item_data, ensure_ascii=False), db_id))
        conn.commit()
        conn.close()
        
        if action == print_blank: self.print_violation_report_word()
        elif action == delete_item: self.delete_violation()
        
        self.refresh_all()

    def handle_viol_header_click(self, logical_index):
        if self.viol_sort_col == logical_index: self.viol_sort_asc = not self.viol_sort_asc
        else:
            self.viol_sort_col = logical_index
            self.viol_sort_asc = True
        self.refresh_viol_table()

    def refresh_viol_table(self):
        cols, types = self.get_columns_metadata("viol")
        display_headers = ["№"] + cols
        
        if 0 <= self.viol_sort_col < len(display_headers):
            display_headers[self.viol_sort_col] = display_headers[self.viol_sort_col] + (" ▲" if self.viol_sort_asc else " ▼")
            
        self.viol_table.setColumnCount(len(display_headers))
        self.viol_table.setHorizontalHeaderLabels(display_headers)

        search = self.viol_search.text().lower()
        status_col = next((c for c in cols if "стат" in c.lower()), "Статус")
        org_col = next((c for c in cols if "орг" in c.lower()), None)
        selected_org = self.viol_org_filter.currentText()
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, data_json, photo_path FROM violations")
        
        rows = []
        for db_id, d_json, p_path in c.fetchall():
            v = json.loads(d_json)
            v["photo"] = p_path
            
            if org_col and selected_org != "" and selected_org != "Все организации":
                if str(v.get(org_col, "")).strip() != selected_org: continue
                
            full_text = " ".join([str(val) for val in v.values()]).lower()
            if search and search not in full_text: continue
            
            st = v.get(status_col, "Активно")
            if self.viol_filter_mode != "Все" and st != self.viol_filter_mode: continue
            rows.append((db_id, v))
        conn.close()

        if self.viol_sort_col == 0:
            rows.sort(key=lambda x: x[0], reverse=not self.viol_sort_asc)
        else:
            col_target = cols[self.viol_sort_col - 1]
            c_type = types.get(col_target, "Текст")
            
            def viol_sort_engine(item):
                val = item[1].get(col_target, "")
                if not val: return (1, "") if self.viol_sort_asc else (-1, "")
                if c_type == "Число":
                    try: return (0, float(str(val).replace(" ", "").replace(",", ".")))
                    except: return (0, 0.0)
                return (0, str(val).lower())
            rows.sort(key=viol_sort_engine, reverse=not self.viol_sort_asc)

        self.viol_table.setRowCount(len(rows))
        for r_idx, (db_id, v) in enumerate(rows):
            num_item = QTableWidgetItem(str(r_idx + 1))
            num_item.setData(Qt.UserRole, db_id)
            self.viol_table.setItem(r_idx, 0, num_item)
            
            st_val = v.get(status_col, "Активно")
            row_colors = get_violation_status_colors(st_val, self.dark)
            
            for c_idx, col in enumerate(cols):
                val = v.get(col, "")
                disp_text = format_date_to_display(str(val)) if types.get(col) == "Дата" else str(val)
                item = QTableWidgetItem(disp_text if val else "—")
                
                colors = None
                if types.get(col) == "Статус":
                    colors = row_colors
                elif types.get(col) == "Дата":
                    mode = v.get(f"{col}_mode", "Действует до")
                    colors = get_date_status_colors(str(val), self.dark, mode)
                    if val and val != "—":
                        dt = parse_date_safely(val)
                        if dt:
                            if mode == "Дата проведения": dt += timedelta(days=365)
                            days_left = (dt - datetime.now()).days + 1
                            if v.get(status_col) != "Устранено":
                                if days_left > 0: item.setText(f"{dt.strftime('%d-%m-%Y')} ({days_left} дн.)")
                                elif days_left == 0: item.setText(f"{dt.strftime('%d-%m-%Y')} (СЕГОДНЯ!)")
                                else: item.setText(f"{dt.strftime('%d-%m-%Y')} (Проср. {abs(days_left)} дн.)")
                        
                if colors:
                    item.setBackground(QColor(colors[0]))
                    item.setForeground(QColor(colors[1]))
                else:
                    item.setForeground(QColor("#cdd6f4" if self.dark else "#1e1e2e"))
                    if st_val == "Просрочено":
                        item.setBackground(QColor("#3d2222" if self.dark else "#fceade"))
                    elif st_val == "Устранено":
                        item.setBackground(QColor("#1c3322" if self.dark else "#ebfaeb"))
                        
                self.viol_table.setItem(r_idx, 1 + c_idx, item)
                
        self.viol_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

    def add_violation(self):
        cols, types = self.get_columns_metadata("viol")
        dlg = DynamicEntityDialog("Регистрация предписания контроля", cols, types, is_violation=True, parent=self)
        if dlg.exec_():
            res = dlg.get_data()
            photo = res.pop("photo", "")
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("INSERT INTO violations (data_json, photo_path) VALUES (?, ?)", (json.dumps(res, ensure_ascii=False), photo))
            conn.commit()
            conn.close()
            self.log_action(f"Выдано предписание для: {res.get('Организация', 'Контрагента')}")
            self.refresh_all()

    def edit_violation(self):
        row = self.viol_table.currentRow()
        if row < 0: return
        item_zero = self.viol_table.item(row, 0)
        if item_zero is None: return
        db_id = item_zero.data(Qt.UserRole)
        
        cols, types = self.get_columns_metadata("viol")
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT data_json, photo_path FROM violations WHERE id=?", (db_id,))
        res = c.fetchone()
        conn.close()
        
        if not res: return
        curr_data = json.loads(res[0])
        curr_data["photo"] = res[1]
        
        dlg = DynamicEntityDialog("Материалы надзорного дела", cols, types, curr_data, is_violation=True, parent=self)
        if dlg.exec_():
            updated = dlg.get_data()
            photo = updated.pop("photo", "")
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("UPDATE violations SET data_json=?, photo_path=? WHERE id=?", (json.dumps(updated, ensure_ascii=False), photo, db_id))
            conn.commit()
            conn.close()
            self.log_action(f"Обновлено предписание №{db_id}")
            self.refresh_all()

    def view_viol_photo(self):
        row = self.viol_table.currentRow()
        if row < 0: return
        item_zero = self.viol_table.item(row, 0)
        if item_zero is None: return
        db_id = item_zero.data(Qt.UserRole)
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT photo_path FROM violations WHERE id=?", (db_id,))
        p = c.fetchone()[0]
        conn.close()
        if p and os.path.exists(p): webbrowser.open(p)
        else: QMessageBox.information(self, "Инфо", "Фотофиксация отсутствует.")

    def archive_resolved_violations(self):
        cols, _ = self.get_columns_metadata("viol")
        status_col = next((c for c in cols if "стат" in c.lower()), "Статус")
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, data_json FROM violations")
        
        to_archive = []
        for db_id, d_json in c.fetchall():
            v = json.loads(d_json)
            if v.get(status_col) == "Устранено":
                to_archive.append(db_id)
                
        if not to_archive:
            QMessageBox.information(self, "Архивация", "Нет исполненных предложений со статусом 'Устранено'.")
            conn.close()
            return
            
        if QMessageBox.question(self, "Архив", f"Переместить {len(to_archive)} закрытых дел в архив?") == QMessageBox.Yes:
            arch_file = os.path.join(DATA_DIR, "ex_violations_archive.json")
            history = []
            if os.path.exists(arch_file):
                try:
                    with open(arch_file, "r", encoding="utf-8") as f: history = json.load(f)
                except: pass
                
            for d_id in to_archive:
                c.execute("SELECT data_json, photo_path FROM violations WHERE id=?", (d_id,))
                res = c.fetchone()
                history.append({"old_id": d_id, "data": json.loads(res[0]), "photo": res[1]})
                c.execute("DELETE FROM violations WHERE id=?", (d_id,))
                
            with open(arch_file, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
                
            conn.commit()
            self.log_action(f"Убрано в архив {len(to_archive)} предписаний.")
            QMessageBox.information(self, "Успех", "Устраненные инциденты заархивированы.")
        conn.close()
        self.refresh_all()

    def delete_violation(self):
        row = self.viol_table.currentRow()
        if row < 0: return
        item_zero = self.viol_table.item(row, 0)
        if item_zero is None: return
        db_id = item_zero.data(Qt.UserRole)
        if QMessageBox.question(self, "Подтверждение", "Полностью уничтожить запись предписания?") == QMessageBox.Yes:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("DELETE FROM violations WHERE id=?", (db_id,))
            conn.commit()
            conn.close()
            self.log_action(f"Исключено предписание ID: {db_id}")
            self.refresh_all()

    def print_violation_report_word(self):
        row = self.viol_table.currentRow()
        if row < 0: return
        item_zero = self.viol_table.item(row, 0)
        if item_zero is None: return
        db_id = item_zero.data(Qt.UserRole)
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT data_json FROM violations WHERE id=?", (db_id,))
        v_data = json.loads(c.fetchone()[0])
        conn.close()
        
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт Бланка", f"Официальное_Предписание_№_{db_id}.doc", "MS Word (*.doc)")
        if not path: return
        
        rows_html = "".join([f"<tr><td style='background:#f9f9f9; border:1px solid #000; padding:10px; font-weight:bold;'>{k}</td><td style='border:1px solid #000; padding:10px;'>{str(val).split(' (')[0]}</td></tr>" for k, val in v_data.items() if not k.endswith("_mode")])
        
        doc_content = f"""
        <html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word' xmlns='http://www.w3.org/TR/REC-html40'>
        <head><meta charset='utf-8'>
        <style>body {{ font-family: 'Times New Roman', serif; line-height: 1.4; }} table {{ width:100%; border-collapse:collapse; }} th,td{{ font-size:14px; }}</style>
        </head>
        <body>
            <div style='text-align:center; border-bottom:2px solid #000; padding-bottom:5px; font-weight:bold; font-size:16px;'>
                ОФИЦИАЛЬНОЕ ПРЕДПИСАНИЕ СЛУЖБЫ ТЕХНИЧЕСКОГО НАДЗОРА И ОХРАНЫ ТРУДА
            </div>
            <h3 align='center'>КАРТОЧКА НАРУШЕНИЯ ТРЕБОВАНИЙ БЕЗОПАСНОСТИ № {db_id}</h3>
            <p align='right'>Сформировано системой: {datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
            <table>{rows_html}</table>
            <br/><br/><br/>
            <table style='width:100%; border:none;'>
                <tr>
                    <td style='border:none;'><b>Инспектор ООТиПБ:</b> ______________</td>
                    <td style='border:none;' align='right'><b>Представитель Контрагента:</b> ______________</td>
                </tr>
            </table>
        </body></html>
        """
        try:
            with open(path, "w", encoding="utf-8") as f: f.write(doc_content)
            self.log_action(f"Сформирован печатный официальный бланк Word по делу №{db_id}")
            QMessageBox.information(self, "Успех", "Бланк предписания успешно сохранен.")
        except Exception as ex: QMessageBox.critical(self, "Ошибка", str(ex))

    # ==============================================================================
    # УПРАВЛЕНИЕ ДИНАМИЧЕСКОЙ СТРУКТУРОЙ И ИМПОРТ/ЭКСПОРТ
    # ==============================================================================
    def add_column_logic(self, category):
        dlg = AddColumnDialog(self)
        if dlg.exec_():
            name, c_type = dlg.get_data()
            if not name: return
            cols, _ = self.get_columns_metadata(category)
            if name in cols:
                QMessageBox.warning(self, "Ошибка", "Параметр с таким именем уже существует.")
                return
                
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT MAX(position) FROM columns_config WHERE category=?", (category,))
            mx = c.fetchone()[0]
            pos = (mx + 1) if mx is not None else 0
            c.execute("INSERT INTO columns_config VALUES (?, ?, ?, ?)", (category, name, c_type, pos))
            conn.commit()
            conn.close()
            
            self.log_action(f"Создан динамический параметр '{name}' ({c_type}) в {category}")
            self.refresh_all()

    def reorder_columns_logic(self, category):
        cols, _ = self.get_columns_metadata(category)
        dlg = ReorderColumnsDialog(cols, self)
        if dlg.exec_():
            new_order = dlg.get_result()
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            for idx, name in enumerate(new_order):
                c.execute("UPDATE columns_config SET position=? WHERE category=? AND name=?", (idx, category, name))
            conn.commit()
            conn.close()
            self.log_action(f"Перестроен порядок отображения столбцов в {category}")
            self.refresh_all()

    def delete_column_logic(self, category):
        cols, _ = self.get_columns_metadata(category)
        if not cols: return
        col, ok = QInputDialog.getItem(self, "Удаление параметра", "Выберите столбец для удаления:", cols, 0, False)
        if ok and col:
            if QMessageBox.question(self, "Предупреждение", f"Уничтожить столбец '{col}' и стереть его значения во всех архивных строках SQLite?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                c.execute("DELETE FROM columns_config WHERE category=? AND name=?", (category, col))
                
                table_target = "employees" if category == "staff" else "violations"
                c.execute(f"SELECT id, data_json LOG FROM {table_target}")
                c.execute(f"SELECT id, data_json FROM {table_target}")
                for r_id, d_json in c.fetchall():
                    item = json.loads(d_json)
                    item.pop(col, None)
                    item.pop(f"{col}_mode", None)
                    c.execute(f"UPDATE {table_target} SET data_json=? WHERE id=?", (json.dumps(item, ensure_ascii=False), r_id))
                    
                conn.commit()
                conn.close()
                self.log_action(f"Удален параметр '{col}' из базы данных {category}.")
                self.refresh_all()

    def import_excel_logic(self, category):
        path, _ = QFileDialog.getOpenFileName(self, "Импорт структуры из Excel", "", "Excel (*.xlsx)")
        if not path: return
        try:
            from openpyxl import load_workbook
            wb = load_workbook(path)
            ws = wb.active
            headers = [str(cell.value).strip() for cell in ws[1]]
            
            cols, _ = self.get_columns_metadata(category)
            table_target = "employees" if category == "staff" else "violations"
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            imported_count = 0
            
            for row in ws.iter_rows(min_row=2, values_only=True):
                if not any(row): continue
                item = {}
                for col_name in cols:
                    if col_name in headers:
                        h_idx = headers.index(col_name)
                        item[col_name] = str(row[h_idx]).strip() if row[h_idx] is not None else ""
                    else:
                        item[col_name] = ""
                c.execute(f"INSERT INTO {table_target} (data_json, photo_path) VALUES (?, '')", (json.dumps(item, ensure_ascii=False),))
                imported_count += 1
                
            conn.commit()
            conn.close()
            self.log_action(f"Успешный импорт {imported_count} строк из Excel в {table_target}")
            QMessageBox.information(self, "Импорт завершен", f"Успешно добавлено строк: {imported_count}")
            self.refresh_all()
        except Exception as ex:
            QMessageBox.critical(self, "Критическая ошибка импорта", f"Не удалось выполнить парсинг Excel:\n{ex}")

    def export_to_csv_logic(self, category, filename_hint):
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить в формате CSV", filename_hint, "CSV Files (*.csv)")
        if not path: return
        cols, _ = self.get_columns_metadata(category)
        table_target = "employees" if category == "staff" else "violations"
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute(f"SELECT data_json FROM {table_target}")
            
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow(cols)
                for row_data in c.fetchall():
                    item = json.loads(row_data[0])
                    writer.writerow([str(item.get(col, "")).split(" (")[0] for col in cols])
            conn.close()
            self.log_action(f"Выполнен экспорт базы {category} в CSV: {os.path.basename(path)}")
            QMessageBox.information(self, "Успех", "Данные выгружены в Excel-совместимый CSV (Разделитель ';', кодировка UTF-8 BOM).")
        except Exception as ex: QMessageBox.critical(self, "Ошибка", str(ex))

    # ===== МОДУЛИ ГЛОБАЛЬНОЙ АНАЛИТИКИ =====
    def global_category_analytics(self):
        cols, _ = self.get_columns_metadata("viol")
        cat_col = next((c for c in cols if "катег" in c.lower()), None)
        fine_col = next((c for c in cols if "штр" in c.lower()), None)
        status_col = next((c for c in cols if "стат" in c.lower()), "Статус")
        
        if not cat_col:
            QMessageBox.warning(self, "Аналитика", "Колонка категории нарушений не обнаружена в структуре базы.")
            return
            
        stats = {}
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT data_json FROM violations")
        for row in c.fetchall():
            v = json.loads(row[0])
            刻 = v.get(cat_col, "Общее") or "Общее"
            st = v.get(status_col, "Активно")
            
            fine_val = 0.0
            if fine_col and v.get(fine_col):
                try:
                    cleaned = "".join(x for x in str(v[fine_col]) if x.isdigit() or x == '.')
                    if cleaned: fine_val = float(cleaned)
                except: pass
                
            stats.setdefault(刻, {"total": 0, "resolved": 0, "fines": 0.0})
            stats[刻]["total"] += 1
            if st == "Устранено": stats[刻]["resolved"] += 1
            stats[刻]["fines"] += fine_val
        conn.close()
            
        dlg = QDialog(self)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setWindowTitle("Аналитический свод рисков и штрафов по категориям")
        dlg.resize(780, 450)
        lay = QVBoxLayout(dlg)
        
        t = QTableWidget()
        t.verticalHeader().setVisible(False)
        t.setColumnCount(5)
        t.setHorizontalHeaderLabels(["Направление / Категория", "Всего нарушений", "Устранено", "Уровень контроля (%)", "Накопленный штраф"])
        t.setRowCount(len(stats))
        
        for r, (cat, info) in enumerate(stats.items()):
            t.setItem(r, 0, QTableWidgetItem(cat))
            t.setItem(r, 1, QTableWidgetItem(str(info["total"])))
            t.setItem(r, 2, QTableWidgetItem(str(info["resolved"])))
            pct = (info["resolved"] / info["total"] * 100) if info["total"] > 0 else 100.0
            t.setItem(r, 3, QTableWidgetItem(f"{pct:.1f}%"))
            t.setItem(r, 4, QTableWidgetItem(f"{info['fines']:,.2f} руб".replace(",", " ")))
            
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        lay.addWidget(t)
        dlg.exec_()

    def export_audit_log_to_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт лога", f"suot_audit_trail_{datetime.now().strftime('%Y%m%d')}.log", "Log Files (*.log)")
        if not path: return
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT timestamp, action FROM audit_log ORDER BY id ASC")
            lines = [f"[{r[0]}] {r[1]}" for r in c.fetchall()]
            conn.close()
            
            with open(path, "w", encoding="utf-8") as f: f.write("\n".join(lines))
            QMessageBox.information(self, "Успех", "Лог успешно выгружен.")
        except Exception as ex: QMessageBox.critical(self, "Ошибка", str(ex))

    def register_custom_violation_template(self):
        title, ok1 = QInputDialog.getText(self, "Добавление шаблона", "Название пресета (например: ⚡ Нарушение заземления):")
        if not ok1 or not title.strip(): return
        desc, ok2 = QInputDialog.getText(self, "Добавление шаблона", "Описание требований безопасности:")
        if not ok2 or not desc.strip(): return
        cat, ok3 = QInputDialog.getText(self, "Добавление шаблона", "Категория (например: Электробезопасность):")
        if not ok3 or not cat.strip(): return
        fine, ok4 = QInputDialog.getText(self, "Добавление шаблона", "Штраф по умолчанию (руб):")
        if not ok4: return
        
        try:
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("INSERT INTO custom_templates (title, desc, cat, fine) VALUES (?, ?, ?, ?)", (title.strip(), desc.strip(), cat.strip(), fine.strip()))
            conn.commit()
            conn.close()
            self.log_action(f"Зарегистрирован новый шаблон: '{title.strip()}'")
            QMessageBox.information(self, "Успех", f"Шаблон '{title.strip()}' внедрен в систему!")
        except Exception as ex: QMessageBox.critical(self, "Ошибка", str(ex))

    def global_contractor_analytics(self):
        cols, _ = self.get_columns_metadata("viol")
        org_col = next((c for c in cols if "орг" in c.lower()), None)
        status_col = next((c for c in cols if "стат" in c.lower()), "Статус")
        fine_col = next((c for c in cols if "штр" in c.lower()), None)

        if not org_col:
            QMessageBox.warning(self, "Ошибка", "Отсутствует целевая колонка организаций.")
            return

        stats = {}
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT data_json FROM violations")
        for row in c.fetchall():
            v = json.loads(row[0])
            org = v.get(org_col, "Не указан") or "Не указан"
            st = v.get(status_col, "Активно")
            fine_val = 0.0
            if fine_col and v.get(fine_col):
                try:
                    cleaned = "".join(x for x in str(v[fine_col]) if x.isdigit() or x == '.')
                    if cleaned: fine_val = float(cleaned)
                except ValueError: pass

            stats.setdefault(org, {"total": 0, "active": 0, "fines": 0.0})
            stats[org]["total"] += 1
            if st in ["Активно", "Просрочено"]: stats[org]["active"] += 1
            stats[org]["fines"] += fine_val
        conn.close()

        dlg = QDialog(self)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setWindowTitle("Сводный аудит подрядчиков")
        grid = QVBoxLayout(dlg)
        t = QTableWidget()
        t.verticalHeader().setVisible(False)
        t.setColumnCount(4)
        t.setHorizontalHeaderLabels(["Подрядчик", "Всего нарушений", "Активных предписаний", "Сумма штрафов"])
        t.setRowCount(len(stats))
        for r, (org, info) in enumerate(stats.items()):
            t.setItem(r, 0, QTableWidgetItem(org))
            t.setItem(r, 1, QTableWidgetItem(str(info["total"])))
            t.setItem(r, 2, QTableWidgetItem(str(info["active"])))
            t.setItem(r, 3, QTableWidgetItem(f"{info['fines']:,.2f} р".replace(",", " ")))
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        grid.addWidget(t)
        dlg.exec_()

    def global_restore_from_backup(self):
        files = [f for f in os.listdir(BACKUP_DIR) if f.endswith(".db")]
        if not files:
            QMessageBox.information(self, "Архиватор", "Точки восстановления не найдены.")
            return
        files.sort(reverse=True)
        chosen, ok = QInputDialog.getItem(self, "Откат системы", "Выберите точку отката:", files, 0, False)
        if ok and chosen:
            if QMessageBox.question(self, "Внимание", "Откатить состояние всей системы?") == QMessageBox.Yes:
                make_db_backup("before_restore")
                try:
                    shutil.copy(os.path.join(BACKUP_DIR, chosen), DB_FILE)
                    self.log_action(f"Произведен глобальный откат системы к базе: {chosen}")
                    self.refresh_all()
                    QMessageBox.information(self, "Успех", "База данных успешно восстановлена!")
                except Exception as ex: QMessageBox.critical(self, "Ошибка", str(ex))

    def global_cross_search(self):
        query, ok = QInputDialog.getText(self, "Конвейер поиска", "Введите поисковый запрос:")
        if not ok or not query.strip(): return
        q = query.strip().lower()
        res = []
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        c.execute("SELECT id, data_json FROM employees")
        for db_id, d_json in c.fetchall():
            e = json.loads(d_json)
            for k, v in e.items():
                if q in str(v).lower():
                    res.append(f"👤 Персонал (ID: {db_id}) | {list(e.values())[0]} -> [{k}]: {v}")
                    break
                    
        c.execute("SELECT id, data_json FROM violations")
        for db_id, d_json in c.fetchall():
            v = json.loads(d_json)
            for k, val in v.items():
                if q in str(val).lower():
                    res.append(f"🚨 Предписание №{db_id} | Поле [{k}]: {val}")
                    break
        conn.close()

        dlg = QDialog(self)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setWindowTitle("Результаты сквозного сканирования SQLite")
        dlg.resize(750, 450)
        lay = QVBoxLayout(dlg)
        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setText(f"Всего совпадений найдено: {len(res)}\n\n" + "\n\n".join(res) if res else "Совпадений не обнаружено.")
        lay.addWidget(txt)
        dlg.exec_()

    def generate_global_report(self):
        path = os.path.abspath(os.path.join(DATA_DIR, "global_report.html"))
        cols, _ = self.get_columns_metadata("viol")
        status_col = next((c for c in cols if "стат" in c.lower()), "Статус")
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT data_json FROM violations")
        
        active_items = []
        for row in c.fetchall():
            v = json.loads(row[0])
            if v.get(status_col) in ["Активно", "Просрочено"]:
                active_items.append(v)
        conn.close()
        
        li_html = "".join([f"<li><b>{v.get('Организация', 'Контрагент')}:</b> {v.get('Суть нарушения', 'Замечание по ТБ')}</li>" for v in active_items])
        
        html = f"""
        <html><head><meta charset='utf-8'><style>body{{font-family:Arial; margin:40px; background:#fafafa;}} .c{{background:#fff; padding:30px; border-radius:8px; box-shadow:0 2px 5px rgba(0,0,0,0.1);}}</style></head>
        <body><div class="c">
            <h2>Генеральный аналитический свод СУОТ</h2>
            <p>Сформировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
            <h3>⚠️ Список нерешенных нарушений подрядных организаций ({len(active_items)}):</h3>
            <ul>{li_html if li_html else "<li>Все предписания устранены. Риски отсутствуют.</li>"}</ul>
            <hr><button onclick="window.print()">Печать свода</button>
        </div></body></html>
        """
        with open(path, "w", encoding="utf-8") as f: f.write(html)
        webbrowser.open(f"file:///{path}")

    def update_org_filters_data(self):
        staff_cols, _ = self.get_columns_metadata("staff")
        org_col_staff = next((c for c in staff_cols if "орг" in c.lower() or "комп" in c.lower()), None)
        
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        staff_orgs = set()
        if org_col_staff:
            c.execute("SELECT data_json FROM employees")
            for row in c.fetchall():
                e = json.loads(row[0])
                if e.get(org_col_staff): staff_orgs.add(str(e[org_col_staff]).strip())
                
        curr_staff = self.staff_org_filter.currentText()
        self.staff_org_filter.blockSignals(True)
        self.staff_org_filter.clear()
        self.staff_org_filter.addItem("Все организации")
        for o in sorted(list(staff_orgs)): 
            if o: self.staff_org_filter.addItem(o)
        if curr_staff and self.staff_org_filter.findText(curr_staff) >= 0:
            self.staff_org_filter.setCurrentText(curr_staff)
        self.staff_org_filter.blockSignals(False)

        viol_cols, _ = self.get_columns_metadata("viol")
        org_col_viol = next((c for c in viol_cols if "орг" in c.lower()), None)
        viol_orgs = set()
        if org_col_viol:
            c.execute("SELECT data_json FROM violations")
            for row in c.fetchall():
                v = json.loads(row[0])
                if v.get(org_col_viol): viol_orgs.add(str(v[org_col_viol]).strip())
                
        curr_viol = self.viol_org_filter.currentText()
        self.viol_org_filter.blockSignals(True)
        self.viol_org_filter.clear()
        self.viol_org_filter.addItem("Все организации")
        for o in sorted(list(viol_orgs)): 
            if o: self.viol_org_filter.addItem(o)
        if curr_viol and self.viol_org_filter.findText(curr_viol) >= 0:
            self.viol_org_filter.setCurrentText(curr_viol)
        self.viol_org_filter.blockSignals(False)
        conn.close()

    def export_staff_excel(self):
        try:
            from openpyxl import Workbook
            path, _ = QFileDialog.getSaveFileName(self, "Сохранить", "Реестр_Персонала.xlsx", "Excel (*.xlsx)")
            if not path: return
            cols, _ = self.get_columns_metadata("staff")
            
            wb = Workbook()
            ws = wb.active
            ws.append(cols)
            
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT data_json FROM employees")
            for row in c.fetchall():
                e = json.loads(row[0])
                ws.append([e.get(c_name, "") for c_name in cols])
            conn.close()
            
            wb.save(path)
            QMessageBox.information(self, "Успех", "Выгрузка в Excel завершена успешно.")
        except Exception as ex: QMessageBox.critical(self, "Ошибка", str(ex))

    def toggle_theme(self):
        self.dark = not self.dark
        self.apply_theme()
        self.refresh_all()

    def apply_theme(self):
        if self.dark:
            self.setStyleSheet("""
                QWidget { background-color: #1e1e2e; color: #cdd6f4; font-size: 13px; }
                QDialog { background-color: #1e1e2e; color: #cdd6f4; }
                QPushButton { background-color: #313244; color: #cdd6f4; border: 1px solid #45475a; padding: 7px; border-radius: 5px; }
                QPushButton:hover { background-color: #45475a; }
                QLineEdit, QComboBox, QTextEdit, QListWidget { background-color: #313244; color: #cdd6f4; border: 1px solid #45475a; padding: 5px; border-radius: 5px; }
                QComboBox QAbstractItemView { background-color: #313244; color: #cdd6f4; selection-background-color: #45475a; }
                QTableWidget { background-color: #181825; color: #cdd6f4; gridline-color: #45475a; border: 1px solid #45475a; }
                QHeaderView::section { background-color: #313244; color: #cdd6f4; padding: 6px; border: 1px solid #45475a; font-weight: bold; }
                QProgressBar { border: 1px solid #45475a; border-radius: 5px; text-align: center; font-weight: bold; height: 24px; background: #313244; color: #ffffff; }
                QProgressBar::chunk { background-color: #a6e3a1; }
                QFrame#CardFrame { background-color: #252538; border: 1px solid #45475a; border-radius: 8px; padding: 10px; }
                QTabWidget::pane { border: 1px solid #45475a; background-color: #1e1e2e; }
                QTabWidget::tab-bar { alignment: left; }
                QTabBar::tab { background-color: #313244; color: #cdd6f4; padding: 8px 12px; border: 1px solid #45475a; border-top-left-radius: 4px; border-top-right-radius: 4px; }
                QTabBar::tab:selected { background-color: #1e1e2e; font-weight: bold; }
                QRadioButton { color: #cdd6f4; }
                QMenu { background-color: #313244; color: #cdd6f4; border: 1px solid #45475a; }
                QMenu::item:selected { background-color: #45475a; }
            """)
            self.p1.setStyleSheet("QProgressBar { color: #ffffff; } QProgressBar::chunk { background-color: #254b32; }")
            self.p2.setStyleSheet("QProgressBar { color: #ffffff; } QProgressBar::chunk { background-color: #254b32; }")
        else:
            self.setStyleSheet("""
                QWidget { background-color: #f5f5f7; color: #1e1e2e; font-size: 13px; }
                QDialog { background-color: #f5f5f7; color: #1e1e2e; }
                QPushButton { background-color: #ffffff; color: #1e1e2e; border: 1px solid #ddd; padding: 7px; border-radius: 5px; }
                QPushButton:hover { background-color: #e8e8ed; }
                QLineEdit, QComboBox, QTextEdit, QListWidget { background-color: #ffffff; color: #1e1e2e; border: 1px solid #ddd; padding: 5px; border-radius: 5px; }
                QComboBox QAbstractItemView { background-color: #ffffff; color: #1e1e2e; selection-background-color: #ececf0; }
                QTableWidget { background-color: #ffffff; color: #1e1e2e; gridline-color: #e0e0e0; border: 1px solid #ddd; }
                QHeaderView::section { background-color: #ececf0; color: #1e1e2e; padding: 6px; border: 1px solid #ddd; font-weight: bold; }
                QProgressBar { border: 1px solid #ddd; border-radius: 5px; text-align: center; font-weight: bold; height: 24px; background: #eee; color: #000000; }
                QProgressBar::chunk { background-color: #2ecc71; }
                QFrame#CardFrame { background-color: #ffffff; border: 1px solid #ddd; border-radius: 8px; padding: 10px; }
                QTabWidget::pane { border: 1px solid #ddd; background-color: #f5f5f7; }
                QTabBar::tab { background-color: #e8e8ed; color: #1e1e2e; padding: 8px 12px; border: 1px solid #ddd; border-top-left-radius: 4px; border-top-right-radius: 4px; }
                QTabBar::tab:selected { background-color: #f5f5f7; font-weight: bold; }
                QRadioButton { color: #1e1e2e; }
                QMenu { background-color: #ffffff; color: #1e1e2e; border: 1px solid #ddd; }
                QMenu::item:selected { background-color: #ececf0; }
            """)

    def open_settings(self):
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key='app_name'")
        res = c.fetchone()
        curr_name = res[0] if res else ""
        
        name, ok = QInputDialog.getText(self, "Система", "Имя ПО в шапке:", text=curr_name)
        if ok and name.strip():
            c.execute("INSERT OR REPLACE INTO settings VALUES ('app_name', ?)", (name.strip(),))
            conn.commit()
            self.setWindowTitle(name.strip())
        conn.close()

    def open_knowledge(self):
        dlg = QDialog(self)
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        dlg.setWindowTitle("Нормативная база СУОТ")
        dlg.resize(600, 420)
        lay = QVBoxLayout(dlg)
        t = QTextEdit()
        if os.path.exists(KNOWLEDGE_FILE):
            try:
                with open(KNOWLEDGE_FILE, "r", encoding="utf-8") as f: t.setText(f.read())
            except Exception: pass
        lay.addWidget(t)
        b = QPushButton("Сохранить изменения")
        b.clicked.connect(lambda: [open(KNOWLEDGE_FILE, "w", encoding="utf-8").write(t.toPlainText()), dlg.accept()])
        lay.addWidget(b)
        dlg.exec_()

    def refresh_all(self):
        self.update_org_filters_data()
        self.update_dashboard()
        self.refresh_staff_table()
        self.refresh_viol_table()

    def closeEvent(self, event):
        try:
            conn = sqlite3.connect(DB_FILE)
            conn.execute("VACUUM")
            conn.close()
        except Exception:
            pass
        make_db_backup("exit")
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())