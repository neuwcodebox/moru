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
];
export const generationSettings: Settings = {
  model_id: "anima-turbo-v1.1", width: 1024, height: 1024, steps: 10, cfg: 1, seed: null,
};
