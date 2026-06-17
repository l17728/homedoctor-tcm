import { request } from './client';

export type NodeType = 'herb' | 'formula' | 'symptom' | 'therapy' | 'medicine';

export type EdgeType = '组成' | '主治' | '配伍禁忌' | '中西药交互';

export interface GraphNodeDatum {
  id: string;
  node_type: NodeType | string;
  label: string;
}

export interface GraphEdgeDatum {
  source: string;
  target: string;
  edge_type: EdgeType | string;
}

export interface GraphData {
  root_id: string;
  nodes: GraphNodeDatum[];
  edges: GraphEdgeDatum[];
}

export type GraphSnapshot = GraphData;

export interface RebuildResult {
  组成: number;
  主治: number;
  配伍禁忌: number;
  中西药交互: number;
}

export interface GraphNodeDetail {
  id: string;
  node_type: string;
  label: string;
  properties: Record<string, unknown>;
  search_text: string | null;
  created_at: string;
}

export async function getGraph(params?: {
  types?: string;
  q?: string;
  limit?: number;
}): Promise<GraphData> {
  const query = new URLSearchParams();
  if (params?.types) query.set('types', params.types);
  if (params?.q) query.set('q', params.q);
  if (params?.limit) query.set('limit', String(params.limit));
  const qs = query.toString();
  return request<GraphData>(`/api/kg/graph${qs ? `?${qs}` : ''}`);
}

export async function getSnapshot(
  nodeType: string,
  nodeId: string,
  depth?: number,
): Promise<GraphSnapshot> {
  const query = depth ? `?depth=${depth}` : '';
  return request<GraphSnapshot>(
    `/api/kg/snapshot/${encodeURIComponent(nodeType)}/${encodeURIComponent(nodeId)}${query}`,
  );
}

export async function rebuildGraph(): Promise<RebuildResult> {
  return request<RebuildResult>('/api/kg/rebuild', { method: 'POST' });
}

export async function getNode(nodeId: string): Promise<GraphNodeDetail> {
  return request<GraphNodeDetail>(`/api/kg/node/${encodeURIComponent(nodeId)}`);
}
