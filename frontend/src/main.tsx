import { createRoot } from "react-dom/client";

import { App } from "./app/App";

const root = document.getElementById("nexora-root");
if (!root) throw new Error("Nexora root element is missing");

const nonce = document.querySelector<HTMLMetaElement>('meta[name="csp-nonce"]')?.content;
if (!nonce) throw new Error("CSP nonce is missing");

createRoot(root).render(<App nonce={nonce} />);
