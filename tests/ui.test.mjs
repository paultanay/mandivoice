import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

class Element {
  constructor(tagName = "div") {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.listeners = new Map();
    this.classList = { toggle() {} };
    this.dataset = {};
  }

  append(...children) {
    this.children.push(...children);
  }

  addEventListener(name, listener) {
    this.listeners.set(name, listener);
  }

  querySelectorAll() {
    return [];
  }

  setAttribute() {}

  removeAttribute() {}

  replaceChildren(...children) {
    this.children = children;
  }
}

function loadApp() {
  const elements = new Map();
  const document = {
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, new Element());
      return elements.get(id);
    },
    createElement(tagName) {
      return new Element(tagName);
    },
  };
  const context = vm.createContext({ document, window: {} });
  context.elements = elements;
  const source = readFileSync(
    new URL("../app/static/app.js", import.meta.url),
    "utf8",
  );
  vm.runInContext(source, context, { filename: "app.js" });
  return context;
}

test("draft editor selects the current value and listens once for selection changes", () => {
  const app = loadApp();
  const entry = new Element("li");

  app.addDraftEditor(entry, "Price basis", "pack", () => {}, {
    choices: [
      { value: "unit", label: "Per unit" },
      { value: "pack", label: "Per pack" },
      { value: "line_total", label: "Line total" },
    ],
  });

  const select = entry.children[0].children[1];
  assert.equal(select.value, "pack");
  assert.deepEqual([...select.listeners.keys()], ["change"]);
});

test("the review panel displays duplicate API issues once", () => {
  const app = loadApp();
  const question = "What price should I use for paneer?";
  vm.runInContext(`interpretationIssues = [${JSON.stringify(question)}]`, app);
  app.showOrderDetails({
    status: "needs_clarification",
    draft: {
      lines: [],
      order_discount_value: null,
      order_discount_kind: "none",
      order_discount_evidence: null,
      order_discount_after_tax: false,
      round_off: false,
      charges: [],
      returns: [],
      previous_balance: null,
      payments: [],
      customer_gstin: null,
      default_tax_rate_percent: null,
      clarifications: [question],
      unsupported_requests: [],
    },
  });

  const panel = app.elements.get("orderDetails");
  const issueList = panel.children.find(
    (child) => child.className === "order-issues",
  );

  assert.equal(issueList.children.length, 1);
});
