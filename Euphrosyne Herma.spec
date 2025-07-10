# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['data_upload/gui.py'],
    pathex=[],
    binaries=[],
    datas=[('assets/icon.png', 'assets'), ('config.yml', '.'), ('bin/*', 'bin')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Euphrosyne Herma',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/icon.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Euphrosyne Herma',
)
app = BUNDLE(
    coll,
    name='Euphrosyne Herma.app',
    icon='assets/icon.icns',
    bundle_identifier=None,
)
