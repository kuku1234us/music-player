# -*- mode: python ; coding: utf-8 -*-
import os
import sys

# Get the absolute path to the current directory
base_dir = os.path.abspath('.')

# Add the 'src' directory to the sys.path for analysis
sys.path.insert(0, os.path.join(base_dir, 'src'))

# Get absolute icon path
icon_path = os.path.abspath(os.path.join(base_dir, 'assets', 'app.ico'))
print(f"Using icon path: {icon_path}")

block_cipher = None

a = Analysis(
    ['src/youtubemaster/main.py'],
    pathex=[
        base_dir,
        os.path.join(base_dir, 'src'),
    ],
    binaries=[],
    datas=[
        ('src/youtubemaster/resources', 'youtubemaster/resources'),
        ('assets', 'assets'),
        ('.env', '.'),
        ('src/config.yaml', '.'),  # Put in root directory
    ],
    hiddenimports=[
        'yt_dlp.utils', 
        'yt_dlp.options',
        'PyQt6',
        'PyQt6.QtWidgets',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.sip',
        'requests',
        'ruamel.yaml',
        'PIL',
        'youtubemaster',
        'youtubemaster.ui',
        'youtubemaster.ui.main_window',
        'youtubemaster.ui.VideoInput',
        'youtubemaster.ui.DownloadQueue',
        'youtubemaster.ui.YoutubeProgress',
        'youtubemaster.ui.FlowLayout',
        'youtubemaster.utils',
        'youtubemaster.models',
        'youtubemaster.services',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['hook_youtubemaster.py'],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='YouTubeMaster',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Set to False to remove console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
) 