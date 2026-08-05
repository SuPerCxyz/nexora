document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-copy-target]");
  if (!button) return;
  const target = document.getElementById(button.dataset.copyTarget);
  if (!target) return;
  try {
    await navigator.clipboard.writeText(target.textContent || "");
    const original = button.textContent;
    button.textContent = "已复制";
    window.setTimeout(() => {
      button.textContent = original;
    }, 1200);
  } catch (_error) {
    button.textContent = "复制失败";
  }
});

document.querySelectorAll("[data-code-language]").forEach((code) => {
  const language = code.dataset.codeLanguage;
  const content = code.textContent || "";
  const fragment = document.createDocumentFragment();
  content.split("\n").forEach((line, index, lines) => {
    const row = document.createElement("span");
    row.className = "nx-code-line";
    const marker = document.createElement("span");
    marker.className = "nx-code-marker";
    marker.textContent = String(index + 1);
    const text = document.createElement("span");
    text.className = language === "diff" ? diffClass(line) : xmlClass(line);
    text.textContent = line;
    row.append(marker, text);
    fragment.append(row);
    if (index < lines.length - 1) fragment.append(document.createTextNode("\n"));
  });
  code.replaceChildren(fragment);
});

function diffClass(line) {
  if (line.startsWith("+")) return "nx-code-added";
  if (line.startsWith("-")) return "nx-code-removed";
  if (line.startsWith("@@")) return "nx-code-location";
  return "";
}

function xmlClass(line) {
  const trimmed = line.trimStart();
  if (trimmed.startsWith("<!--")) return "nx-code-comment";
  if (trimmed.startsWith("<")) return "nx-code-tag";
  return "";
}
