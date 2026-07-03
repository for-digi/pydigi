"""Single source of truth for the package version.

Kept in its own tiny module with only a literal assignment so it can be read
*without importing the package*: pyproject.toml resolves the distribution
version from ``pydigi.version.__version__`` (see ``[tool.setuptools.dynamic]``),
and the rest of the code imports it from here. Bump the version in one place.
"""

__version__ = "1.0.1"
