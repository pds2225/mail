/** monitor.py FETCHERS 키와 동기화 */
export const COLLECTOR_TYPES = [
  "bizinfo_api",
  "myfair_html",
  "kstartup_html",
  "kita_html",
  "iris_api",
  "smtech_html",
  "kocca_pims",
  "kocca_bbs",
  "gtp_html",
  "gsp_html",
  "ccei_html",
  "nipa_html",
  "mss_html",
  "itp_html",
  "bizok_html",
  "exportvoucher_html",
  "mssmiv_html",
  "keit_html",
  "sba_html",
  "semas_loan_ols",
  "html_table",
  "html_card",
  "pw_keit",
  "pw_kiat",
  "pw_thevc",
  "pw_connectworks",
  "pw_semas",
  "pw_table",
] as const;

export type CollectorType = (typeof COLLECTOR_TYPES)[number];

export const SITE_CATEGORIES = [
  "통합포털",
  "주관기관",
  "전용 API",
  "전용 HTML",
  "지자체/TP",
  "기타",
] as const;

export type SiteRecord = {
  id: string;
  name: string;
  type: string;
  url: string;
  enabled: boolean;
  is_aggregator: boolean;
  note?: string;
  category?: string;
  selectors?: { row?: string };
};

export type SiteAddInput = {
  name: string;
  url: string;
  category: string;
  collectorType: string;
  enabled: boolean;
  isAggregator: boolean;
  note: string;
  testCollect: boolean;
  suggestedId?: string;
};
