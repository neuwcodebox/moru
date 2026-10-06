# Model sources

The portable application does not include model weights. Model downloads are pinned
in `src/moru/model-manifest.json` and verified by size and SHA-256.

- Anima, its bundled text encoder and VAE: https://huggingface.co/circlestone-labs/Anima/tree/f973fc41ec7545364ac9776c2440285f43ff2a30
  Original license: https://huggingface.co/circlestone-labs/Anima/blob/f973fc41ec7545364ac9776c2440285f43ff2a30/LICENSE.md
- Default prompt model: https://huggingface.co/HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive/tree/c09cdbcdb1fefad6d335809d445621b5f5ba0c6e (Apache-2.0).
  Previously supported prompt quantization: https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/tree/e87f176479d0855a907a41277aca2f8ee7a09523
  Upstream model: https://huggingface.co/Qwen/Qwen3.5-4B (Apache-2.0).

- FLUX.2 klein 4B distilled FP8: https://huggingface.co/black-forest-labs/FLUX.2-klein-4b-fp8/tree/5b4408e59397a4a37ccb46afe426d8ed86379441 (Apache-2.0).
  Original license: https://huggingface.co/black-forest-labs/FLUX.2-klein-4b-fp8/blob/5b4408e59397a4a37ccb46afe426d8ed86379441/LICENSE.md
- FLUX.2 klein Qwen3 4B FP4 encoder: https://huggingface.co/Comfy-Org/vae-text-encorder-for-flux-klein-4b/tree/8556e4d870cda7c53c7942b190bfeea5be9bd411 (Apache-2.0).
  Upstream encoder: https://huggingface.co/Qwen/Qwen3-4B (Apache-2.0).
- FLUX.2 klein VAE and optional FP16 encoder: https://huggingface.co/Comfy-Org/flux2-klein-4B/tree/5f526678002e43af5551dadb73ce2e8c91b43afe (Apache-2.0).

The unmodified Anima and FLUX.2 klein licenses are included in this directory. Application and dependency
licenses do not replace model licenses.
