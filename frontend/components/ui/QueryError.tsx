import Link from "next/link";
import { ApiError } from "@/lib/query-client";

export function QueryError({ error, retry }: { error: Error | null; retry: () => unknown }) {
  if (!error) return null;
  return <div role="alert" className="mb-4 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
    {error.message} {error instanceof ApiError && error.status === 401
      ? <Link className="ml-2 underline" href="/login">Sign in</Link>
      : <button className="ml-2 underline" onClick={() => void retry()}>Retry</button>}
  </div>;
}
