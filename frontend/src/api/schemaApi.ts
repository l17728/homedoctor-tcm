import { request } from './client';

/** Field type supported by the schema system. */
export type SchemaFieldType =
  | 'string'
  | 'number'
  | 'enum'
  | 'boolean'
  | 'date'
  | 'text';

/** A single field definition loaded from a backend schema JSON. */
export interface SchemaFieldDef {
  id: string;
  name: string;
  type: SchemaFieldType;
  label: string;
  required: boolean;
  group?: string;
  order?: number;
  enumValues?: string[];
}

/** A complete schema definition for one entity type. */
export interface SchemaDefinition {
  nodeType: string;
  label: string;
  fields: SchemaFieldDef[];
}

/** Response from GET /api/schemas */
interface SchemaListResponse {
  items: SchemaDefinition[];
}

/** Fetch a single schema definition by node type. */
export async function getSchema(
  nodeType: string,
): Promise<SchemaDefinition> {
  return request<SchemaDefinition>(`/api/schemas/${nodeType}`);
}

/** List all available schema definitions. */
export async function listSchemas(): Promise<SchemaDefinition[]> {
  const data = await request<SchemaListResponse>('/api/schemas');
  return data.items;
}
