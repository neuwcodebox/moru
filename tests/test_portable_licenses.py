import importlib.metadata
import runpy
from pathlib import Path


def test_portable_distribution_includes_i18n_and_runtime_dependency_licenses(tmp_path, monkeypatch):
    packages = (
        "react", "react-dom", "lucide-react", "i18next", "react-i18next",
        "@babel/runtime", "html-parse-stringify", "use-sync-external-store",
    )
    for package in packages:
        license_file = tmp_path / "frontend/node_modules" / package / "LICENSE"
        license_file.parent.mkdir(parents=True)
        license_file.write_text(f"{package} license", encoding="utf-8")
    (tmp_path / "vendor/comfyui").mkdir(parents=True)
    (tmp_path / "vendor/comfyui/LICENSE").write_text("ComfyUI license", encoding="utf-8")
    (tmp_path / "vendor/licenses").mkdir()
    (tmp_path / "vendor/licenses/model.txt").write_text("Model license", encoding="utf-8")
    monkeypatch.setattr(importlib.metadata, "distributions", lambda: [])
    builder = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/build_portable.py"))

    destination = tmp_path / "release/licenses"
    builder["copy_licenses"](destination, tmp_path)

    for package in packages:
        assert (destination / "frontend" / package / "LICENSE").read_text(encoding="utf-8") == (
            f"{package} license"
        )
