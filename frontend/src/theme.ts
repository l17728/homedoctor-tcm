import { theme, type ThemeConfig } from 'antd';

const cjkFontFamily =
  "'PingFang SC', 'Microsoft YaHei', 'Noto Sans SC', sans-serif";

export const lightTheme: ThemeConfig = {
  token: {
    colorPrimary: '#2ba471',
    borderRadius: 8,
    fontSize: 16,
    fontFamily: cjkFontFamily,
  },
};

export const darkTheme: ThemeConfig = {
  token: {
    colorPrimary: '#2ba471',
    borderRadius: 8,
    fontSize: 16,
    fontFamily: cjkFontFamily,
  },
  algorithm: theme.darkAlgorithm,
};
