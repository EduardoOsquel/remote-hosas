"""Controller aliases, live indicators and deliberate input identification."""
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QGridLayout, QLabel,
    QProgressBar, QScrollArea, QLineEdit)
from ui_theme import make_button


class JoystickTools:
    def setup_tools(self, form, root, buttons_row, settings):
        self.alias_settings = settings
        self.session_aliases = {}
        self.identifying = []
        self.identify_ticks = 0
        self.identify_timer = QTimer(self)
        self.identify_timer.timeout.connect(self.identify_tick)
        self.alias_edit = QLineEdit()
        self.alias_edit.setMaxLength(60)
        self.alias_edit.setPlaceholderText("Left stick, Right stick, Throttle...")
        self.alias_edit.editingFinished.connect(self.save_alias)
        form.addRow("Alias:", self.alias_edit)
        self.alias_note = QLabel()
        self.alias_note.setWordWrap(True)
        form.addRow(self.alias_note)
        self.identify_btn = make_button("Identify controller", "gaming")
        self.identify_btn.clicked.connect(self.identify_controller)
        buttons_row.addWidget(self.identify_btn)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.indicator_panel = QWidget()
        self.indicator_layout = QVBoxLayout(self.indicator_panel)
        scroll.setWidget(self.indicator_panel)
        root.insertWidget(root.indexOf(self.live_state) - 1, scroll, 3)
        self.live_state.setMaximumHeight(90)
        self.log.setMaximumHeight(120)
        self.axis_bars, self.button_lights, self.hat_labels = [], [], []
        self.visual_shape = None

    def alias_key(self, info):
        return "joysticks/aliases/" + info["guid"]

    def prepare_aliases(self):
        infos = [self.device_combo.itemData(i) for i in range(self.device_combo.count())]
        infos = [info for info in infos if info]
        for i, info in enumerate(infos):
            info["ambiguous"] = sum(other["guid"] == info["guid"] for other in infos) > 1
            self.device_combo.setItemData(i, info)
            self.update_alias_label(i)
        self.identify_btn.setEnabled(bool(infos))
        self.show_alias()

    def get_alias(self, info):
        if info.get("ambiguous"):
            return self.session_aliases.get(info["instance"], "")
        return str(self.alias_settings.value(self.alias_key(info), ""))

    def update_alias_label(self, index):
        info = self.device_combo.itemData(index)
        alias = self.get_alias(info)
        label = f'{info["index"]} - {info["name"]}'
        self.device_combo.setItemText(index, f"{alias} | {label}" if alias else label)

    def show_alias(self):
        if not hasattr(self, "alias_edit"):
            return
        info = self.device_combo.currentData()
        self.alias_edit.setEnabled(bool(info))
        self.alias_edit.setText(self.get_alias(info) if info else "")
        self.alias_note.setText("Identical models detected: aliases apply only to this connection session."
            if info and info.get("ambiguous") else "Alias saved for this hardware GUID; does not rename the device in games.")
        self.clear_indicators()

    def save_alias(self):
        info = self.device_combo.currentData()
        if not info:
            return
        alias = self.alias_edit.text().strip()
        if info.get("ambiguous"):
            self.session_aliases[info["instance"]] = alias
        else:
            self.alias_settings.setValue(self.alias_key(info), alias)
        self.update_alias_label(self.device_combo.currentIndex())

    def clear_indicators(self):
        if not hasattr(self, "indicator_layout"):
            return
        while self.indicator_layout.count():
            item = self.indicator_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.visual_shape = None
        self.axis_bars, self.button_lights, self.hat_labels = [], [], []

    def render_indicators(self, axes, buttons, hats):
        shape = (len(axes), len(buttons), len(hats))
        if shape != self.visual_shape:
            self.clear_indicators()
            self.visual_shape = shape
            for i in range(len(axes)):
                bar = QProgressBar()
                bar.setRange(0, 2000)
                self.indicator_layout.addWidget(bar)
                self.axis_bars.append(bar)
            panel = QWidget()
            grid = QGridLayout(panel)
            for i in range(len(buttons)):
                light = QLabel()
                light.setAlignment(Qt.AlignmentFlag.AlignCenter)
                grid.addWidget(light, i // 8, i % 8)
                self.button_lights.append(light)
            self.indicator_layout.addWidget(panel)
            for i in range(len(hats)):
                label = QLabel()
                self.indicator_layout.addWidget(label)
                self.hat_labels.append(label)
        for i, (bar, value) in enumerate(zip(self.axis_bars, axes)):
            bar.setValue(round((max(-1, min(1, value)) + 1) * 1000))
            bar.setFormat(f"Axis {i}: {value:+.3f}")
        for i, (light, pressed) in enumerate(zip(self.button_lights, buttons)):
            light.setText(f"{i}: {'ON' if pressed else 'OFF'}")
            light.setStyleSheet("padding: 6px; border-radius: 4px; background: "
                + ("#185448; color: #8ff0ca;" if pressed else "#202d3e; color: #aab8cc;"))
        for i, (label, (x, y)) in enumerate(zip(self.hat_labels, hats)):
            direction = " ".join(filter(None, ["Up" if y > 0 else "Down" if y < 0 else "",
                "Right" if x > 0 else "Left" if x < 0 else ""])) or "Centered"
            label.setText(f"Hat {i}: {direction}")

    def cancel_identification(self):
        if not hasattr(self, "identify_timer"):
            return
        self.identify_timer.stop()
        for device, _, _ in self.identifying:
            try:
                device.quit()
            except self._pygame.error:
                pass
        self.identifying = []
        self.identify_btn.setText("Identify controller")
        self.device_combo.setEnabled(True)
        self.connect_btn.setEnabled(bool(self._devices))

    def identify_controller(self):
        if self.identify_timer.isActive():
            self.cancel_identification()
            self.monitor_status.setText("Identification cancelled")
            return
        self.stop_monitoring(announce=False)
        self.identify_ticks = 0
        try:
            self._pygame.event.pump()
            for i in range(self.device_combo.count()):
                info = self.device_combo.itemData(i)
                if not info:
                    continue
                device = self._pygame.joystick.Joystick(info["index"])
                self.identifying.append((device, i, None))
                device.init()
                if device.get_instance_id() != info["instance"]:
                    raise self._pygame.error("Controller order changed; refresh controllers.")
                self.identifying[-1] = (device, i, self.input_snapshot(device))
        except self._pygame.error:
            self.cancel_identification()
            self.monitor_status.setText("Controller unavailable. Refresh controllers.")
            return
        self.connect_btn.setEnabled(False)
        self.device_combo.setEnabled(False)
        self.identify_btn.setText("Cancel identification")
        self.monitor_status.setText("Move an axis or press a button on one controller (15 seconds).")
        self.identify_timer.start(50)

    @staticmethod
    def input_snapshot(device):
        return ([device.get_axis(i) for i in range(device.get_numaxes())],
                [bool(device.get_button(i)) for i in range(device.get_numbuttons())],
                [device.get_hat(i) for i in range(device.get_numhats())])

    def identify_tick(self):
        self.identify_ticks += 1
        matches = []
        try:
            self._pygame.event.pump()
            removed = {event.instance_id for event in self._pygame.event.get([self._pygame.JOYDEVICEREMOVED])}
            for device, index, baseline in self.identifying:
                if device.get_instance_id() in removed:
                    raise self._pygame.error("Disconnected")
                axes, buttons, hats = self.input_snapshot(device)
                if (any(abs(a-b) >= 0.25 for a,b in zip(axes, baseline[0]))
                    or any(a and not b for a,b in zip(buttons, baseline[1]))
                    or hats != baseline[2]):
                    matches.append(index)
        except self._pygame.error:
            self.cancel_identification()
            self.monitor_status.setText("Controller disconnected. Refresh controllers.")
            return
        if len(matches) == 1:
            self.cancel_identification()
            self.device_combo.setCurrentIndex(matches[0])
            self.monitor_status.setText("Identified: " + self.device_combo.currentText())
        elif len(matches) > 1:
            self.cancel_identification()
            self.monitor_status.setText("Multiple controllers moved. Try again using only one controller.")
        elif self.identify_ticks >= 300:
            self.cancel_identification()
            self.monitor_status.setText("No input detected. Try identifying again.")
