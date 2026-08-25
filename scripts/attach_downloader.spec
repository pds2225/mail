# -*- mode: python ; coding: utf-8 -*-
# PyInstaller onefile — 저장소 루트에서 실행:
#   pyinstaller --noconfirm --clean scripts/attach_downloader.spec
# (이 스펙 파일 위치=scripts/ 기준 상대경로)

block_cipher = None

a = Analysis(
    ['attach_downloader_app.py'],
    pathex=['..'],
    binaries=[],
    datas=[
        ('../mail_core', 'mail_core'),
        ('requirements-attach.txt', 'scripts'),
        ('notice_download_config.json', 'scripts'),
    ],
    hiddenimports=[
        'monitor',
        'httpx',
        'bs4',
        'certifi',
        'cryptography',
        'dotenv',
        'mail_core',
        'mail_core.paths',
        'mail_core.delivery',
        'mail_core.delivery.outbox',
        'mail_core.delivery.state',
        'mail_core.operations',
        'mail_core.operations.run_lock',
        'mail_core.security',
        'mail_core.security.net_guard',
        'mail_core.security.private_config',
        'mail_core.storage',
        'mail_core.storage.seen_ids_prune',
        'mail_core.storage.state_store',
        'mail_core.storage.secure_store',
        'scripts',
        'scripts.fetch_notice_attachments',
        'scripts.download_kstartup_targets',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'streamlit',
        'flask',
        'gspread',
        'google',
        'googleapiclient',
        'pytest',
        'respx',
        'playwright',
        'tkinter',
    ],
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
    name='지원사업_공고첨부_받기',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
