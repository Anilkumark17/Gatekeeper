import { CUSTOMER, greet } from "./customer.js";
import { titleCase } from "./utils/index.js";

export function itemCount(items) {
  return items.length;
}

export function header(items) {
  return greet(titleCase(CUSTOMER)) + " (" + itemCount(items) + " items)";
}
