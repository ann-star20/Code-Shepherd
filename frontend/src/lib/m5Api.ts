import axios, { type InternalAxiosRequestConfig } from "axios";

const m5Client = axios.create({ baseURL: "" });
m5Client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem("access_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

function extractDetail(error: unknown, fallback: string): Error {
  const detail = (error as { response?: { data?: { detail?: string } } })
    .response?.data?.detail;
  return new Error(typeof detail === "string" ? detail : fallback);
}

// ── Types ──────────────────────────────────────────────────────────────────

export type CodeExampleMeta = {
  unq_id: string;
  lang: string | null;
  framework: string | null;
};

export type MechanismMeta = {
  mechanism_name: string;
  code_examples: CodeExampleMeta[];
};

export type ConceptOverview = {
  concept_name: string;
  severity: string | null;
  mechanism_names: string[];
  domain_names: string[];
};

export type GraphOverviewResponse = {
  concepts: ConceptOverview[];
};

export type ConceptGraphResponse = {
  concept_name: string;
  concept_desc: string | null;
  cwe_id: string | null;
  owasp_id: string | null;
  severity: string | null;
  affected_components: string[];
  parent_domains: string[];
  related_concepts: string[];
  mechanisms: MechanismMeta[];
};

export type VideoResult = {
  rank: number;
  recommendation_type: string;
  query_used: string;
  title: string;
  url: string;
  thumbnail: string | null;
  channel_title: string | null;
};

export type RankedRecommendRequest = {
  concept_name: string;
  mechanism_name?: string | null;
  code_id?: string | null;
  code_lang?: string | null;
  code_framework?: string | null;
};

export type RankedRecommendResponse = {
  concept_name: string;
  videos: VideoResult[];
};

// ── API Functions ──────────────────────────────────────────────────────────

export async function getGraphOverview(): Promise<GraphOverviewResponse> {
  try {
    const { data } = await m5Client.get<GraphOverviewResponse>("/m5-api/graph/overview");
    return data;
  } catch (e) {
    throw extractDetail(e, "그래프 데이터를 불러오지 못했습니다");
  }
}

export async function getConceptGraph(keyword: string): Promise<ConceptGraphResponse> {
  try {
    const { data } = await m5Client.get<ConceptGraphResponse>("/m5-api/graph/concept", {
      params: { keyword },
    });
    return data;
  } catch (e) {
    throw extractDetail(e, `'${keyword}' 개념을 찾을 수 없습니다`);
  }
}

export async function getRankedRecommendations(
  req: RankedRecommendRequest
): Promise<RankedRecommendResponse> {
  try {
    const { data } = await m5Client.post<RankedRecommendResponse>(
      "/m5-api/youtube/ranked",
      req
    );
    return data;
  } catch (e) {
    throw extractDetail(e, "YouTube 추천 요청에 실패했습니다");
  }
}
