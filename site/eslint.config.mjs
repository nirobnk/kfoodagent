import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    rules: {
      // Plain <a>, never <Link>: every page is a full page load, as it was on
      // the static site. That keeps the Meta Pixel's PageView at exactly one
      // per page, and there is no client-side router for crawlers to trip on.
      "@next/next/no-html-link-for-pages": "off",
    },
  },
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Plain browser/Node scripts that are not part of the Next.js app:
    // the catalogue (also loaded by menu/menu-card.html) and the local tools.
    "products-data.js",
    "menu/**",
  ]),
]);

export default eslintConfig;
