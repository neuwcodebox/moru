"""Install lightweight modules at the ComfyUI/PyTorch import boundary."""

import sys
from types import SimpleNamespace


def install_runtime(
    monkeypatch, root, *, torch, management, sd=None, sample=None, utils=None, model_base=None,
):
    (root / "comfy").mkdir(exist_ok=True)
    (root / "comfy/sd.py").touch()
    monkeypatch.syspath_prepend(str(root))
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True, raising=False)
    modules = {
        "cli_args": SimpleNamespace(args=SimpleNamespace()),
        "sd": sd,
        "sample": sample,
        "model_management": management,
        "utils": utils,
        "model_base": model_base,
    }
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "comfy", SimpleNamespace(**modules))
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, f"comfy.{name}", module or SimpleNamespace())
