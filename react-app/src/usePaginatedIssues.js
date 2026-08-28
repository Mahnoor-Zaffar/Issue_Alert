import { useState, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchIssues, fetchPriorityIssues, fetchGeneralIssues } from "./api";

export const PAGE_SIZE = 30;

function buildParams(filters) {
  const params = { limit: PAGE_SIZE, hide_old_unclaimed: true };
  if (filters.filterLang) params.language = filters.filterLang;
  if (filters.filterStatus) params.status = filters.filterStatus;
  if (filters.filterDiff) params.difficulty = filters.filterDiff;
  if (filters.filterLabel) params.label = filters.filterLabel;
  if (filters.filterSaved) params.bookmarked_only = "true";
  if (filters.filterClaimed) params.claimed_only = "true";
  if (filters.filterBounty) params.bounty_only = "true";
  return params;
}

function pickFetcher(isPriority) {
  if (isPriority === true) return fetchPriorityIssues;
  if (isPriority === false) return fetchGeneralIssues;
  return fetchIssues;
}

export function usePaginatedIssues(filters, isPriority = undefined) {
  const [page, setPage] = useState(0);
  const prevFilterKey = useRef(JSON.stringify(filters));

  // Reset to page 0 whenever server-side filters change (during render, per React docs).
  const filterKey = JSON.stringify(filters);
  if (prevFilterKey.current !== filterKey) {
    prevFilterKey.current = filterKey;
    setPage(0);
  }

  const fetcher = pickFetcher(isPriority);

  const query = useQuery({
    queryKey: ["issues", isPriority, page, filterKey],
    queryFn: () => fetcher({ ...buildParams(filters), offset: page * PAGE_SIZE }),
    placeholderData: (prev) => prev,
  });

  const issues = query.data?.issues || [];
  const hasNextPage = issues.length >= PAGE_SIZE;

  return {
    ...query,
    issues,
    page,
    setPage,
    hasNextPage,
    isFetchingPage: Boolean(query.isFetching || query.isPlaceholderData),
  };
}