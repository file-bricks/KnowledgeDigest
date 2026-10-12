from importlib.resources import files
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from KnowledgeDigest.gui.app import _load_app_icon


def main() -> None:
    resource = files("KnowledgeDigest").joinpath("KnowledgeDigest.ico")
    assert resource.is_file(), "KnowledgeDigest.ico is missing from the installed package"
    icon_path = Path(str(resource))
    assert icon_path.stat().st_size > 0, "KnowledgeDigest.ico is empty"

    app = QApplication.instance() or QApplication(["knowledgedigest-package-smoke"])
    icon = QIcon(str(icon_path))
    assert not icon.isNull(), "Qt could not load the installed package icon"
    assert not _load_app_icon().isNull(), "the application icon loader returned a null icon"
    app.quit()


if __name__ == "__main__":
    main()
