"""Ce/Tb formal-composition enumerator."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("ce-tb-formula-enumerator")
except PackageNotFoundError:  # pragma: no cover - source tree without installation
    __version__ = "0.1.0"
