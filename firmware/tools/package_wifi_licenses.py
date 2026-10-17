"""Retain notices from the exact wheels used to build the portable sender."""
from importlib.metadata import distribution
from pathlib import Path
import shutil
import sys

destination = Path(sys.argv[1]) / 'third-party-licenses'
destination.mkdir(parents=True, exist_ok=True)
for name in ('numpy', 'Pillow', 'PyInstaller', 'pyserial'):
    package = distribution(name)
    for entry in package.files or ():
        if any(word in entry.name.lower() for word in ('license', 'copying', 'copyright')):
            source = Path(package.locate_file(entry))
            if source.is_file():
                target = destination / name / str(entry)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
for name in ('LICENSE.txt', 'LICENSE'):
    source = Path(sys.base_prefix) / name
    if source.is_file():
        shutil.copyfile(source, destination / ('Python-' + name))
