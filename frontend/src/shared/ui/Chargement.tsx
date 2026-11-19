import { useTranslation } from "react-i18next";

import "./ui.css";

export function Chargement() {
  const { t } = useTranslation();
  return <span className="chargement" role="status" aria-label={t("commun.chargement")} />;
}
