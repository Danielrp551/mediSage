// Flat config de ESLint 9 usando las configuraciones nativas de eslint-config-next 16
// (exports ./core-web-vitals y ./typescript). Reemplaza el uso de FlatCompat, que con
// ESLint 9 fallaba al validar la config heredada ("circular structure to JSON"). Esto
// tambien sustituye al comando "next lint", removido en Next 16.
import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const config = [
  {
    ignores: [".next/**", "coverage/**", "node_modules/**", "next-env.d.ts"],
  },
  ...nextCoreWebVitals,
  ...nextTypescript,
  {
    rules: {
      "@typescript-eslint/consistent-type-imports": "error",
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
      // Reglas de eslint-plugin-react-hooks 7 orientadas a React Compiler (mas estrictas que el
      // codigo existente, que se escribio antes de esta version). Se desactivan para restaurar el
      // comportamiento de lint previo a la migracion de Next 16 (que rompio "next lint"). Quedan
      // como oportunidad de refactor aparte; no son errores de correctitud.
      "react-hooks/set-state-in-effect": "off",
      "react-hooks/refs": "off",
      "react-hooks/purity": "off",
      "react-hooks/incompatible-library": "off",
    },
  },
];

export default config;
