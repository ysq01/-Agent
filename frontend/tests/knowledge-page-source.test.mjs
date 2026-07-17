import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/styles.css", import.meta.url), "utf8");
const types = readFileSync(new URL("../src/types.ts", import.meta.url), "utf8");

function getRule(selector) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = css.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`, "m"));
  return match?.[1] ?? "";
}

function hasDeclaration(rule, property, value) {
  return new RegExp(`${property}\\s*:\\s*${value}\\s*;`).test(rule);
}

assert.match(
  types,
  /export type KnowledgeDocument = \{[\s\S]*content: string;/,
  "KnowledgeDocument should include full policy content for the read-only modal",
);

assert.match(
  appSource,
  /selectedDocument/,
  "KnowledgePage should track a selected policy document",
);
assert.match(
  appSource,
  /setSelectedDocument\(document\)/,
  "policy cards should open the selected policy document",
);
assert.match(
  appSource,
  /className="policy-modal"/,
  "KnowledgePage should render a policy detail modal",
);
assert.match(
  appSource,
  /document\.body\.style\.overflow\s*=\s*"hidden"/,
  "opening a policy modal should lock page scrolling behind the dialog",
);
assert.match(
  appSource,
  /document\.body\.style\.overflow\s*=\s*previousBodyOverflow/,
  "closing a policy modal should restore the previous page scroll style",
);

const searchFormFieldFullRule = getRule(".search-form .field-full");
assert.ok(
  hasDeclaration(searchFormFieldFullRule, "margin-bottom", "0"),
  ".search-form .field-full should not offset the user-question input",
);

const searchFormRule = getRule(".search-form");
assert.ok(
  hasDeclaration(searchFormRule, "align-items", "end"),
  ".search-form should align input controls on the same baseline",
);

const policyModalRule = getRule(".policy-modal");
assert.ok(
  !/(^|;)\s*height\s*:/.test(policyModalRule),
  ".policy-modal should fit short policies instead of forcing a tall blank dialog",
);
assert.ok(
  hasDeclaration(policyModalRule, "grid-template-rows", "auto minmax\\(0, 1fr\\)"),
  ".policy-modal should reserve a shrinking scroll row for long policy content",
);

const modalBackdropRule = getRule(".modal-backdrop");
assert.ok(
  hasDeclaration(modalBackdropRule, "overflow", "hidden"),
  ".modal-backdrop should not scroll while the policy modal is open",
);

const policyModalContentRule = getRule(".policy-modal-content");
assert.ok(
  hasDeclaration(policyModalContentRule, "min-height", "0"),
  ".policy-modal-content must be allowed to shrink inside the modal grid",
);
assert.ok(
  hasDeclaration(policyModalContentRule, "max-height", "min\\(620px, calc\\(100vh - 180px\\)\\)"),
  ".policy-modal-content should cap long policies to the viewport",
);
assert.ok(
  hasDeclaration(policyModalContentRule, "overflow-y", "scroll"),
  ".policy-modal-content should always expose a vertical scrollbar for long policies",
);
assert.ok(
  hasDeclaration(policyModalContentRule, "overscroll-behavior", "contain"),
  ".policy-modal-content should contain wheel scrolling inside the modal",
);
assert.ok(
  hasDeclaration(policyModalContentRule, "scrollbar-gutter", "stable"),
  ".policy-modal-content should reserve space for the scrollbar",
);

console.log("knowledge-page-source.test.mjs passed");
