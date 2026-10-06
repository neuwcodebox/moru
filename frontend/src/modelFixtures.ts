import type { ImageModel, Settings } from "./api";

export const imageModels: ImageModel[] = [
  {
    id: "anima-turbo-v1.1", name: "Anima Turbo", family: "anima", family_name: "Anima",
    variant_name: "Turbo", asset_ids: ["anima-turbo-v1.1", "text_encoder", "vae"],
    defaults: { steps: 10, cfg: 1 },
  },
  {
    id: "anima-aesthetic-v1.1", name: "Anima Aesthetic", family: "anima", family_name: "Anima",
    variant_name: "Aesthetic", asset_ids: ["anima-aesthetic-v1.1", "text_encoder", "vae"],
    defaults: { steps: 40, cfg: 4.5 },
  },
  {
    id: "flux2-klein-4b", name: "FLUX.2 klein 4B", family: "flux2", family_name: "FLUX.2",
    variant_name: "klein 4B", asset_ids: ["flux2-klein-4b", "flux2_text_encoder", "flux2_vae"],
    defaults: { steps: 4, cfg: 1 },
  },
];
export const generationSettings: Settings = {
  model_id: "anima-turbo-v1.1", width: 1024, height: 1024, steps: 10, cfg: 1, seed: null,
};
