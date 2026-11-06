import { Button } from "./Button.jsx";
import { useTheme } from "./useTheme.js";

export default function Card({ title, ...rest }) {
  const theme = useTheme();
  return <Button label={title} onClick={() => {}} {...rest} />;
}
