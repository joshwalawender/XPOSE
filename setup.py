from setuptools import setup, find_packages

# You can have one or more plugins.  Just list them all here.
# For each one, add a setup function in plugins/__init__.py
#
entry_points = """
[ginga.rv.plugins]
XPOSE=plugins:setup_XPOSE
"""

setup(
    name = 'XPOSE',
    version = "0.1.dev",
    description = "Universal XPOSE GUI",
    author = "Josh Walawender",
    license = "BSD",
    # change this to your URL
    url = "https://github.com/joshwalawender/XPOSE",
    install_requires = ["ginga>=2.6.1"],
    packages = find_packages(),
    include_package_data = True,
    package_data = {},
    entry_points = entry_points,
)
