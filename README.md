# Moru

[한국어](README.ko.md)

**A local image-generation app: create with words, refine through conversation.**

![Creating and refining images in Moru with natural-language requests](docs/screenshot.png)

Moru is a Windows desktop app that turns natural-language descriptions into images.
You do not need to write image-generation prompts yourself: a local LLM turns your request
into a prompt, and a local image model creates the result. Once the models are set up,
you can use Moru offline. Your requests and images are not sent to external APIs.

## Create images through conversation

Describe a scene, such as “a silver-haired girl eating cup noodles outside a convenience store on a rainy night.”
Then refine the result with requests like “add an umbrella” or “just make her expression neutral.”
Moru uses the current image's prompt and your recent requests to apply the changes.

Generate several results from the same request to compare them, or branch from an earlier image
to explore a different direction. Requests, image versions, and generation settings are saved
locally, so you can return to them later.

When needed, you can edit the actual prompt directly and adjust the image-generation and prompt-LLM settings.

Anima Turbo is suited to quick experiments, while Anima Aesthetic is suited to generation with more steps.
Switching models applies the recommended Steps and CFG values for that model. You can then adjust them as needed.

## Getting started

You need Windows, an NVIDIA GPU and its drivers, and the Windows WebView2 Runtime.
Install Git, Python 3.12, uv, and Node.js 22.12 or later, then run these commands in PowerShell.
Initial setup requires an internet connection to download dependencies and ComfyUI.

```powershell
git clone https://github.com/neuwcodebox/moru.git
cd moru
uv sync --frozen --extra inference
uv run --extra inference python scripts/setup_comfyui.py
cd frontend
npm.cmd ci
npm.cmd run build
cd ..
uv run --extra inference python -m moru
```

When the app opens, use **Model setup** to download the required models or select files you have already downloaded.
Then describe your scene in the input box. Models are not included in the repository;
their use is governed by their respective distributors' licenses.

For subsequent launches, run this command from the repository folder:

```powershell
uv run --extra inference python -m moru
```

Models and work history are stored in the repository's `models/` and `data/` folders.
Moving the entire repository folder also moves your work history and any models stored within it.

## Development

Moru consists of a Python core and a React UI. The Python environment is managed with `uv`.
See the [technical documentation](docs/TECH.md#개발-및-검증) for development setup, running the app,
testing, and portable builds. The app's behavior and requirements are documented in [SPEC.md](docs/SPEC.md).
