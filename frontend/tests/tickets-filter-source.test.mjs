import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");

assert.match(appSource, /response\.tickets\.some/);
assert.match(appSource, /setSelectedTicket\(null\)/);
assert.match(appSource, /每页数量/);
assert.match(appSource, /第 \{pagination\.page\} \/ \{pagination\.totalPages\} 页/);
assert.match(appSource, /goToTicketPage\(pagination\.page - 1\)/);
assert.match(appSource, /goToTicketPage\(pagination\.page \+ 1\)/);
assert.match(appSource, /page_size: nextPageSize/);

console.log("tickets-filter-source.test.mjs passed");
