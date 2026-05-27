"use client";

import { Button } from "@fluentui/react-components";

export default function GlobalError({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div style={{ padding: 32 }}>
      <h2>Something went wrong</h2>
      <pre style={{ whiteSpace: "pre-wrap", color: "#a00" }}>{error.message}</pre>
      <Button appearance="primary" onClick={reset}>
        Try again
      </Button>
    </div>
  );
}
