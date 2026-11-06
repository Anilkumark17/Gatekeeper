import { useContext } from "react";
import { ThemeContext } from "./ThemeContext.jsx";

export function useTheme() {
  return useContext(ThemeContext);
}
