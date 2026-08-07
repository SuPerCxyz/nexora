import { Card } from "antd";
import type { ReactNode } from "react";

export function FactCard({ label, value, technical }: { label: string; value: ReactNode; technical?: boolean }) {
  return (
    <Card size="small" className="nx-fact-card">
      <span>{label}</span>
      <strong className={technical ? "nx-technical" : ""}>{value}</strong>
    </Card>
  );
}
