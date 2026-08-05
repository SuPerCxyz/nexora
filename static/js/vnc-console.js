import RFB from "/static/vendor/novnc/core/rfb.js";

const shell = document.querySelector("[data-vnc-console-id]");
const screen = document.querySelector("[data-vnc-screen]");
const status = document.querySelector("[data-vnc-status]");
if (shell && screen && status) {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  const url = `${scheme}://${location.host}/ws/consoles/${shell.dataset.vncConsoleId}`;
  const rfb = new RFB(screen, url, {
    shared: false,
    wsProtocols: ["binary", `nexora.token.${shell.dataset.vncConsoleToken}`]
  });
  delete shell.dataset.vncConsoleToken;
  rfb.scaleViewport = true;
  rfb.focusOnClick = true;

  rfb.addEventListener("connect", () => {
    status.textContent = "已连接";
    status.className = "badge bg-green-lt";
  });
  rfb.addEventListener("disconnect", () => {
    status.textContent = "已断开";
    status.className = "badge bg-secondary-lt";
  });
  rfb.addEventListener("securityfailure", () => {
    status.textContent = "认证失败";
    status.className = "badge bg-red-lt";
  });
  document.querySelector("[data-vnc-cad]")?.addEventListener("click", () => {
    rfb.sendCtrlAltDel();
  });
  document.querySelector("[data-vnc-fullscreen]")?.addEventListener("click", () => {
    shell.requestFullscreen();
  });
  document.querySelector("[data-vnc-paste]")?.addEventListener("click", () => {
    const input = document.querySelector("#vnc-clipboard");
    if (input instanceof HTMLInputElement) rfb.clipboardPasteFrom(input.value);
  });
}
