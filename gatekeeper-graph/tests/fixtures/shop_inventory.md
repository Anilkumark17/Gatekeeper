# Shop fixture

Byte copy of `sample-js` (`.js` and `.json` only). SHA-256 of `sample-js` matched the copy and was unchanged after the copy.

| Path | SHA-256 |
| --- | --- |
| `jsconfig.json` | `843dd735f4d16ad415746b79bf7b4894861dd3432f47aa595b0ea53c1a923e29` |
| `package.json` | `8d7ff955dc7a12834bc6b931d9075dcce36769898e7a568ce39bc4454dad5be6` |
| `src/constants.js` | `98f00b981b1ae38475059b028f74816926c09cf197211073de43e05e79586140` |
| `src/customer.js` | `f727f221a3b413b9ff3e76b901c7626e81d4a5065d32d74c0986b1d05d4e043a` |
| `src/format.js` | `ef26d753dc450f9b8ece1c01891abf84d64daebf262786e5999cd7652be8fb35` |
| `src/kmp.js` | `8da0ed597a13a5dd2a48c9fbff2a806a87c9af8ed99d1ea12b70a1e023828c4d` |
| `src/main.js` | `da132f214c83116ec4546f230480c53d7077f6a3e3066370d41af9703785856c` |
| `src/math.js` | `e275d11ed7930e603d7524a4f13bd01a8e8160b9eaabbe362d0547e9c4fdc2ff` |
| `src/receipt.js` | `58c3adfc881dce39b4ddc475df61a67017b2b4bfa5d802a1c4dbf51d331adb83` |
| `src/summary.js` | `19cc0ef0bfc3ec473db1c7fda4046ff7b9e97f6cab4238730cc14e981ee16af4` |
| `src/utils/index.js` | `3e75c5a3672b755f5c7c2941f446282f8b50dad1749e2c5b8db6a768b054d0fb` |
| `src/utils/join.js` | `90bcc3c35a7bd2ae0897cfc505794620da2f3137bcc80a324c0000e45dcdb74d` |
| `src/utils/string.js` | `6a2fe138ada406bf0a0262acd8ad7eed3a23ea966bcde9fde4e8edba5d332b09` |

## Symbols

- `src/constants.js:1` `TAX_RATE` constant, lines 1-1
- `src/constants.js:2` `DISCOUNT_RATE` constant, lines 2-2
- `src/constants.js:3` `APP_NAME` constant, lines 3-3
- `src/customer.js:1` `CUSTOMER` constant, lines 1-1
- `src/customer.js:3` `greet` function, lines 3-5
- `src/format.js:3` `formatMoney` function, lines 3-5
- `src/kmp.js:2` `kmp` function, lines 2-14
- `src/main.js:8` `checkout` function, lines 8-13
- `src/main.js:15` `ITEMS` constant, lines 15-19
- `src/main.js:21` `loadExtra` function, lines 21-21
- `src/math.js:1` `add` function, lines 1-3
- `src/math.js:5` `applyTax` function, lines 5-7
- `src/math.js:9` `applyDiscount` function, lines 9-11
- `src/math.js:13` `multiply` function, lines 13-13
- `src/receipt.js:3` `lineFor` function, lines 3-5
- `src/receipt.js:7` `receiptLines` function, lines 7-9
- `src/summary.js:4` `itemCount` function, lines 4-6
- `src/summary.js:8` `header` function, lines 8-10
- `src/utils/join.js:1` `joinLines` function, lines 1-3
- `src/utils/string.js:1` `titleCase` function, lines 1-3

`src/utils/index.js:1` re-exports `joinLines`. `src/utils/index.js:2` re-exports `titleCase`. No local symbol.
`src/kmp.js:1` is the bare name `ReadableStreamDefaultController`, not a symbol.

## Imports

- `src/format.js:1` `APP_NAME` from `./constants.js`
- `src/main.js:1` `DISCOUNT_RATE`, `TAX_RATE` from `./constants.js`
- `src/main.js:2` `add`, `applyDiscount`, `applyTax` from `./math.js`
- `src/main.js:3` `formatMoney` from `./format.js`
- `src/main.js:4` `receiptLines` from `./receipt.js`
- `src/main.js:5` `header` from `./summary.js`
- `src/main.js:6` `joinLines`, `titleCase` from `./utils/index.js`
- `src/main.js:21` dynamic import of `./math.js`
- `src/receipt.js:1` `titleCase` from `./utils/index.js`
- `src/summary.js:1` `CUSTOMER`, `greet` from `./customer.js`
- `src/summary.js:2` `titleCase` from `./utils/index.js`
- `src/utils/index.js:1` `joinLines` from `./join.js`
- `src/utils/index.js:2` `titleCase` from `./string.js`

## Calls

- `src/format.js:4` `formatMoney` calls `toFixed`
- `src/kmp.js:3` `kmp` calls `getPrefix`
- `src/main.js:9` `checkout` calls `reduce` and `add`
- `src/main.js:10` `checkout` calls `applyDiscount`
- `src/main.js:11` `checkout` calls `applyTax`
- `src/main.js:12` `checkout` calls `formatMoney` and `titleCase`
- `src/main.js:23` file calls `header` and `log`
- `src/main.js:24` file calls `joinLines` and `receiptLines`
- `src/main.js:26` file calls `checkout`, `map`, and `log`
- `src/receipt.js:4` `lineFor` calls `titleCase` and `toFixed`
- `src/receipt.js:8` `receiptLines` calls `map`
- `src/summary.js:9` `header` calls `greet`, `titleCase`, and `itemCount`
- `src/utils/join.js:2` `joinLines` calls `join`
- `src/utils/string.js:2` `titleCase` calls `replace` and `toUpperCase`

## Constant reads inside a function

- `src/main.js:10` `checkout` reads `DISCOUNT_RATE`
- `src/main.js:11` `checkout` reads `TAX_RATE`
- `src/format.js:4` `formatMoney` reads `APP_NAME`
- `src/summary.js:9` `header` reads `CUSTOMER`

## Callbacks

- `src/main.js:9` arrow passed to `reduce`
- `src/main.js:26` arrow passed to `map`
- `src/receipt.js:8` `lineFor` passed to `map`
- `src/utils/string.js:2` arrow passed to `replace`
