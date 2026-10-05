import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import ko from "./locales/ko/translation.json";
import en from "./locales/en/translation.json";
import koDialogs from "./locales/ko/dialogs.json";
import enDialogs from "./locales/en/dialogs.json";
import koErrors from "./locales/ko/errors.json";
import enErrors from "./locales/en/errors.json";

// Bundle every locale: the desktop UI runs offline with connect-src 'none'.
void i18n.use(initReactI18next).init({
  resources: {
    ko: { translation: ko, dialogs: koDialogs, errors: koErrors },
    en: { translation: en, dialogs: enDialogs, errors: enErrors },
  },
  // Until the saved preference is available, failures must remain readable in English.
  lng: "en",
  fallbackLng: "en",
  supportedLngs: ["ko", "en"],
  defaultNS: "translation",
  initAsync: false,
  interpolation: { escapeValue: false },
});

i18n.on("languageChanged", (language) => {
  document.documentElement.lang = language;
});
document.documentElement.lang = i18n.resolvedLanguage ?? "en";

export default i18n;
