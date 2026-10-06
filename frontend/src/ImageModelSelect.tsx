import { useTranslation } from "react-i18next";
import type { ImageModel } from "./api";

export default function ImageModelSelect({
  models, modelId, onChange, disabled = false,
}: {
  models: ImageModel[];
  modelId: string;
  onChange: (model: ImageModel) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation("dialogs");
  const selected = models.find((model) => model.id === modelId);
  const families = models.filter((model, index) =>
    models.findIndex((other) => other.family === model.family) === index,
  );
  return (
    <div className="field-grid">
      <label>
        {t("common.model")}
        <select value={selected?.family ?? ""} disabled={disabled} onChange={(event) => {
          const model = models.find((model) => model.family === event.target.value);
          if (model) onChange(model);
        }}>
          {families.map((model) => <option key={model.family} value={model.family}>{model.family_name}</option>)}
        </select>
      </label>
      <label>
        {t("common.variant")}
        <select value={modelId} disabled={disabled} onChange={(event) => {
          const model = models.find((model) => model.id === event.target.value);
          if (model) onChange(model);
        }}>
          {models.filter((model) => model.family === selected?.family).map((model) =>
            <option key={model.id} value={model.id}>{model.variant_name}</option>,
          )}
        </select>
      </label>
    </div>
  );
}
