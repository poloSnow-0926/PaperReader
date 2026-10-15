export type SourceType = "published" | "preprint" | "tech_report";
export type Vetting = "seed" | "published" | "tech_report" | "cited" | "new" | "unvetted";

export interface Paper {
  id: string;
  title: string;
  authors: string[];
  n_authors: number;
  published: string; // YYYY-MM-DD
  abstract: string;
  category: string;
  secondary_category: string | null;
  tldr: string;
  source: { type: SourceType; venue: string | null; honor: "oral" | "spotlight" | null };
  citations: number | null;
  influential_citations: number | null;
  citations_per_month: number | null;
  url: string;
  vetting: Vetting;
}

export interface Dataset {
  generated_at: string;
  categories: Record<string, string>;
  papers: Paper[];
}

export type ReadStatus = "none" | "to_read" | "reading" | "read";

/** 个人数据：只存在浏览器本地 */
export interface UserEntry {
  status: ReadStatus;
  rating: number; // 0 表示未评分，1–5
  note: string;
  updated: string;
}
export type UserData = Record<string, UserEntry>;
