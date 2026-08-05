(() => {
  "use strict";

  const shell = document.querySelector("[data-console-id]");
  const target = document.querySelector("[data-console-terminal]");
  const status = document.querySelector("[data-console-status]");
  if (!shell || !target || !status || !window.Terminal || !window.FitAddon) return;

  const rootStyles = getComputedStyle(document.documentElement);
  const terminal = new window.Terminal({
    cursorBlink: true,
    convertEol: true,
    fontFamily: "ui-monospace, SFMono-Regular, Cascadia Code, monospace",
    fontSize: 14,
    theme: {
      background: rootStyles.getPropertyValue("--console-background").trim(),
      foreground: rootStyles.getPropertyValue("--console-foreground").trim(),
      cursor: rootStyles.getPropertyValue("--console-cursor").trim()
    }
  });
  const fit = new window.FitAddon.FitAddon();
  terminal.loadAddon(fit);
  terminal.open(target);
  fit.fit();

  const scheme = location.protocol === "https:" ? "wss" : "ws";
  const url = `${scheme}://${location.host}/ws/consoles/${shell.dataset.consoleId}`;
  const socket = new WebSocket(url, [
    "nexora.console",
    `nexora.token.${shell.dataset.consoleToken}`
  ]);
  socket.binaryType = "arraybuffer";
  delete shell.dataset.consoleToken;

  socket.addEventListener("open", () => {
    status.textContent = "已连接";
    status.className = "badge bg-green-lt";
  });
  socket.addEventListener("message", (event) => {
    terminal.write(
      event.data instanceof ArrayBuffer ? new Uint8Array(event.data) : event.data
    );
  });
  socket.addEventListener("close", () => {
    status.textContent = "已断开";
    status.className = "badge bg-secondary-lt";
    terminal.write("\r\n\x1b[33m控制台会话已关闭。\x1b[0m\r\n");
  });
  socket.addEventListener("error", () => {
    status.textContent = "连接失败";
    status.className = "badge bg-red-lt";
  });
  terminal.onData((data) => {
    if (socket.readyState === WebSocket.OPEN) socket.send(data);
  });
  window.addEventListener("resize", () => fit.fit());
})();
