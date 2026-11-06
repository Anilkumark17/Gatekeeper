# sample-js inventory

Read-only walk of `sample-js` on 2026-11-06. Skipped directory names (`node_modules`, `dist`, `build`, `.git`, `coverage`, `.next`, `out`) were not present. Nothing under `sample-js` was created, edited, or deleted.

## Counts

- `.js` files: 6
- `.jsx` files: 0

## Source folders

```text
src/
  constants.js
  format.js
  main.js
  math.js
  utils/
    index.js
    string.js
```

Non-source files at the repo root: `package.json`, `jsconfig.json`.

## Module system

ESM. `package.json` sets `"type": "module"`. Every `.js` file uses `import` or `export`. No file contains `require(` or `module.exports`.

## jsconfig.json

Present at `jsconfig.json`.

- `compilerOptions.baseUrl`: `"."`
- `compilerOptions.paths`: `"@app/*"` maps to `["src/*"]`

No source file imports `@app/*`. Imports that exist are relative.

## Barrel files

- `src/utils/index.js:1` re-exports `titleCase` from `./string.js`.

## React code

None. No `.jsx` file. No file contains JSX, `React`, a PascalCase component, or a function whose name matches `use[A-Z]`.

## Parser patterns

Each line below was read from the file. Missing patterns are absent from this repo.

| Pattern | Example |
| --- | --- |
| Named export | `src/constants.js:1` `export const TAX_RATE = 0.08;` |
| Default export | Missing. No `export default`. |
| Function declaration | `src/math.js:1` `export function add(a, b)`. Not a component. |
| Arrow function | `src/math.js:9` `export const multiply = (a, b) => a * b`. Not a component. |
| Arrow function component | Missing. No PascalCase component. |
| Function component | Missing. No PascalCase component. |
| Class component | Missing. No `class` declaration. |
| Props destructuring | Missing. No JSX props. |
| Props spread `{...rest}` | Missing. |
| Dynamic `import()` | `src/main.js:12` `const loadExtra = () => import("./math.js");` |
| `React.lazy` | Missing. |
| `Context.Provider` | Missing. |
| `useContext` | Missing. |
| Custom hook | Missing. No `use[A-Z]` declaration. |
| Test file | Missing. No `*.test.js` or `*.spec.js`. |

Other named exports read from the tree:

- `src/constants.js:2` `export const APP_NAME = "Till";`
- `src/math.js:4` `export function applyTax(amount, rate)`
- `src/format.js:1` `import { APP_NAME } from "./constants.js";`
- `src/format.js:3` `export function formatMoney(amount)`
- `src/utils/string.js:1` `export function titleCase(value)`
- `src/main.js:1` `import { TAX_RATE } from "./constants.js";`
- `src/main.js:2` `import { add, applyTax } from "./math.js";`
- `src/main.js:3` `import { formatMoney } from "./format.js";`
- `src/main.js:4` `import { titleCase } from "./utils/index.js";`
- `src/main.js:6` `export function checkout(label, prices)`

`checkout` calls `add` (`src/main.js:7`), `applyTax` (`src/main.js:8`), `formatMoney` and `titleCase` (`src/main.js:9`).

## Subset

`tests/fixtures/sample_subset/` is a full copy of the sample-js source tree. Relative paths are preserved.

- `jsconfig.json`
- `package.json`
- `src/constants.js`
- `src/format.js`
- `src/main.js`
- `src/math.js`
- `src/utils/index.js`
- `src/utils/string.js`

Not present in this repo:

- A parent component rendering a child component with named props.
- A custom hook or context.
- An external package import. `package.json` has no `dependencies`. Every import specifier is relative.
