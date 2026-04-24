from data_upload import azcopy as azcopy_module
from data_upload.app import init as init_module


class FakeProgressDialog:
    NoButton = 0
    instances = []

    def __init__(self):
        self.window_title = None
        self.text = None
        self.standard_buttons = None
        self.modal = None
        self.show_count = 0
        self.close_count = 0
        FakeProgressDialog.instances.append(self)

    def setWindowTitle(self, title):
        self.window_title = title

    def setText(self, text):
        self.text = text

    def setStandardButtons(self, buttons):
        self.standard_buttons = buttons

    def setModal(self, modal):
        self.modal = modal

    def show(self):
        self.show_count += 1

    def close(self):
        self.close_count += 1


def test_init_azcopy_uses_writable_app_data_path_for_bundled_macos(
    qapp, monkeypatch, tmp_path
):
    FakeProgressDialog.instances = []
    bundle_dir = tmp_path / "Euphrosyne Herma.app" / "Contents" / "Frameworks"
    app_data_dir = tmp_path / "app-data"
    download_calls = []

    monkeypatch.setattr(init_module, "QMessageBox", FakeProgressDialog)
    monkeypatch.setattr(init_module, "is_azcopy_installed", lambda: False)
    monkeypatch.setattr(
        init_module,
        "download_azcopy",
        lambda: download_calls.append(azcopy_module.get_azcopy_path()),
    )

    monkeypatch.setattr(azcopy_module, "IS_BUNDLED", True)
    monkeypatch.setattr(azcopy_module, "_is_macos", True)
    monkeypatch.setattr(azcopy_module, "_is_windows", False)
    monkeypatch.setattr(azcopy_module, "BUNDLE_DIR", bundle_dir)
    monkeypatch.setattr(
        azcopy_module.QStandardPaths,
        "writableLocation",
        lambda location: str(app_data_dir),
    )

    init_module.init_azcopy(qapp)

    assert download_calls == [app_data_dir / "bin" / "azcopy" / "azcopy"]
    assert download_calls[0] != bundle_dir / "bin" / "azcopy" / "azcopy"
    assert len(FakeProgressDialog.instances) == 1
    assert FakeProgressDialog.instances[0].close_count == 1
