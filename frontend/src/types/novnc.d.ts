declare module "@novnc/novnc" {
  export default class RFB extends EventTarget {
    constructor(
      target: HTMLElement,
      url: string,
      options: { shared: boolean; wsProtocols: string[] },
    );
    scaleViewport: boolean;
    focusOnClick: boolean;
    sendCtrlAltDel(): void;
    clipboardPasteFrom(value: string): void;
    disconnect(): void;
  }
}
