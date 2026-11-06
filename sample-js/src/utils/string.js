export function titleCase(value) {
  return value.replace(/\b\w/g, (char) => char.toUpperCase());
}
