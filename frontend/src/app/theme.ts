import { theme as antdTheme } from "antd";
import type { ThemeConfig } from "antd";

import { darkDesignTokens, designTokens } from "./designTokens";

export const technicalFontFamily = 'ui-monospace, SFMono-Regular, "Cascadia Code", "JetBrains Mono", Menlo, Monaco, Consolas, "Liberation Mono", "Noto Sans Mono", monospace';

export type ThemeMode = "light" | "dark";

export const THEME_STORAGE_KEY = "nexora-theme";

export function resolveThemeMode(): ThemeMode {
  try {
    const saved = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (saved === "light" || saved === "dark") return saved;
    if (window.matchMedia?.("(prefers-color-scheme: dark)").matches) return "dark";
  } catch {
    // Storage may be unavailable in hardened or private browsing contexts.
  }
  return "light";
}

export function createNexoraTheme(mode: ThemeMode): ThemeConfig {
  const tokens = mode === "dark" ? darkDesignTokens : designTokens;
  return {
  algorithm: mode === "dark" ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
  token: {
    colorPrimary: tokens.primary,
    colorSuccess: tokens.success,
    colorWarning: tokens.warning,
    colorError: tokens.danger,
    colorInfo: tokens.info,
    colorBgLayout: tokens.backgroundApp,
    colorBgContainer: tokens.backgroundCard,
    colorBorder: tokens.border,
    colorText: tokens.textPrimary,
    colorTextSecondary: tokens.textSecondary,
    colorTextDisabled: tokens.textDisabled,
    colorLink: tokens.textLink,
    borderRadius: 8,
    controlHeight: 32,
    fontSize: 14,
    boxShadow: "none",
    boxShadowSecondary: "none",
    motion: false,
  },
  components: {
    Button: { primaryShadow: "none", dangerShadow: "none" },
    Card: { bodyPadding: 16, headerHeight: 44, headerBg: tokens.backgroundCard },
    Drawer: { colorBgElevated: tokens.backgroundCard },
    Input: { activeBorderColor: tokens.primary, hoverBorderColor: tokens.primary },
    Menu: {
      itemHeight: 48,
      itemHoverBg: tokens.backgroundHover,
      itemSelectedBg: tokens.backgroundSelected,
      itemSelectedColor: tokens.primary,
    },
    Table: {
      borderColor: tokens.border,
      cellPaddingBlock: 10,
      cellPaddingInline: 12,
      headerBg: tokens.backgroundHover,
      headerColor: tokens.textPrimary,
      rowHoverBg: tokens.backgroundHover,
    },
  },
  };
}

export const nexoraTheme = createNexoraTheme("light");
