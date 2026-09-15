/* Front end for the Franc-anglais compiler.
   One endpoint, POST /api/analyze, returns the token stream, the language mixture,
   the parse verdict and the English translation in a single response. */

const el = (id) => document.getElementById(id);

const ui = {
  text: el("text"),
  prefer: el("prefer"),
  generate: el("generate"),
  detect: el("detect"),
  translate: el("translate"),
  status: el("status"),
  error: el("error"),
  result: el("result"),
  kicker: el("result-kicker"),
  answer: el("result-answer"),
  detail: el("result-detail"),
  dictionary: el("dictionary"),
  readings: el("readings"),
  analysis: el("analysis"),
  verdict: el("verdict"),
  categories: el("categories"),
  tokens: el("tokens"),
  treeToggle: el("tree-toggle"),
  tree: el("tree"),
  recent: el("recent"),
  recentList: el("recent-list"),
};

const history = [];
let busy = false;

/* ------------------------------------------------------------------ state */

function setBusy(state) {
  busy = state;
  ui.generate.disabled = state;
  ui.detect.disabled = state;
  ui.translate.disabled = state;
  ui.status.hidden = !state;
}

function showError(message) {
  ui.error.textContent = message;
  ui.error.hidden = false;
}

function clearOutput() {
  ui.error.hidden = true;
  ui.result.hidden = true;
  ui.dictionary.hidden = true;
  ui.analysis.hidden = true;
  collapseTree();
}

function collapseTree() {
  ui.tree.hidden = true;
  ui.treeToggle.textContent = "Show parse tree";
  ui.treeToggle.setAttribute("aria-expanded", "false");
}

/* ----------------------------------------------------------------- render */

function row(cells) {
  const tr = document.createElement("tr");
  for (const [value, className] of cells) {
    const td = document.createElement("td");
    td.textContent = value;
    if (className) td.className = className;
    tr.appendChild(td);
  }
  return tr;
}

function fill(tbody, rows) {
  tbody.replaceChildren(...rows);
}

function renderResult(kicker, answer, detail) {
  ui.kicker.textContent = kicker;
  ui.answer.textContent = answer;
  ui.detail.textContent = detail;
  ui.result.hidden = false;
}

function renderAnalysis(data) {
  const { syntax, tokens } = data;

  ui.verdict.textContent = syntax.accepted ? "ACCEPTED" : "REJECTED";
  ui.verdict.classList.toggle("rejected", !syntax.accepted);
  ui.categories.textContent = syntax.accepted
    ? syntax.categories.join("  ")
    : syntax.error;

  fill(ui.tokens, tokens.map((t) => row([
    [t.lexeme, "lexeme"],
    [t.category, "tag"],
    [t.language, "tag"],
    [t.gloss || "\u2014", "gloss"],
  ])));

  ui.tree.textContent = syntax.tree;
  ui.treeToggle.hidden = !syntax.tree;
  ui.analysis.hidden = false;
}

function renderReadings(readings) {
  if (!readings.length) return;
  fill(ui.readings, readings.map((r) => row([
    [r.language, "tag"],
    [r.category, "tag"],
    [r.english, "gloss"],
  ])));
  ui.dictionary.hidden = false;
}

function renderRecent(tag, input, output) {
  history.unshift({ tag, input, output });
  history.length = Math.min(history.length, 4);

  ui.recentList.replaceChildren(...history.map((entry) => {
    const div = document.createElement("div");
    div.className = "recent-row";
    for (const [value, className] of [
      [entry.tag, "recent-tag"],
      [entry.input, "recent-in"],
      [entry.output, "recent-out"],
    ]) {
      const span = document.createElement("span");
      span.className = className;
      span.textContent = value;
      div.appendChild(span);
    }
    return div;
  }));
  ui.recent.hidden = false;
}

/* --------------------------------------------------------------- requests */

async function analyze(text) {
  return post("/api/analyze", { text, prefer: ui.prefer.value });
}

async function post(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "request failed");
  return data;
}

function mixtureDetail(mixture) {
  const shares = mixture.shares
    .map((s) => `${s.language} ${s.percent}%`)
    .join(", ");
  const shared = mixture.shared === 1
    ? "1 word belongs to more than one dictionary."
    : `${mixture.shared} words belong to more than one dictionary.`;
  return `${shares} across ${mixture.total} tokens. ${shared}`;
}

async function generate() {
  if (busy) return;
  clearOutput();
  setBusy(true);
  try {
    const { text } = await post("/api/sample", { prefer: ui.prefer.value });
    ui.text.value = text;
  } catch (error) {
    showError(failureMessage(error));
    return;
  } finally {
    setBusy(false);
  }
  await run("translate");
}

function failureMessage(error) {
  return error instanceof TypeError
    ? "That request didn't go through. Try again in a moment."
    : error.message;
}

async function run(mode) {
  if (busy) return;
  const text = ui.text.value.trim();
  clearOutput();

  if (!text) {
    showError("Enter some text first.");
    return;
  }

  setBusy(true);
  try {
    const data = await analyze(text);

    if (mode === "detect") {
      renderResult("LANGUAGE", data.mixture.label, mixtureDetail(data.mixture));
      renderRecent("Detected", text, data.mixture.dominant);
    } else {
      const notes = data.translation.notes.length
        ? ` ${data.translation.notes.join(". ")}.`
        : "";
      renderResult(
        "TRANSLATION \u2014 ENGLISH",
        data.translation.english,
        `From ${data.mixture.label} into English.${notes}`,
      );
      renderRecent("English", text, data.translation.english);
    }

    renderReadings(data.readings);
    renderAnalysis(data);
  } catch (error) {
    showError(failureMessage(error));
  } finally {
    setBusy(false);
  }
}

/* ----------------------------------------------------------------- events */

ui.generate.addEventListener("click", generate);
ui.detect.addEventListener("click", () => run("detect"));
ui.translate.addEventListener("click", () => run("translate"));

ui.treeToggle.addEventListener("click", () => {
  const open = ui.tree.hidden;
  ui.tree.hidden = !open;
  ui.treeToggle.textContent = open ? "Hide parse tree" : "Show parse tree";
  ui.treeToggle.setAttribute("aria-expanded", String(open));
});

ui.text.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    run("translate");
  }
});
