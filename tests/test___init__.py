from importlib.metadata import version

import nanobot_learn


def test_installed_package_version_matches_module_version() -> None:
    assert version("nanobot-learn") == nanobot_learn.__version__
