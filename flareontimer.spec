a = Analysis(
    ['flareontimer.py'],
    pathex      = [],
    binaries    = [],
    datas       = [
        ('assets/sounds/*.wav', 'assets/sounds'),
        ('assets/json/*.json',  'assets/json'),
    ],
    hiddenimports = [],
    hookspath     = [],
    runtime_hooks = [],
    excludes      = [],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries = True,
    name             = 'flareontimer',
    console          = True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name = 'flareontimer',
)
