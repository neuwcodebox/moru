"""Fetch and verify the project-pinned ComfyUI core revision."""

import subprocess

from moru.config import application_root


def main():
    root = application_root()
    destination = root / "vendor/comfyui"
    revision = (root / "vendor/comfyui-revision.txt").read_text().strip()
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "git",
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                "https://github.com/Comfy-Org/ComfyUI.git",
                str(destination),
            ],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(destination), "checkout", "--detach", revision], check=True
        )
    actual = subprocess.check_output(
        [
            "git",
            "-c",
            f"safe.directory={destination.as_posix()}",
            "-C",
            str(destination),
            "rev-parse",
            "HEAD",
        ],
        text=True,
    ).strip()
    if actual != revision:
        raise RuntimeError(
            "ComfyUI revision differs from the project pin; restore it before building"
        )
    modified = subprocess.check_output(
        [
            "git",
            "-c",
            f"safe.directory={destination.as_posix()}",
            "-C",
            str(destination),
            "status",
            "--porcelain",
            "--untracked-files=no",
        ],
        text=True,
    ).strip()
    if modified:
        raise RuntimeError("Pinned ComfyUI contains local changes; refusing to replace them")
    print(f"ComfyUI core verified: {actual}")


if __name__ == "__main__":
    main()
