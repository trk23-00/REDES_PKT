from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap, QFont
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTabWidget, QFileDialog, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QSpinBox, QComboBox, QCheckBox,
    QProgressBar, QScrollArea, QAbstractItemView,
)
from UI.theme import QSS
from core.workflow import TopologySession, parse_ips


def label(text, name=None):
    widget = QLabel(text)
    widget.setWordWrap(True)
    if name:
        widget.setObjectName(name)
    return widget


def button(text, action, primary=False):
    widget = QPushButton(text)
    if primary:
        widget.setObjectName('Primary')
    widget.clicked.connect(action)
    return widget


def table(headers):
    widget = QTableWidget(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    widget.verticalHeader().hide()
    widget.verticalHeader().setDefaultSectionSize(40)
    widget.setAlternatingRowColors(True)
    widget.setMinimumHeight(150)
    return widget


def item(value, editable=True):
    result = QTableWidgetItem(str(value))
    if not editable:
        result.setFlags(result.flags() & ~Qt.ItemIsEditable)
    return result


def card(title, description):
    frame = QFrame()
    frame.setObjectName('Card')
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(24, 20, 24, 20)
    layout.setSpacing(12)
    heading = label(title)
    font = heading.font()
    font.setPointSize(15)
    font.setWeight(QFont.DemiBold)
    heading.setFont(font)
    layout.addWidget(heading)
    layout.addWidget(label(description, 'Hint'))
    return frame, layout


class AnalysisWorker(QThread):
    ready = Signal(object)
    failed = Signal(str)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path

    def run(self):
        try:
            from api_gemini.procesador import procesar_topologia_red
            with TemporaryDirectory(prefix='autopkt-') as folder:
                procesar_topologia_red(self.path, folder)
                session = TopologySession()
                session.load(Path(folder) / 'conexiones.csv', Path(folder) / 'pos.csv')
            self.ready.emit(session)
        except Exception as error:
            self.failed.emit(str(error))


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('AutoPKT · Topologías desde imágenes')
        self.setStyleSheet(QSS)
        self.setMinimumSize(1000, 720)
        self.session = TopologySession()
        self.image_path = None
        self.worker = None
        self._updating = False
        bg = QWidget()
        bg.setObjectName('Background')
        self.setCentralWidget(bg)
        root = QHBoxLayout(bg)
        root.setContentsMargins(18, 18, 18, 12)
        root.setSpacing(24)
        sidebar = QFrame()
        sidebar.setObjectName('Sidebar')
        sidebar.setFixedWidth(206)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(22, 30, 22, 26)
        side.addWidget(label('AUTO\nP K T', 'Brand'))
        side.addWidget(label('TOPOLOGY STUDIO'))
        side.addSpacing(48)
        side.addWidget(label('01   IMAGEN'))
        side.addWidget(label('Reconoce tu topología'))
        side.addSpacing(25)
        side.addWidget(label('02   CONFIGURACIÓN'))
        side.addWidget(label('Opcional · IP y protocolos'))
        side.addSpacing(25)
        side.addWidget(label('03   ARCHIVO'))
        side.addWidget(label('Genera y exporta'))
        side.addStretch()
        side.addWidget(label('DE LA IMAGEN\nA TU RED.'))
        side.addSpacing(15)
        self.side_state = label('Esperando una imagen')
        side.addWidget(self.side_state)
        root.addWidget(sidebar)
        content = QVBoxLayout()
        content.setSpacing(14)
        content.addWidget(label('D I S E Ñ A  ·  C O N F I G U R A  ·  C R E A', 'Kicker'))
        content.addWidget(label('T U   P R Ó X I M A   R E D', 'Title'))
        self.tabs = QTabWidget()
        self.tabs.addTab(self.image_page(), '01  Cargar imagen')
        self.tabs.addTab(self.config_page(), '02  Configurar · opcional')
        self.tabs.addTab(self.export_page(), '03  Crear archivo')
        self.tabs.setTabEnabled(1, False)
        self.tabs.setTabEnabled(2, False)
        content.addWidget(self.tabs, 1)
        root.addLayout(content, 1)
        self.statusBar().showMessage('Carga una imagen para empezar.')

    def image_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 18, 0, 0)
        frame, body = card('Todo empieza con una imagen', 'Sube una captura o un diagrama de red. Detectaremos los dispositivos, enlaces y posiciones.')
        self.preview = label('PNG / JPG / WEBP\n\nSelecciona la imagen de tu topología', 'Preview')
        self.preview.setMinimumHeight(240)
        self.preview.setAlignment(Qt.AlignCenter)
        body.addWidget(self.preview, 1)
        self.image_name = label('Ninguna imagen seleccionada', 'Hint')
        body.addWidget(self.image_name)
        row = QHBoxLayout()
        self.pick_button = button('Seleccionar imagen', self.pick_image)
        self.analyze_button = button('Analizar imagen', self.analyze, True)
        self.analyze_button.setEnabled(False)
        row.addWidget(self.pick_button)
        row.addWidget(self.analyze_button)
        body.addLayout(row)
        body.addWidget(label('Al analizar, la imagen se envía a Gemini para reconocer la red.', 'Hint'))
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        body.addWidget(self.progress)
        self.image_status = label('La configuración es opcional: puedes generar el archivo después del análisis.', 'Hint')
        body.addWidget(self.image_status)
        self.detected = table(['Dispositivo', 'Tipo', 'Enlaces'])
        self.detected.hide()
        self.detected.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.detected.setMaximumHeight(170)
        body.addWidget(self.detected)
        next_row = QHBoxLayout()
        self.go_config = button('Configurar red', lambda: self.tabs.setCurrentIndex(1))
        self.go_export = button('Continuar sin configurar →', self.skip_config, True)
        self.go_config.hide()
        self.go_export.hide()
        next_row.addWidget(self.go_config)
        next_row.addWidget(self.go_export)
        body.addLayout(next_row)
        layout.addWidget(frame, 1)
        return page

    def config_page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 18, 0, 0)
        layout.setSpacing(16)
        frame, body = card('Segmentos por rama', 'Elige la cantidad por rama/router. Deja el segmento vacío para generarlo automáticamente o escribe una red CIDR. Cada segmento corresponde a una VLAN.')
        self.branch_table = table(['Rama / router', 'Equipos', 'Segmentos'])
        self.branch_table.setMaximumHeight(190)
        body.addWidget(self.branch_table)
        self.segment_table = table(['Rama', 'VLAN', 'Segmento (vacío = automático)'])
        self.segment_table.itemChanged.connect(self.invalidate)
        body.addWidget(self.segment_table)
        body.addWidget(label('Se reserva la primera IP como puerta de enlace. Los switches usan VLAN 1; los equipos restantes se reparten entre los segmentos.', 'Hint'))
        layout.addWidget(frame)
        frame, body = card('Direcciones de dispositivos', 'Combina la asignación automática con IP manuales o importadas. CSV: dispositivo,ip,máscara. Para interfaces de router: R1@GigabitEthernet0/0.')
        row = QHBoxLayout()
        row.addWidget(button('Importar IP desde CSV', self.import_ips))
        row.addWidget(button('Restablecer IP automáticas', self.clear_ips))
        body.addLayout(row)
        self.ip_table = table(['Dispositivo / interfaz', 'IP manual', 'Máscara o prefijo'])
        self.ip_table.itemChanged.connect(self.invalidate)
        body.addWidget(self.ip_table)
        layout.addWidget(frame)
        frame, body = card('Protocolos por router', 'Elige Sin protocolo, OSPF (área 0), RIP v2 o EIGRP (AS 100). Cada router conserva su propia selección.')
        self.router_table = table(['Router', 'Protocolo'])
        self.router_table.setMaximumHeight(180)
        body.addWidget(self.router_table)
        body.addWidget(label('Los protocolos distintos no intercambian rutas entre sí automáticamente.', 'Hint'))
        layout.addWidget(frame)
        self.config_status = label('Los cambios se aplican solo después de validar.', 'Hint')
        layout.addWidget(self.config_status)
        row = QHBoxLayout()
        row.addWidget(button('Generar IP y validar configuración', self.apply_config, True))
        row.addWidget(button('Continuar sin configurar →', self.skip_config))
        layout.addLayout(row)
        self.result_table = table(['Dispositivo / interfaz', 'IP', 'Máscara'])
        self.result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.result_table.hide()
        layout.addWidget(self.result_table)
        self.finish_config = button('Crear archivo con esta configuración →', lambda: self.tabs.setCurrentIndex(2), True)
        self.finish_config.hide()
        layout.addWidget(self.finish_config)
        scroll.setWidget(page)
        return scroll

    def export_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 18, 0, 0)
        frame, body = card('Tu topología, lista para salir', 'Genera el archivo para Packet Tracer o exporta la configuración como documentos Markdown.')
        self.summary = label('Analiza una imagen para ver el resumen.', 'Title')
        body.addWidget(self.summary)
        self.include_config = QCheckBox('Incluir la configuración validada')
        self.include_config.setEnabled(False)
        self.include_config.toggled.connect(self.update_summary)
        body.addWidget(self.include_config)
        self.export_mode = label('Solo dispositivos, enlaces y posiciones.', 'Hint')
        body.addWidget(self.export_mode)
        body.addSpacing(22)
        body.addWidget(button('Crear archivo .pkt', self.generate, True))
        body.addWidget(label('Elige dónde guardar la topología para Cisco Packet Tracer.', 'Hint'))
        body.addSpacing(18)
        md = button('Exportar configuración .md', self.export_md)
        md.setObjectName('Coral')
        body.addWidget(md)
        body.addWidget(label('cisco.md · Comandos de switches y routers\npcs.md · Listado de equipos, IP, máscara y puerta de enlace', 'Hint'))
        self.export_result = label('', 'Hint')
        body.addWidget(self.export_result)
        layout.addWidget(frame)
        layout.addStretch()
        return page

    def pick_image(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Seleccionar topología', '', 'Imágenes (*.png *.jpg *.jpeg *.webp)')
        if not path:
            return
        pixmap = QPixmap(path)
        if pixmap.isNull():
            self.error('No se pudo abrir la imagen. Selecciona un archivo válido.')
            return
        self.image_path = path
        self.session = TopologySession()
        self.preview.setMinimumHeight(240)
        self.preview.setPixmap(pixmap.scaled(650, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.image_name.setText(Path(path).name)
        self.analyze_button.setEnabled(True)
        self.tabs.setTabEnabled(1, False)
        self.tabs.setTabEnabled(2, False)
        self.detected.hide()
        self.go_config.hide()
        self.go_export.hide()
        self.include_config.setChecked(False)
        self.include_config.setEnabled(False)
        self.image_status.setText('Imagen seleccionada. Analízala para detectar tu topología.')
        self.side_state.setText('Imagen lista para analizar')

    def analyze(self):
        if not self.image_path or (self.worker and self.worker.isRunning()):
            return
        self.pick_button.setEnabled(False)
        self.analyze_button.setEnabled(False)
        self.tabs.setTabEnabled(1, False)
        self.tabs.setTabEnabled(2, False)
        self.go_config.setEnabled(False)
        self.go_export.setEnabled(False)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.image_status.setText('Analizando la imagen… Esto puede tardar un momento.')
        self.worker = AnalysisWorker(self.image_path, self)
        self.worker.ready.connect(self.loaded)
        self.worker.failed.connect(self.analysis_failed)
        self.worker.finished.connect(self.analysis_finished)
        self.worker.start()

    def analysis_failed(self, message):
        self.image_status.setText('No se pudo analizar la imagen. Puedes volver a intentarlo.')
        self.error(message)

    def analysis_finished(self):
        self.progress.hide()
        self.pick_button.setEnabled(True)
        self.analyze_button.setEnabled(True)
        ready = self.session.base is not None
        self.tabs.setTabEnabled(1, ready)
        self.tabs.setTabEnabled(2, ready)
        self.go_config.setEnabled(ready)
        self.go_export.setEnabled(ready)

    def loaded(self, session):
        self.session = session
        self._updating = True
        self.preview.setMinimumHeight(150)
        core = session.base
        self.detected.setRowCount(len(core.dic_device_objeto))
        kinds = {'r': 'Router', 'sw': 'Switch', 'pc': 'PC', 'srv': 'Servidor'}
        for row, (name, device) in enumerate(core.dic_device_objeto.items()):
            for column, value in enumerate((name, kinds[device.tipo], len(device.interfa_device))):
                self.detected.setItem(row, column, item(value, False))
        self.detected.show()
        self.go_config.show()
        self.go_export.show()
        self.branch_table.setRowCount(len(session.branches))
        for row, branch in enumerate(session.branches):
            self.branch_table.setItem(row, 0, item(branch.key, False))
            self.branch_table.setItem(row, 1, item(len(branch.switches) + len(branch.hosts), False))
            count = QSpinBox()
            count.setRange(1, 128 if branch.switches else 1)
            count.valueChanged.connect(self.rebuild_segments)
            self.branch_table.setCellWidget(row, 2, count)
        self.segment_table.setRowCount(0)
        self.rebuild_segments()
        names = []
        for name, device in core.dic_device_objeto.items():
            names.extend([f'{name}@{port}' for port in device.interfa_device] if device.tipo == 'r' else [name])
        self.ip_table.setRowCount(len(names))
        for row, name in enumerate(names):
            self.ip_table.setItem(row, 0, item(name, False))
            self.ip_table.setItem(row, 1, item(''))
            self.ip_table.setItem(row, 2, item(''))
        self.router_table.setRowCount(len(core.lista_routers))
        for row, name in enumerate(core.lista_routers):
            self.router_table.setItem(row, 0, item(name, False))
            combo = QComboBox()
            combo.addItems(['Sin protocolo', 'OSPF', 'RIP', 'EIGRP'])
            combo.currentTextChanged.connect(self.invalidate)
            self.router_table.setCellWidget(row, 1, combo)
        self._updating = False
        self.invalidate()
        self.tabs.setTabEnabled(1, True)
        self.tabs.setTabEnabled(2, True)
        self.image_status.setText(f'{len(names)} dispositivos/interfaces detectados. Revisa la lista y elige cómo continuar.')
        self.side_state.setText('Topología reconocida')
        self.update_summary()

    def rebuild_segments(self, *_):
        previous = {(self.segment_table.item(row, 0).text(), self.segment_table.item(row, 1).text()): self.segment_table.item(row, 2).text() for row in range(self.segment_table.rowCount())}
        updating = self._updating
        self._updating = True
        self.segment_table.setRowCount(0)
        for row, branch in enumerate(self.session.branches):
            count = self.branch_table.cellWidget(row, 2).value()
            for vlan in range(1, count + 1):
                index = self.segment_table.rowCount()
                self.segment_table.insertRow(index)
                for col, value in enumerate((branch.key, str(vlan), previous.get((branch.key, str(vlan)), ''))):
                    self.segment_table.setItem(index, col, item(value, col == 2))
        self._updating = updating
        self.invalidate()

    def invalidate(self, *_):
        if self._updating:
            return
        self.session.configured = None
        self.include_config.setChecked(False)
        self.include_config.setEnabled(False)
        self.config_status.setText('Configuración pendiente de validar. Los campos vacíos se completan automáticamente.')
        self.result_table.hide()
        self.finish_config.hide()
        self.export_result.setText('')

    def clear_ips(self):
        for row in range(self.ip_table.rowCount()):
            self.ip_table.item(row, 1).setText('')
            self.ip_table.item(row, 2).setText('')

    def import_ips(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Importar IP', '', 'CSV (*.csv)')
        if not path:
            return
        try:
            values = parse_ips(path)
            indices = {self.ip_table.item(row, 0).text(): row for row in range(self.ip_table.rowCount())}
            unknown = set(values) - set(indices)
            if unknown:
                raise ValueError('Dispositivos desconocidos: ' + ', '.join(sorted(unknown)))
            for name, (ip, mask) in values.items():
                row = indices[name]
                self.ip_table.item(row, 1).setText(ip)
                self.ip_table.item(row, 2).setText(mask)
            self.config_status.setText('IP importadas. Revisa los valores y valida el conjunto antes de generar.')
        except Exception as error:
            self.error(str(error))

    def apply_config(self):
        try:
            plans, overrides, protocols = {}, {}, {}
            for row in range(self.segment_table.rowCount()):
                key = self.segment_table.item(row, 0).text()
                plans.setdefault(key, []).append(self.segment_table.item(row, 2).text())
            for row in range(self.ip_table.rowCount()):
                name, ip, mask = [self.ip_table.item(row, col).text().strip() for col in range(3)]
                if bool(ip) != bool(mask):
                    raise ValueError(f'{name}: introduce IP y máscara juntas o deja ambas vacías.')
                if ip:
                    overrides[name] = (ip, mask)
            for row in range(self.router_table.rowCount()):
                protocols[self.router_table.item(row, 0).text()] = self.router_table.cellWidget(row, 1).currentText()
            resolved = self.session.configure(plans, overrides, protocols)
            self._updating = True
            for row in range(self.segment_table.rowCount()):
                key = self.segment_table.item(row, 0).text()
                vlan = int(self.segment_table.item(row, 1).text())
                self.segment_table.item(row, 2).setText(resolved[key][vlan - 1])
            self._updating = False
            self.result_table.setRowCount(0)
            for name, device in self.session.configured.dic_device_objeto.items():
                entries = [(name, device.ip, device.mask)] if device.tipo != 'r' else [(f'{name}@{port}' + (f'.{vlan}' if index else ''), ip, mask) for port, values in device.interfa_vlan.items() for index, (vlan, ip, mask) in enumerate(values)]
                for entry in entries:
                    row = self.result_table.rowCount()
                    self.result_table.insertRow(row)
                    for column, value in enumerate(entry):
                        self.result_table.setItem(row, column, item(value or '—', False))
            self.result_table.show()
            self.finish_config.show()
            self.include_config.setEnabled(True)
            self.include_config.setChecked(True)
            self.config_status.setText('Configuración válida. Revisa las IP generadas en la tabla inferior.')
            self.statusBar().showMessage('Segmentos e IP validados. Configuración lista para generar.')
        except Exception as error:
            self._updating = False
            self.invalidate()
            self.error(str(error))

    def skip_config(self):
        self.include_config.setChecked(False)
        self.tabs.setCurrentIndex(2)

    def update_summary(self):
        if not self.session.base:
            return
        core = self.session.base
        self.summary.setText(f'{len(core.dic_device_objeto)} dispositivos   /   {len(core.dic_edges)} enlaces')
        self.export_mode.setText('Con IP, VLAN y protocolos validados.' if self.include_config.isChecked() else 'Sin configurar: dispositivos, enlaces y posiciones. Sin asignación de IP ni protocolos.')

    def generate(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Guardar topología', 'topologia.pkt', 'Packet Tracer (*.pkt)')
        if not path:
            return
        if not path.lower().endswith('.pkt'):
            path += '.pkt'
        try:
            self.session.generator(self.include_config.isChecked()).generar(path)
            self.export_result.setText(f'Archivo creado:\n{path}')
            self.statusBar().showMessage('Topología guardada correctamente.')
        except Exception as error:
            self.error(str(error))

    def export_md(self):
        folder = QFileDialog.getExistingDirectory(self, 'Guardar configuración Markdown')
        if not folder:
            return
        existing = [name for name in ('cisco.md', 'pcs.md') if (Path(folder) / name).exists()]
        if existing and QMessageBox.question(self, 'Reemplazar archivos', 'Ya existen ' + ', '.join(existing) + '. ¿Reemplazarlos?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            paths = self.session.export_markdown(folder, self.include_config.isChecked())
            self.export_result.setText('Archivos exportados:\n' + '\n'.join(map(str, paths)))
            self.statusBar().showMessage('Configuración exportada correctamente.')
        except Exception as error:
            self.error(str(error))

    def error(self, message):
        self.statusBar().showMessage(message)
        QMessageBox.warning(self, 'Revisa los datos', message)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.statusBar().showMessage('El análisis está en curso. Espera a que termine antes de cerrar.')
            event.ignore()
        else:
            event.accept()
