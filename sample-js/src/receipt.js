import { titleCase } from "./utils/index.js";

export function lineFor(item) {
  return titleCase(item.name) + " " + item.price.toFixed(2);
}

export function receiptLines(items) {
  return items.map(lineFor);
}
