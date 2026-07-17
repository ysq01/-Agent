import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");

function getRule(selector) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = css.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`, "m"));
  return match?.[1] ?? "";
}

function hasDeclaration(rule, property, value) {
  return new RegExp(`${property}\\s*:\\s*${value}\\s*;`).test(rule);
}

const adminMainStackRule = getRule(".admin-main-stack");
assert.ok(
  hasDeclaration(adminMainStackRule, "min-width", "0"),
  ".admin-main-stack must allow its table panels to shrink inside admin-layout",
);

const adminMainPanelRule = getRule(".admin-main-stack > .panel");
assert.ok(
  hasDeclaration(adminMainPanelRule, "min-width", "0"),
  ".admin-main-stack > .panel must not force the left admin column under the detail panel",
);

console.log("admin-layout-css.test.mjs passed");
