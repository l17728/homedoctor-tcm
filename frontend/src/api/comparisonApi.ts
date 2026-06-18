import { request } from './client';

export interface HerbComparisonItem {
  id: string;
  name: string;
  nature: string;
  flavor: string;
  meridians: string;
  efficacy: string;
  indications: string;
  dosage_min_g: number | null;
  dosage_max_g: number | null;
  toxicity: string;
  category: string;
  contraindications: string;
}

export interface FormulaComparisonItem {
  id: string;
  name: string;
  category: string;
  source: string;
  efficacy: string;
  indications: string;
  composition: unknown;
  herb_names: string[];
}

export interface ComparisonPropertyRow {
  field: string;
  label: string;
  values: Record<string, string>;
  same: boolean;
}

export interface CompositionOverlap {
  formula_a: string;
  formula_b: string;
  shared: string[];
  shared_count: number;
  overlap_ratio: number;
}

export interface HerbComparisonResult {
  herbs: HerbComparisonItem[];
  property_table: ComparisonPropertyRow[];
  similarities: string[];
  differences: string[];
  safety_notes: string[];
  not_found: string[];
}

export interface FormulaComparisonResult {
  formulas: FormulaComparisonItem[];
  shared_herbs: string[];
  shared_herb_count: number;
  herbs_unique_to_each: Record<string, string[]>;
  composition_overlap: CompositionOverlap[];
  efficacy_comparison: { name: string; efficacy: string }[];
  shared_indications: string[];
  property_table: ComparisonPropertyRow[];
  safety_notes: string[];
  not_found: string[];
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapHerbItem(row: any): HerbComparisonItem {
  return {
    id: row.id ?? '',
    name: row.name ?? '',
    nature: row.nature ?? '',
    flavor: row.flavor ?? '',
    meridians: row.meridians ?? '',
    efficacy: row.efficacy ?? '',
    indications: row.indications ?? '',
    dosage_min_g: row.dosage_min_g ?? null,
    dosage_max_g: row.dosage_max_g ?? null,
    toxicity: row.toxicity ?? '',
    category: row.category ?? '',
    contraindications: row.contraindications ?? '',
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapFormulaItem(row: any): FormulaComparisonItem {
  return {
    id: row.id ?? '',
    name: row.name ?? '',
    category: row.category ?? '',
    source: row.source ?? '',
    efficacy: row.efficacy ?? '',
    indications: row.indications ?? '',
    composition: row.composition ?? [],
    herb_names: Array.isArray(row.herb_names) ? row.herb_names : [],
  };
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapPropertyTable(rows: any[]): ComparisonPropertyRow[] {
  if (!Array.isArray(rows)) return [];
  return rows.map((r) => ({
    field: r.field ?? '',
    label: r.label ?? '',
    values: r.values ?? {},
    same: !!r.same,
  }));
}

export async function compareHerbs(herbIds: string[]): Promise<HerbComparisonResult> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const data = await request<any>('/api/comparisons/herbs', {
    method: 'POST',
    body: JSON.stringify({ herb_ids: herbIds }),
  });
  return {
    herbs: Array.isArray(data.herbs) ? data.herbs.map(mapHerbItem) : [],
    property_table: mapPropertyTable(data.property_table),
    similarities: Array.isArray(data.similarities) ? data.similarities : [],
    differences: Array.isArray(data.differences) ? data.differences : [],
    safety_notes: Array.isArray(data.safety_notes) ? data.safety_notes : [],
    not_found: Array.isArray(data.not_found) ? data.not_found : [],
  };
}

export async function compareFormulas(formulaIds: string[]): Promise<FormulaComparisonResult> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const data = await request<any>('/api/comparisons/formulas', {
    method: 'POST',
    body: JSON.stringify({ formula_ids: formulaIds }),
  });
  const overlap: CompositionOverlap[] = Array.isArray(data.composition_overlap)
    ? // eslint-disable-next-line @typescript-eslint/no-explicit-any
      data.composition_overlap.map((o: any) => ({
        formula_a: o.formula_a ?? '',
        formula_b: o.formula_b ?? '',
        shared: Array.isArray(o.shared) ? o.shared : [],
        shared_count: o.shared_count ?? 0,
        overlap_ratio: o.overlap_ratio ?? 0,
      }))
    : [];
  return {
    formulas: Array.isArray(data.formulas) ? data.formulas.map(mapFormulaItem) : [],
    shared_herbs: Array.isArray(data.shared_herbs) ? data.shared_herbs : [],
    shared_herb_count: data.shared_herb_count ?? 0,
    herbs_unique_to_each: data.herbs_unique_to_each ?? {},
    composition_overlap: overlap,
    efficacy_comparison: Array.isArray(data.efficacy_comparison) ? data.efficacy_comparison : [],
    shared_indications: Array.isArray(data.shared_indications) ? data.shared_indications : [],
    property_table: mapPropertyTable(data.property_table),
    safety_notes: Array.isArray(data.safety_notes) ? data.safety_notes : [],
    not_found: Array.isArray(data.not_found) ? data.not_found : [],
  };
}

export async function compareTwoHerbs(herbA: string, herbB: string): Promise<HerbComparisonResult> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const data = await request<any>(`/api/comparisons/herbs/${herbA}/${herbB}`);
  return {
    herbs: Array.isArray(data.herbs) ? data.herbs.map(mapHerbItem) : [],
    property_table: mapPropertyTable(data.property_table),
    similarities: Array.isArray(data.similarities) ? data.similarities : [],
    differences: Array.isArray(data.differences) ? data.differences : [],
    safety_notes: Array.isArray(data.safety_notes) ? data.safety_notes : [],
    not_found: Array.isArray(data.not_found) ? data.not_found : [],
  };
}
