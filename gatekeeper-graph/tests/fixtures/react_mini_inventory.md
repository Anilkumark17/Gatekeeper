# react_mini inventory

Read from `tests/fixtures/react_mini` after the files were written. Line numbers are the file lines.

## Top-level symbols

- `src/ThemeContext.jsx:3` `ThemeContext` CONSTANT, lines 3-3. `export const ThemeContext = createContext("light");`
- `src/ThemeContext.jsx:5` `ThemeProvider` COMPONENT, lines 5-7.
- `src/useTheme.js:4` `useTheme` HOOK, lines 4-6.
- `src/Button.jsx:1` `Button` COMPONENT, lines 1-3.
- `src/Card.jsx:4` `Card` COMPONENT, lines 4-7. Default export.
- `src/App.jsx:5` `Lazy` COMPONENT, lines 5-5. `const Lazy = React.lazy(() => import("./Card.jsx"));`
- `src/App.jsx:7` `App` COMPONENT, lines 7-13. Default export.
- `src/App.jsx:15` `Legacy` COMPONENT, lines 15-19. `class Legacy extends React.Component`.

`describe` and `it` are test blocks, not symbols.

## Imports

- `src/ThemeContext.jsx:1` named `createContext` from `"react"`.
- `src/useTheme.js:1` named `useContext` from `"react"`.
- `src/useTheme.js:2` named `ThemeContext` from `"./ThemeContext.jsx"`.
- `src/Card.jsx:1` named `Button` from `"./Button.jsx"`.
- `src/Card.jsx:2` named `useTheme` from `"./useTheme.js"`.
- `src/App.jsx:1` named `ThemeProvider` from `"./ThemeContext.jsx"`.
- `src/App.jsx:2` default `Card` from `"./Card.jsx"`.
- `src/App.jsx:3` default `React` from `"react"`.
- `src/Button.test.jsx:1` named `describe`, `it`, `expect` from `"vitest"`.
- `src/Button.test.jsx:2` named `Button` from `"./Button.jsx"`.

## Exports

- `src/ThemeContext.jsx:3` named `ThemeContext`.
- `src/ThemeContext.jsx:5` named `ThemeProvider`.
- `src/useTheme.js:4` named `useTheme`.
- `src/Button.jsx:1` named `Button`.
- `src/Card.jsx:4` default `Card`.
- `src/App.jsx:7` default `App`.

`Lazy` and `Legacy` are not exported.

## Calls

- `src/ThemeContext.jsx:3` owner `ThemeContext`, callee `createContext`.
- `src/useTheme.js:5` owner `useTheme`, callee `useContext`.
- `src/Card.jsx:5` owner `Card`, callee `useTheme`.
- `src/App.jsx:5` owner `Lazy`, callee `React.lazy`.
- `src/Button.test.jsx:4` owner file, callee `describe`.
- `src/Button.test.jsx:5` owner file, callee `it`.
- `src/Button.test.jsx:6` owner file, callee `expect`.

## Hook calls

- `src/useTheme.js:5` `useContext`.
- `src/Card.jsx:5` `useTheme`.

## useContext reads

- `src/useTheme.js:5` context `ThemeContext`.

## Component JSX

- `src/ThemeContext.jsx:6` owner `ThemeProvider`, tag `ThemeContext.Provider`, props `value`, spread no, provider yes.
- `src/Card.jsx:6` owner `Card`, tag `Button`, props `label`, `onClick`, spread yes, provider no.
- `src/App.jsx:9` owner `App`, tag `ThemeProvider`, props none, spread no, provider no.
- `src/App.jsx:10` owner `App`, tag `Card`, props `title`, spread no, provider no.

## Lowercase JSX

Listed separately. A later extractor ignores these tags.

- `src/Button.jsx:2` owner `Button`, tag `button`.
- `src/App.jsx:17` owner `Legacy`, tag `div`.

## Dynamic imports

- `src/App.jsx:5` owner `Lazy`, specifier `"./Card.jsx"`, lazy yes.

## Test blocks

- `src/Button.test.jsx:4` `describe` title `Button`.
- `src/Button.test.jsx:5` `it` title `renders a label`.
