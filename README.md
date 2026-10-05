# Moru

[한국어](README.ko.md)

**Create with words. Refine, compare, and branch. All locally.**

Moru is a Windows desktop app for making images through conversation. Describe a scene,
look at the result, and tell it what to change. A local LLM writes the image prompt, and
Anima generates the image on your computer.

Your work grows as a conversation: try another result, choose a version you like,
or return to an earlier image and explore a different direction.

![Creating and refining images in Moru with natural-language requests](docs/demo-en.webp)

## A conversation that takes shape as images

Start with a description in your own words:

> A blonde woman eating ramen at a convenience store.

Then keep going:

> Make it a rainy evening.
>
> Give her a neutral expression.

Moru uses the current image's actual prompt and your recent requests to write the next
prompt and generate a new image. The prompt LLM can enrich a simple idea with fitting
lighting, atmosphere, and textures while following your explicit choices.
You can see the prompt being written and the image-generation progress in the conversation.

## Compare versions and explore branches

**Regenerate** creates a new image version using the same prompt and your current generation settings.
The results stay together as versions of the same conversation entry. Browse them,
choose one, and continue the conversation from that version.

**Fork** starts a separate project from an image you choose, carrying over the conversation
up to that point. Try a watercolor direction in one branch and a night scene in another.
The original project stays available, and each branch keeps its own subsequent work.

Successful images, prompts, settings, and version selections are saved locally.
Reopen a project later and continue where you left off.

## Automatic prompts, direct control

- **Edit the actual prompt.** Inspect or copy the prompt behind an image, change it yourself,
  and generate another version directly.
- **Choose how to generate.** Use Anima Turbo for quick iterations or Anima Aesthetic for
  generation with more sampling steps. Adjust image dimensions, Steps, CFG, and Seed.
- **Tune the prompt LLM.** Adjust thinking, reasoning level, context and output limits,
  and how much recent conversation it uses.
- **Inspect and share results.** Open images in the full-screen viewer, zoom and pan,
  browse versions, or copy the image to the clipboard.
- **Use Korean or English.** Switch the interface language while keeping your current work.

## Local from prompt to image

Both prompt writing and image generation run locally. No external API key is needed,
and your requests, prompts, and images are not sent to external inference services.
Once the models are ready, you can create and refine images offline.

Projects, images, and settings live in the app's `data/` folder; downloaded models live in
`models/`. Keep these folders with the app when moving it to preserve your work and models.

## Getting started

You need Windows, an NVIDIA GPU with its drivers, and the Windows WebView2 Runtime.

### Portable ZIP

1. Extract the entire `Moru.zip` archive and run `Moru.exe`.
2. Open **Model setup** to download the required models or select local files you already have.
3. Describe a scene in the input box and send it. Continue with changes after the image appears.

The portable build includes the application runtimes, so you do not need to install Python,
Node.js, or ComfyUI separately. Models are downloaded separately; their use is governed
by their distributors' licenses. Downloading models requires an internet connection.

### Run from source

Install Git, Python 3.12, uv, and Node.js 22.12 or later, then run these commands in PowerShell.
Initial setup downloads dependencies and ComfyUI.

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

For subsequent launches, run `uv run --extra inference python -m moru` from the repository folder.
The same model setup flow applies, and `data/` and `models/` are stored in that folder.

## Development

Moru combines a Python core with a React UI. See [TECH.md](docs/TECH.md#개발-및-검증)
for development setup, tests, and portable builds, and [SPEC.md](docs/SPEC.md) for product behavior.
