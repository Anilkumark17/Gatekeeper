import { createContext } from "react";

export const ThemeContext = createContext("light");

export function ThemeProvider({ children }) {
  return <ThemeContext.Provider value="dark">{children}</ThemeContext.Provider>;
}
