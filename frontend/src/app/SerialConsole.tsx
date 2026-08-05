import { useEffect, useRef, useState } from "react";
import { FitAddon } from "@xterm/addon-fit";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";

import type { ConsoleCredential } from "../api/consoles";
import { StatusTag } from "./StatusTag";
import { technicalFontFamily } from "./theme";

export function SerialConsole({ credential }: { credential: ConsoleCredential }) {
  const target = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState("connecting");
  useEffect(() => {
    if (!target.current) return;
    const styles = getComputedStyle(document.documentElement);
    const terminal = new Terminal({
      cursorBlink: true,
      convertEol: true,
      fontFamily: technicalFontFamily,
      fontSize: 14,
      theme: {
        background: styles.getPropertyValue("--console-background").trim(),
        foreground: styles.getPropertyValue("--console-foreground").trim(),
        cursor: styles.getPropertyValue("--console-cursor").trim(),
      },
    });
    const fit = new FitAddon();
    terminal.loadAddon(fit);
    terminal.open(target.current);
    fit.fit();
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(
      `${scheme}://${location.host}/ws/consoles/${credential.session_id}`,
      ["nexora.console", `nexora.token.${credential.token}`],
    );
    socket.binaryType = "arraybuffer";
    socket.addEventListener("open", () => setStatus("connected"));
    socket.addEventListener("message", (event) => terminal.write(event.data instanceof ArrayBuffer ? new Uint8Array(event.data) : event.data));
    socket.addEventListener("close", () => {
      setStatus("closed");
      terminal.write("\r\n\x1b[33m控制台会话已关闭。\x1b[0m\r\n");
    });
    socket.addEventListener("error", () => setStatus("error"));
    const input = terminal.onData((value) => { if (socket.readyState === WebSocket.OPEN) socket.send(value); });
    const resize = () => fit.fit();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      input.dispose();
      socket.close();
      terminal.dispose();
    };
  }, [credential]);
  return <div className="nx-console-panel">
    <div className="nx-console-status"><span className="nx-technical">{credential.vm_uuid}</span><ConsoleStatus value={status} /></div>
    <div ref={target} className="nx-serial-terminal" aria-label="虚拟机串口控制台" />
  </div>;
}

export function ConsoleStatus({ value }: { value: string }) {
  const labels = { connecting: "正在连接", connected: "已连接", closed: "已断开", error: "连接失败" } as Record<string, string>;
  return <StatusTag label={labels[value] ?? value} tone={value === "connected" ? "running" : value === "error" ? "error" : value === "connecting" ? "starting" : "stopped"} />;
}
