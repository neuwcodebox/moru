# Moru

[한국어](README.ko.md)

**Create with words. Refine, compare, and branch. All locally.**

Moru is a Windows desktop app for making images through conversation. Describe a scene,
look at the result, and tell it what to change. A local LLM writes the image prompt, and
Anima or FLUX.2 generates the image on your computer.

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
- **Choose how to generate.** Choose Anima Turbo, Anima Aesthetic, or FLUX.2 klein 4B.
  Adjust image dimensions, Steps, CFG, and Seed.
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

[Download Moru.zip (Google Drive)](https://drive.google.com/file/d/1Y_aYECQ6VqFdV51_GoDl_Uy2-r51NWwW/view?usp=sharing)

1. Extract the entire `Moru.zip` archive and run `Moru.exe`.
2. Open **Model setup** to download the required models or select local files you already have.
3. Describe a scene in the input box and send it. Continue with changes after the image appears.

The portable build includes the application runtimes, so you do not need to install Python,
Node.js, or ComfyUI separately. Models are downloaded separately; their use is governed
by their distributors' licenses. Downloading models requires an internet connection.

### Manual model download

If downloading in the app fails, open **Model setup → Manual download** for the model,
or use the file-page links below. Click the download button on Hugging Face, then use
**Select file** for the matching model in Moru to choose the downloaded file.
You can keep the original filename and save it anywhere.

The prompt-writing model is required for every image model. Choose the family and
version in **Model setup**, then prepare its listed files. Choose the active model separately
in **Generation settings**. Anima needs one version plus the
shared text-understanding and image-decoding models.
FLUX.2 klein 4B needs its own diffusion, text encoder, and VAE files.

| Model | File to download |
| --- | --- |
| Prompt-writing model | [Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf](https://huggingface.co/HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive/blob/c09cdbcdb1fefad6d335809d445621b5f5ba0c6e/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive-Q4_K_M.gguf) |
| Anima text-understanding model | [qwen_3_06b_base.safetensors](https://huggingface.co/circlestone-labs/Anima/blob/f973fc41ec7545364ac9776c2440285f43ff2a30/split_files/text_encoders/qwen_3_06b_base.safetensors) |
| Anima image-decoding model | [qwen_image_vae.safetensors](https://huggingface.co/circlestone-labs/Anima/blob/f973fc41ec7545364ac9776c2440285f43ff2a30/split_files/vae/qwen_image_vae.safetensors) |
| Anima Turbo | [anima-turbo-v1.1.safetensors](https://huggingface.co/circlestone-labs/Anima/blob/f973fc41ec7545364ac9776c2440285f43ff2a30/split_files/diffusion_models/anima-turbo-v1.1.safetensors) |
| Anima Aesthetic | [anima-aesthetic-v1.1.safetensors](https://huggingface.co/circlestone-labs/Anima/blob/f973fc41ec7545364ac9776c2440285f43ff2a30/split_files/diffusion_models/anima-aesthetic-v1.1.safetensors) |
| FLUX.2 klein 4B | [flux-2-klein-4b-fp8.safetensors](https://huggingface.co/black-forest-labs/FLUX.2-klein-4b-fp8/blob/5b4408e59397a4a37ccb46afe426d8ed86379441/flux-2-klein-4b-fp8.safetensors) |
| FLUX.2 text encoder (FP4) | [qwen_3_4b_fp4_flux2.safetensors](https://huggingface.co/Comfy-Org/vae-text-encorder-for-flux-klein-4b/blob/8556e4d870cda7c53c7942b190bfeea5be9bd411/split_files/text_encoders/qwen_3_4b_fp4_flux2.safetensors) |
| FLUX.2 VAE | [flux2-vae.safetensors](https://huggingface.co/Comfy-Org/flux2-klein-4B/blob/5f526678002e43af5551dadb73ce2e8c91b43afe/split_files/vae/flux2-vae.safetensors) |

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
