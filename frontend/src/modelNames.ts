export const imageModelNames: Record<string, string> = {
  "anima-turbo-v1.1": "Anima Turbo",
  "anima-aesthetic-v1.1": "Anima Aesthetic",
};

export const modelNames: Record<string, string> = {
  ...imageModelNames,
  prompt: "프롬프트 작성 모델",
  text_encoder: "문장 이해 모델",
  vae: "이미지 복원 모델",
};
