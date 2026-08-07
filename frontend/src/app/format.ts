export function formatBytes(value: number | null, options?: { fixedUnit?: "GiB" }): string {
  if (value === null || value === undefined) return "—";
  if (options?.fixedUnit === "GiB") {
    const gibibytes = value / 1024 ** 3;
    return `${gibibytes.toLocaleString("zh-CN", { maximumFractionDigits: gibibytes >= 10 ? 0 : 1 })} GiB`;
  }
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)} GiB`;
  if (value >= 1024 ** 2) return `${(value / 1024 ** 2).toFixed(1)} MiB`;
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KiB`;
  return `${value} B`;
}
