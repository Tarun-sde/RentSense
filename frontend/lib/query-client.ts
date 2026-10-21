import { QueryClient, queryOptions } from "@tanstack/react-query";

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

export function createQueryClient() {
  return new QueryClient({ defaultOptions: { queries: {
    staleTime: 30_000, gcTime: 10 * 60_000,
    retry: (count, error) => count < 1 && (!(error instanceof ApiError) || error.status >= 500),
    refetchOnWindowFocus: false,
  }, mutations: { retry: false } } });
}

let browserClient: QueryClient | undefined;
export function getQueryClient() {
  if (typeof window === "undefined") return createQueryClient();
  return browserClient ??= createQueryClient();
}

export function apiQuery<T>(path: string) {
  return queryOptions({
    queryKey: ["api", path],
    staleTime: /^\/(sites|operators|chat\/status)(\?|$)/.test(path) ? 300_000
      : path.startsWith("/forecasts") ? 300_000 : 30_000,
    queryFn: async ({ signal }): Promise<T> => {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || ""}/api/v1${path}`, {
        credentials: "include", cache: "no-store", signal: AbortSignal.any([signal, AbortSignal.timeout(20_000)]),
      });
      if (!res.ok) throw new ApiError(res.status === 404 ? "NOT_FOUND"
        : res.status === 401 ? "Your session has expired. Please sign in again."
        : `Unable to load data (${res.status}). Please retry.`, res.status);
      return res.json();
    },
  });
}

export async function invalidateOperationalData() {
  const client = getQueryClient();
  const filters = { predicate: (query: { queryKey: readonly unknown[] }) =>
    query.queryKey[0] === "api" && !/^\/(sites|operators|chat\/status)(\?|$)/.test(String(query.queryKey[1])) };
  // Cancel older reads before marking data stale, so pre-mutation results cannot win.
  await client.cancelQueries(filters);
  await client.invalidateQueries(filters);
}
