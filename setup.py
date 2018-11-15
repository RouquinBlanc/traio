import setuptools
import pathlib

root_dir = pathlib.Path(__file__).parent
with (root_dir / 'traio' / '__version__.py').open(encoding='utf-8') as f:
    exec(f.read())

setuptools.setup(
    version=__version__
)
