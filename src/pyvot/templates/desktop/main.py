"""{{name}}: {{t:desktop_doc}}"""

import sys

from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("{{name}}")
        self.resize(420, 380)

        self.entry = QLineEdit()
        self.entry.setPlaceholderText("{{t:desktop_placeholder}}")
        add_button = QPushButton("{{t:desktop_add}}")
        self.items = QListWidget()
        self.count = QLabel()

        row = QHBoxLayout()
        row.addWidget(self.entry, 1)
        row.addWidget(add_button)

        layout = QVBoxLayout()
        layout.addLayout(row)
        layout.addWidget(self.items, 1)
        layout.addWidget(self.count)
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        add_button.clicked.connect(self.add_item)
        self.entry.returnPressed.connect(self.add_item)
        self.update_count()

    def add_item(self) -> None:
        text = self.entry.text().strip()
        if text:
            self.items.addItem(text)
            self.entry.clear()
            self.update_count()

    def update_count(self) -> None:
        count = self.items.count()
        self.count.setText(f"{{t:desktop_count}}")


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
