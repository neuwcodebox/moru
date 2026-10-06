"""Build a model-free Windows onedir release with all required inference runtimes."""

import argparse
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from moru.config import application_root


def copy_licenses(destination: Path, root: Path):
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / "vendor/comfyui/LICENSE", destination / "ComfyUI-LICENSE.txt")
    shutil.copytree(root / "vendor/licenses", destination / "models", dirs_exist_ok=True)
    for package in (
        "react", "react-dom", "lucide-react", "i18next", "react-i18next",
        "@babel/runtime", "html-parse-stringify", "use-sync-external-store",
    ):
        source = root / "frontend/node_modules" / package / "LICENSE"
        target = destination / "frontend" / package / "LICENSE"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata["Name"]
        for file in distribution.files or ():
            if ".dist-info/" in str(file) and any(
                label in file.name.lower() for label in ("license", "copying", "notice")
            ):
                source = Path(distribution.locate_file(file))
                if source.is_file():
                    target = destination / "dependencies" / name / file.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        shutil.copy2(python_license, destination / "Python-LICENSE.txt")


def seven_zip() -> str:
    executable = shutil.which("7z")
    if executable:
        return executable
    installed = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "7-Zip/7z.exe"
    if installed.is_file():
        return str(installed)
    raise FileNotFoundError("Install Windows 7-Zip or add 7z.exe to PATH before archiving")


def archive_release(application: Path, release: Path):
    application, release = application.resolve(), release.resolve()
    if not (application / "Moru.exe").is_file():
        raise FileNotFoundError("Build Moru.exe before creating its 7z archive")
    executable = seven_zip()
    release.mkdir(exist_ok=True)
    temporary = release / "Moru.7z.part"
    archive = release / "Moru.7z"
    temporary.unlink(missing_ok=True)
    try:
        subprocess.run(
            [executable, "a", "-t7z", "-mx=5", "-mmt=4", "-bsp0", str(temporary), application.name],
            cwd=application.parent, check=True,
        )
        subprocess.run([executable, "t", "-bsp0", str(temporary)], check=True)
        os.replace(temporary, archive)
    finally:
        temporary.unlink(missing_ok=True)
    (release / "last-build.json").write_text(
        json.dumps({"application": str(application), "archive": str(archive)}),
        encoding="utf-8",
    )
    print(f"Portable 7z: {archive}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reuse-staging", type=Path)
    parser.add_argument("--skip-archive", action="store_true")
    parser.add_argument("--archive-only", action="store_true")
    options = parser.parse_args()
    if sys.platform != "win32":
        raise RuntimeError("Build Windows portable releases on Windows")
    root = application_root()
    staging = options.reuse_staging or root / "build" / f"portable-{uuid.uuid4().hex[:8]}"
    staging = staging.resolve()
    if not staging.is_relative_to((root / "build").resolve()) or staging == root / "build":
        raise ValueError("Build staging must be a subdirectory of the project build folder")
    if options.archive_only:
        if options.reuse_staging is None:
            parser.error("--archive-only requires --reuse-staging")
        archive_release(staging / "dist/Moru", root / "release")
        return
    if not options.skip_archive:
        seven_zip()
    subprocess.run([sys.executable, str(root / "scripts/setup_comfyui.py")], check=True)
    subprocess.run(["npm.cmd", "run", "build"], cwd=root / "frontend", check=True)
    staging.mkdir(parents=True, exist_ok=True)
    os.environ["PYINSTALLER_CONFIG_DIR"] = str(root / ".cache/pyinstaller")
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--icon",
        str(root / "src/moru/assets/icon.ico"),
        "--name",
        "Moru",
        "--contents-directory",
        "runtime",
        "--distpath",
        str(staging / "dist"),
        "--workpath",
        str(staging / "work"),
        "--specpath",
        str(staging),
        "--paths",
        str(root / "src"),
        "--paths",
        str(root / "vendor/comfyui"),
        "--add-data",
        f"{root / 'src/moru/web'};moru/web",
        "--add-data",
        f"{root / 'src/moru/assets'};moru/assets",
        "--add-data",
        f"{root / 'src/moru/model-manifest.json'};moru",
        "--add-data",
        f"{root / 'vendor/comfyui/comfy'};comfy",
        "--add-data",
        f"{root / 'vendor/comfyui/folder_paths.py'};.",
        "--add-data",
        f"{root / 'vendor/comfyui-revision.txt'};.",
        "--hidden-import",
        "comfy.sd",
        "--hidden-import",
        "comfy.sample",
        "--hidden-import",
        "comfy.model_management",
        "--hidden-import",
        "comfy.utils",
        "--collect-data",
        "webview",
        "--collect-binaries",
        "llama_cpp",
    ]
    for package in (
        "torch",
        "torchvision",
        "transformers",
        "numpy",
        "tqdm",
        "regex",
        "huggingface-hub",
        "safetensors",
        "tokenizers",
        "packaging",
        "requests",
        "filelock",
        "sentencepiece",
        "pyyaml",
        "comfy-kitchen",
        "comfy-aimdo",
        "llama-cpp-python",
    ):
        command.extend(["--copy-metadata", package])
    command.append(str(root / "app.py"))
    with (staging / "build.log").open("w", encoding="utf-8") as build_log:
        subprocess.run(command, cwd=root, stdout=build_log, stderr=subprocess.STDOUT, check=True)
    application = staging / "dist/Moru"
    for directory in ("models", "data"):
        (application / directory).mkdir(exist_ok=True)
    copy_licenses(application / "licenses", root)
    (application / "README.txt").write_text(
        "Moru\n\n7z 전체를 압축 해제한 뒤 Moru.exe를 실행하세요.\n"
        "모델 준비 창에서 모델을 다운로드하거나 로컬 파일을 선택합니다.\n"
        "모델 준비 후에는 오프라인으로 사용할 수 있습니다.\n"
        "작업은 data 폴더에 저장됩니다. 앱을 이동할 때 data와 models도 함께 옮기세요.\n"
        "Turbo: Steps 10, CFG 1. Aesthetic: Steps 40, CFG 4.5. "
        "FLUX.2 klein 4B: Steps 4, CFG 1. Seed Auto.\n",
        encoding="utf-8",
    )
    release = root / "release"
    release.mkdir(exist_ok=True)
    if options.skip_archive:
        print(f"Portable application: {application}")
        return
    archive_release(application, release)
    print(f"Build log: {staging / 'build.log'}")


if __name__ == "__main__":
    main()
