PYTHON ?= $(shell if [ -x venv/bin/python ]; then printf 'venv/bin/python'; else printf 'python3'; fi)
PYINSTALLER ?= pyinstaller

.PHONY: install install-dev run format style test build-windows build-mac

install:
	$(PYTHON) -m pip install -r requirements/base.txt

install-dev:
	$(PYTHON) -m pip install -r requirements/dev.txt

run:
	$(PYTHON) -m data_upload.main

format:
	$(PYTHON) -m isort . --profile black
	$(PYTHON) -m black .

style:
	$(PYTHON) -m isort . --profile black --check-only
	$(PYTHON) -m black . --check

test:
	$(PYTHON) -m pytest

build-windows:
	$(PYINSTALLER) --add-data "assets/icon.png:assets" --name "Euphrosyne Herma" --add-data "config.yml:." --windowed --icon assets/icon.ico data_upload/gui.py

build-mac:
	$(PYINSTALLER) --add-data "assets/icon.png:assets" --name "Euphrosyne Herma" --add-data "config.yml:." --windowed --icon assets/icon.icns data_upload/gui.py
