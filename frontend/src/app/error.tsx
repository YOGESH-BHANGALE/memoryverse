"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/Button";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Global routing error:", error);
  }, [error]);

  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-4">
      <div className="w-20 h-20 rounded-2xl bg-red-500/10 flex items-center justify-center text-4xl mb-6">
        ⚠️
      </div>
      <h2 className="text-2xl font-bold text-white mb-2">
        Something went wrong!
      </h2>
      <p className="text-dark-200 max-w-md mb-8">
        MemoryVerse encountered an unexpected error while rendering this page.
      </p>
      <div className="flex gap-4">
        <Button onClick={() => reset()} variant="primary">
          Try again
        </Button>
        <Button onClick={() => window.location.href = "/"} variant="secondary">
          Go Home
        </Button>
      </div>
    </div>
  );
}
