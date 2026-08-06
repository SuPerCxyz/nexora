import type { ThemeConfig } from "antd";

import { designTokens } from "./designTokens";

export const technicalFontFamily = 'ui-monospace, SFMono-Regular, "Cascadia Code", "JetBrains Mono", Menlo, Monaco, Consolas, "Liberation Mono", "Noto Sans Mono", monospace';

export const nexoraTheme: ThemeConfig = {
  token: {
    colorPrimary: designTokens.primary,
    colorSuccess: designTokens.success,
    colorWarning: designTokens.warning,
    colorError: designTokens.danger,
    colorInfo: designTokens.info,
    colorBgLayout: designTokens.backgroundApp,
    colorBgContainer: designTokens.backgroundCard,
    colorBorder: designTokens.border,
    colorText: designTokens.textPrimary,
    colorTextSecondary: designTokens.textSecondary,
    colorTextDisabled: designTokens.textDisabled,
    colorLink: designTokens.textLink,
    borderRadius: 8,
    controlHeight: 32,
    fontSize: 14,
    boxShadow: "none",
    boxShadowSecondary: "none",
    motion: false,
  },
  components: {
    Button: { primaryShadow: "none", dangerShadow: "none" },
    Card: { bodyPadding: 16, headerHeight: 44, headerBg: designTokens.backgroundCard },
    Drawer: { colorBgElevated: designTokens.backgroundCard },
    Input: { activeBorderColor: designTokens.primary, hoverBorderColor: designTokens.primary },
    Menu: {
      itemHeight: 48,
      itemHoverBg: designTokens.backgroundHover,
      itemSelectedBg: designTokens.backgroundSelected,
      itemSelectedColor: designTokens.primary,
    },
    Table: {
      borderColor: designTokens.border,
      cellPaddingBlock: 10,
      cellPaddingInline: 12,
      headerBg: designTokens.backgroundHover,
      headerColor: designTokens.textPrimary,
      rowHoverBg: designTokens.backgroundHover,
    },
  },
};
