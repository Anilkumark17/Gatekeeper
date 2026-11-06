import { TAX_RATE } from "./constants.js";
import { add, applyTax } from "./math.js";
import { formatMoney } from "./format.js";
import { titleCase } from "./utils/index.js";

export function checkout(label, prices) {
  const subtotal = prices.reduce((sum, price) => add(sum, price), 0);
  const total = applyTax(subtotal, TAX_RATE);
  return formatMoney(total) + " " + titleCase(label);
}

const loadExtra = () => import("./math.js");

console.log(checkout("daily total", [10, 5, 2.5]));

void loadExtra;
