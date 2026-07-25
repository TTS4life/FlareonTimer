import json
import pathlib
import sys

import src.config

from src.config import PATH_CONFIG, PATH_FILE, PATH_TIMERS, config, timers


class TestGetPath:
    def test_source_checkout_resolves_to_the_project_root(self):
        path = src.config.get_path()

        assert (path / "assets" / "json" / "timers.json").is_file()
        assert (path / "src" / "config.py").is_file()

    def test_frozen_build_resolves_next_to_the_executable(self, monkeypatch, tmp_path):
        """PyInstaller puts the bundled assets in _internal beside the exe."""
        monkeypatch.setattr(sys, "frozen", True, raising = False)
        monkeypatch.setattr(sys, "executable", str(tmp_path / "flareontimer.exe"))

        assert src.config.get_path() == tmp_path / "_internal"

    def test_source_checkout_is_not_the_frozen_layout(self, monkeypatch):
        monkeypatch.delattr(sys, "frozen", raising = False)

        assert src.config.get_path().name != "_internal"


class TestPaths:
    def test_paths_are_built_from_path_file(self):
        assert PATH_TIMERS == str(PATH_FILE / "assets" / "json" / "timers.json")
        assert PATH_CONFIG == str(PATH_FILE / "assets" / "json" / "config.json")

    def test_paths_exist(self):
        assert pathlib.Path(PATH_TIMERS).is_file()
        assert pathlib.Path(PATH_CONFIG).is_file()


class TestLoaded:
    def test_timers_and_config_are_dicts(self):
        assert isinstance(timers, dict)
        assert isinstance(config, dict)

    def test_loaded_values_match_the_files_on_disk(self):
        with open(PATH_TIMERS) as file_timers: assert json.load(file_timers) == timers
        with open(PATH_CONFIG) as file_config: assert json.load(file_config) == config
