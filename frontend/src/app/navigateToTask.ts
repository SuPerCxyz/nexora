export function navigateToTask(location: string): void {
  const currentPath = window.location.pathname + window.location.search;
  if (!currentPath.startsWith("/tasks")) {
    sessionStorage.setItem("nexora-return-to", currentPath);
  }
  window.location.assign(location);
}
