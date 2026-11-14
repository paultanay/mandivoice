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

test("completed line values resolve stale price questions", () => {
  const app = loadApp();
  const question = "What is the price of the brown bread per packet?";
  const draft = {
    lines: [
      {
        name: "paneer",
        quantity: "250",
        unit_price: "50",
        price_basis: "unit",
      },
      {
        name: "brown bread",
        quantity: "1",
        unit_price: "40",
        price_basis: "unit",
      },
    ],
    clarifications: [question],
  };
  const items = [
    { name: "paneer", quantity: "250", unit_price: "50" },
    { name: "brown bread", quantity: "1", unit_price: "40" },
  ];

  assert.deepEqual([...app.getOpenClarifications(draft, items)], []);
});

test("missing price questions remain open until amount and basis are set", () => {
  const app = loadApp();
  const question = "What is the price of paneer?";
  const draft = {
    lines: [
      { name: "paneer", quantity: "250", unit_price: null, price_basis: null },
    ],
    clarifications: [question],
  };
  const items = [{ name: "paneer", quantity: "250", unit_price: "" }];

  assert.deepEqual([...app.getOpenClarifications(draft, items)], [question]);
});

test("a question naming multiple items stays open if one price is missing", () => {
  const app = loadApp();
  const question = "What is the price of paneer and brown bread?";
  const draft = {
    lines: [
      { name: "paneer", price_basis: "unit" },
      { name: "brown bread", price_basis: null },
    ],
    clarifications: [question],
  };
  const items = [{ unit_price: "50" }, { unit_price: "" }];

  assert.deepEqual([...app.getOpenClarifications(draft, items)], [question]);
});

test("a reviewed complete draft enables calculation after its price question is resolved", () => {
  const app = loadApp();
  const row = new Element("div");
  const fields = [
    ["name", "brown bread"],
    ["quantity", "1"],
    ["unit_price", "40"],
  ];
  const inputs = fields.map(([key, value]) => {
    const input = new Element("input");
    input.dataset.key = key;
    input.value = value;
    return input;
  });
  row.querySelectorAll = () => inputs;
  app.elements.get("lineItems").querySelectorAll = () => [row];
  app.elements.get("confirmOrder").checked = true;
  const draft = {
    lines: [
      {
        name: "brown bread",
        price_basis: "unit",
        price_unit: "packet",
        unit: "packet",
        pack_size: null,
        tax_rate_percent: null,
        tax_inclusive: false,
        discount_kind: "none",
        free_quantity: "0",
      },
    ],
    clarifications: ["What is the price of the brown bread per packet?"],
    charges: [],
    returns: [],
    payments: [],
    order_discount_kind: "none",
  };
  vm.runInContext(
    "activeOrderDraft = " +
      JSON.stringify(draft) +
      "; interpretationIssues = []",
    app,
  );

  app.updateReviewControls();

  assert.equal(app.elements.get("calculateButton").disabled, false);
});

test("mixed-unit Hindi drafts explain why read-back is unavailable", () => {
  const app = loadApp();
  const row = new Element("div");
  row.querySelectorAll = () => [];
  app.elements.get("lineItems").querySelectorAll = () => [row];
  const draft = {
    lines: [
      {
        name: "paneer",
        price_basis: "unit",
        price_unit: "kg",
        unit: "g",
        pack_size: null,
        tax_rate_percent: null,
        tax_inclusive: false,
        discount_kind: "none",
        free_quantity: "0",
      },
    ],
    clarifications: [],
    charges: [],
    returns: [],
    payments: [],
    order_discount_kind: "none",
  };
  vm.runInContext(
    "activeOrderDraft = " +
      JSON.stringify(draft) +
      "; detectedLanguageCode = 'hi-IN'; interpretationIssues = []",
    app,
  );

  app.updateReviewControls();

  assert.equal(app.elements.get("readbackButton").disabled, true);
  assert.equal(app.elements.get("readbackHint").hidden, false);
});

test("a simple Hindi item with one GST rate can be read back", () => {
  const app = loadApp();
  const input = (key, value) => {
    const field = new Element("input");
    field.dataset.key = key;
    field.value = value;
    return field;
  };
  const row = new Element("div");
  row.querySelectorAll = (selector) =>
    selector === "input"
      ? [
          input("name", "बासमती राइस"),
          input("quantity", "2"),
          input("unit_price", "40"),
        ]
      : [];
  app.elements.get("lineItems").querySelectorAll = (selector) =>
    selector === ".item-row" ? [row] : [];
  app.elements.get("gstRate").value = "0";
  vm.runInContext(
    "activeOrderDraft = " +
      JSON.stringify({
        lines: [
          {
            unit: "kg",
            price_unit: "kg",
            price_basis: "unit",
            pack_size: null,
            tax_rate_percent: "5",
            tax_inclusive: false,
            discount_kind: "none",
            free_quantity: "0",
          },
        ],
        default_tax_rate_percent: null,
        clarifications: [],
        charges: [],
        returns: [],
        payments: [],
        order_discount_kind: "none",
      }) +
      "; detectedLanguageCode = 'hi-IN'; interpretationIssues = []",
    app,
  );

  app.updateReviewControls();

  assert.equal(app.elements.get("readbackButton").disabled, false);
  assert.equal(app.getReadbackTaxRate(), "5");
  assert.deepEqual(
    JSON.parse(JSON.stringify(app.getReadbackItems())),
    [{ name: "बासमती राइस (kg)", quantity: "2", unit_price: "40" }],
  );
});

test("different item GST rates remain ineligible for one-rate read-back", () => {
  const app = loadApp();
  vm.runInContext(
    `activeOrderDraft = ${JSON.stringify({
      lines: [
        { tax_rate_percent: "5" },
        { tax_rate_percent: "12" },
      ],
      default_tax_rate_percent: null,
    })};`,
    app,
  );

  assert.equal(app.getReadbackTaxRate(), null);
});

test("the page uses a repository link instead of local workspace labels", () => {
  const html = readFileSync(
    new URL("../app/static/index.html", import.meta.url),
    "utf8",
  );

  assert.match(
    html,
    /href="https:\/\/github\.com\/paultanay\/mandivoice"[^>]*>GitHub repository/,
  );
  assert.doesNotMatch(
    html,
    /Local workspace|Built for busy counters|A working draft for a busy shop counter|Running on this device/,
  );
});
