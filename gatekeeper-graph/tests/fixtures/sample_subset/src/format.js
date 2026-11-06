import { APP_NAME } from "./constants.js";

export function formatMoney(amount) {
  return `${APP_NAME}: $${amount.toFixed(2)}`;
}
