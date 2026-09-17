import { Card, Tooltip } from "antd";
import type { ReactNode } from "react";

export function FactCard({ label, value, technical }: { label: string; value: ReactNode; technical?: boolean }) {
  const content = <strong className={technical ? "nx-technical" : ""}>{value}</strong>;
  const fullValue = technical && (typeof value === "string" || typeof value === "number") ? String(value) : null;
  return (
    <Card size="small" className="nx-fact-card">
      <span>{label}</span>
      {fullValue ? <Tooltip title={fullValue}>{content}</Tooltip> : content}
    </Card>
  );
}
