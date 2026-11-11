import { DISCOUNT_RATE, TAX_RATE } from "./constants.js";
import { add, applyDiscount, applyTax } from "./math.js";
import { formatMoney } from "./format.js";
import { receiptLines } from "./receipt.js";
import { header } from "./summary.js";
import { joinLines, titleCase } from "./utils/index.js";

export function checkout(label, prices) {
  const subtotal = prices.reduce((sum, price) => add(sum, price), 0);
  const discounted = applyDiscount(subtotal, DISCOUNT_RATE);
  const total = applyTax(discounted, TAX_RATE);
  return formatMoney(total) + " " + titleCase(label);
}

const ITEMS = [
  { name: "coffee", price: 10 },
  { name: "tea", price: 5 },
  { name: "muffin", price: "2.50" },
];

const loadExtra = () => import("./math.js");

console.log(header(ITEMS));
console.log(joinLines(receiptLines(ITEMS)));

console.log(checkout("daily total", ITEMS.map((item) => Number(item.price))));

void loadExtra;
