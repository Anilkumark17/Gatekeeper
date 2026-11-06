import { ThemeProvider } from "./ThemeContext.jsx";
import Card from "./Card.jsx";
import React from "react";

const Lazy = React.lazy(() => import("./Card.jsx"));

export default function App() {
  return (
    <ThemeProvider>
      <Card title="Hi" />
    </ThemeProvider>
  );
}

class Legacy extends React.Component {
  render() {
    return <div />;
  }
}
