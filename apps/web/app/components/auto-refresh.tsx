"use client";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

// Re-render the server page while a job is in progress; stops after 30 minutes.
export function AutoRefresh({ seconds = 15 }: { seconds?: number }) {
  const router = useRouter();
  useEffect(() => {
    const started = Date.now();
    const timer = setInterval(() => {
      if (Date.now() - started > 30 * 60 * 1000) clearInterval(timer);
      else router.refresh();
    }, seconds * 1000);
    return () => clearInterval(timer);
  }, [router, seconds]);
  return null;
}
