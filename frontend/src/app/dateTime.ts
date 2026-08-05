const defaultTimeZone = "Asia/Shanghai";

let administratorTimeZone = defaultTimeZone;

export function configureTimeZone(timeZone: string) {
  try {
    new Intl.DateTimeFormat("zh-CN", { timeZone }).format();
    administratorTimeZone = timeZone;
  } catch {
    administratorTimeZone = defaultTimeZone;
  }
}

export function formatDateTime(
  value: string | null,
  options: Intl.DateTimeFormatOptions = { dateStyle: "medium", timeStyle: "short" },
  emptyValue = "—",
) {
  if (!value) return emptyValue;
  return new Intl.DateTimeFormat("zh-CN", {
    ...options,
    timeZone: administratorTimeZone,
  }).format(parseUtcDate(value));
}

function parseUtcDate(value: string) {
  const hasOffset = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value);
  return new Date(hasOffset ? value : `${value}Z`);
}
