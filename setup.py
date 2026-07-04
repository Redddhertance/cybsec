"""builds the c++ ac_engine ext via pybind11.

pure-python bits live in pyproject.toml - this file's only here to compile the
native module (setuptools cant do that declaratively). `pip install -e .` does both.
"""

from pybind11.setup_helpers import Pybind11Extension, build_ext
from setuptools import setup

ext_modules = [
    Pybind11Extension(
        "ac_engine",
        ["engine/bindings.cpp", "engine/aho_corasick.cpp"],
        include_dirs=["engine"],
        cxx_std=17,
    ),
]

setup(
    ext_modules=ext_modules,
    cmdclass={"build_ext": build_ext},
)
