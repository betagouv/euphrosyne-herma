**Project Understanding**
This is a small PySide6 desktop app for uploading local run data to Euphrosyne-backed Azure storage. The main path is `data_upload/gui.py`: it loads `config.yml`, checks/downloads AzCopy, initializes or refreshes auth, prompts login if needed, then opens `DataUploadWidget`.

The upload flow is: fetch projects from Euphrosyne, let the user choose project/run/data type/folder, call the tools API to initialize folders, request an upload SAS URL, then run AzCopy in a `QThread` while streaming stdout/stderr into a `QTextEdit`.

Configuration is YAML plus environment override for `EUPHROSYNE_URL`. Tokens live in Qt `QSettings`. Tests are located in tests package, and packaging is partly PyInstaller-based through the GitHub release workflow.

**Findings**

- Medium: Refresh tokens are stored directly in `QSettings`: [data_upload/app/login.py](/Users/witold/dev/euphrosyne-toolkit/data-upload/data_upload/app/login.py:20). That is usually plaintext or lightly encoded platform storage, not a credential vault. For long-lived tokens, consider OS keychain storage or at least reducing token lifetime and adding an explicit logout/clear-token path.

- Medium: Users can type or paste a folder path, but the form validation only trusts `selected_folder`, which is set only by the file dialog: [data_upload/widget/data_location.py](/Users/witold/dev/euphrosyne-toolkit/data-upload/data_upload/widget/data_location.py:30), [data_upload/widget/data_upload.py](/Users/witold/dev/euphrosyne-toolkit/data-upload/data_upload/widget/data_upload.py:207). A valid typed path will not enable Start.

- Medium: `data_upload/main.py` is currently broken as an executable entry point. It references undefined argparse fields and imports `gui` as a top-level module: [data_upload/main.py](/Users/witold/dev/euphrosyne-toolkit/data-upload/data_upload/main.py:20), [data_upload/main.py](/Users/witold/dev/euphrosyne-toolkit/data-upload/data_upload/main.py:25). If it is legacy, remove it or make it delegate cleanly to `data_upload.gui`.

- Medium: Build/development metadata is inconsistent. The Makefile still references `new_aglae_data_converter`, `maturin`, and `nuitka3`: [Makefile](/Users/witold/dev/euphrosyne-toolkit/data-upload/Makefile:5), [Makefile](/Users/witold/dev/euphrosyne-toolkit/data-upload/Makefile:17). The README mentions Nuitka as a dev dependency, but `requirements/dev.txt` uses PyInstaller. This will slow down onboarding and release debugging.

- Medium: Sentry is initialized with `send_default_pii=True`: [data_upload/gui.py](/Users/witold/dev/euphrosyne-toolkit/data-upload/data_upload/gui.py:59). For a research data uploader, that should be a deliberate privacy decision with filtering around paths, project names, run labels, and tokens.
