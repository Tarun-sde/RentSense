"use client";

import { useQuery } from "@tanstack/react-query";
import { apiQuery } from "./query-client";

export function useApiQuery<T>(path: string, enabled = true) {
  return useQuery({ ...apiQuery<T>(path), enabled });
}
