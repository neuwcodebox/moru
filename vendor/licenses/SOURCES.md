# Model sources

The portable application does not include model weights. Model downloads are pinned
in `src/moru/model-manifest.json` and verified by size and SHA-256.

- Anima, its bundled text encoder and VAE: https://huggingface.co/circlestone-labs/Anima/tree/f973fc41ec7545364ac9776c2440285f43ff2a30
  Original license: https://huggingface.co/circlestone-labs/Anima/blob/f973fc41ec7545364ac9776c2440285f43ff2a30/LICENSE.md
- Default prompt model: https://huggingface.co/HauhauCS/Qwen3.5-4B-Uncensored-HauhauCS-Aggressive/tree/c09cdbcdb1fefad6d335809d445621b5f5ba0c6e (Apache-2.0).
  Previously supported prompt quantization: https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/tree/e87f176479d0855a907a41277aca2f8ee7a09523
  Upstream model: https://huggingface.co/Qwen/Qwen3.5-4B (Apache-2.0).

The unmodified Anima license is included in this directory. Application and dependency
licenses do not replace model licenses.
