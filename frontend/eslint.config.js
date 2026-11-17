import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "coverage", "node_modules"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: { globals: { ...globals.browser } },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // Un montant n'est JAMAIS un nombre JavaScript (guide §B, annexe A.1).
      "no-restricted-globals": ["error", "parseFloat"],
      "no-restricted-properties": [
        "error",
        { object: "Number", property: "parseFloat", message: "Un montant se manipule avec decimal.js." },
      ],
      "@typescript-eslint/consistent-type-imports": "error",
    },
  },
  { files: ["**/*.config.{js,ts}"], languageOptions: { globals: { ...globals.node } } },
);
