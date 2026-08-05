import RFB from "@novnc/novnc";
import { Button, Input, Space } from "antd";
import { useEffect, useRef, useState } from "react";

import type { ConsoleCredential } from "../api/consoles";
import { ConsoleStatus } from "./SerialConsole";

export function VncConsole({ credential }: { credential: ConsoleCredential }) {
  const shell = useRef<HTMLDivElement>(null);
  const screen = useRef<HTMLDivElement>(null);
  const rfb = useRef<RFB | null>(null);
  const [status, setStatus] = useState("connecting");
  const [clipboard, setClipboard] = useState("");
  useEffect(() => {
    if (!screen.current) return;
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const connection = new RFB(
      screen.current,
      `${scheme}://${location.host}/ws/consoles/${credential.session_id}`,
      { shared: false, wsProtocols: ["binary", `nexora.token.${credential.token}`] },
    );
    connection.scaleViewport = true;
    connection.focusOnClick = true;
    connection.addEventListener("connect", () => setStatus("connected"));
    connection.addEventListener("disconnect", () => setStatus("closed"));
    connection.addEventListener("securityfailure", () => setStatus("error"));
    rfb.current = connection;
    return () => { connection.disconnect(); rfb.current = null; };
  }, [credential]);
  return <div ref={shell} className="nx-console-panel">
    <div className="nx-console-status"><span className="nx-technical">{credential.vm_uuid}</span><ConsoleStatus value={status} /></div>
    <Space wrap className="nx-console-toolbar">
      <Button className="nx-btn-info" onClick={() => rfb.current?.sendCtrlAltDel()}>Ctrl-Alt-Delete</Button>
      <Button className="nx-btn-info" onClick={() => shell.current?.requestFullscreen()}>全屏</Button>
      <Input aria-label="剪贴板文本" maxLength={4096} placeholder="粘贴文本到客户机" value={clipboard} onChange={(event) => setClipboard(event.target.value)} className="nx-console-clipboard" />
      <Button className="nx-btn-info" onClick={() => rfb.current?.clipboardPasteFrom(clipboard)}>发送剪贴板</Button>
    </Space>
    <div ref={screen} className="nx-vnc-screen" aria-label="虚拟机 VNC 控制台" />
  </div>;
}
