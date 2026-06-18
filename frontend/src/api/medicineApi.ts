import { request, requestUpload } from './client';

export interface Medicine {
  id: string;
  name: string;
  type: string;
  status: string;
  dosage: string;
  notes: string;
  quantity?: number;
  expiry_date?: string;
}

export interface PaginatedMedicines {
  items: Medicine[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

export interface OcrRecognitionResult {
  name?: string;
  type?: string;
  specification?: string;
  dosage_instructions?: string;
  raw_text: string;
  confidence: 'high' | 'medium' | 'low';
  message?: string;
}

export interface BarcodeLookupResult {
  valid: boolean;
  barcode: string;
  format?: string;
  reason?: string;
}

const STORAGE_KEY = 'family_doctor_medicines';

function getStoredMedicines(): Medicine[] {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored) {
    try {
      return JSON.parse(stored) as Medicine[];
    } catch {
      return [];
    }
  }
  return [];
}

function saveMedicines(medicines: Medicine[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(medicines));
}

/** Map backend medicine row to frontend Medicine interface */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function mapMedicine(row: any): Medicine {
  return {
    id: row.id ?? '',
    name: row.name ?? '',
    type: row.type ?? '',
    status: row.quantity != null
      ? row.quantity > 5
        ? '充足'
        : row.quantity > 0
          ? '低库存'
          : '已过期'
      : '充足',
    dosage: row.dosage_instructions ?? row.dosage ?? '',
    notes: row.contraindications ?? row.notes ?? '',
    quantity: row.quantity,
    expiry_date: row.expiry_date,
  };
}

export async function getMedicines(params?: {
  page?: number;
  pageSize?: number;
}): Promise<PaginatedMedicines> {
  try {
    const query = new URLSearchParams();
    if (params?.page) query.set('page', String(params.page));
    if (params?.pageSize) query.set('pageSize', String(params.pageSize));
    const qs = query.toString();

    const data = await request<{ items: unknown[]; total?: number; page?: number; pageSize?: number; totalPages?: number }>(
      `/api/medicines${qs ? `?${qs}` : ''}`,
    );
    const items = (data.items ?? []).map(mapMedicine);
    return {
      items,
      total: data.total ?? items.length,
      page: data.page ?? 1,
      pageSize: data.pageSize ?? 20,
      totalPages: data.totalPages ?? 1,
    };
  } catch {
    const stored = getStoredMedicines();
    const page = params?.page ?? 1;
    const pageSize = params?.pageSize ?? 20;
    const total = stored.length;
    const start = (page - 1) * pageSize;
    const items = stored.slice(start, start + pageSize);
    return {
      items,
      total,
      page,
      pageSize,
      totalPages: Math.ceil(total / pageSize) || 1,
    };
  }
}

export async function createMedicine(data: {
  name: string;
  type: string;
  status?: string;
  dosage?: string;
  notes?: string;
  quantity?: number;
  expiry_date?: string;
}): Promise<Medicine> {
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const row = await request<any>('/api/medicines', {
      method: 'POST',
      body: JSON.stringify({
        name: data.name,
        type: data.type,
        dosage_instructions: data.dosage,
        contraindications: data.notes,
        quantity: data.quantity,
        expiry_date: data.expiry_date,
      }),
    });
    return mapMedicine(row);
  } catch {
    const medicines = getStoredMedicines();
    const newMedicine: Medicine = {
      id: Date.now().toString(),
      name: data.name,
      type: data.type,
      status: data.status ?? '充足',
      dosage: data.dosage ?? '',
      notes: data.notes ?? '',
    };
    medicines.push(newMedicine);
    saveMedicines(medicines);
    return newMedicine;
  }
}

export async function updateMedicine(
  id: string,
  data: Partial<Omit<Medicine, 'id'>>,
): Promise<Medicine> {
  try {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const row = await request<any>(`/api/medicines/${id}`, {
      method: 'PUT',
      body: JSON.stringify({
        name: data.name,
        type: data.type,
        dosage_instructions: data.dosage,
        contraindications: data.notes,
        quantity: data.quantity,
        expiry_date: data.expiry_date,
      }),
    });
    return mapMedicine(row);
  } catch {
    const medicines = getStoredMedicines();
    const index = medicines.findIndex((m) => m.id === id);
    if (index >= 0) {
      const existing = medicines[index];
      if (existing) {
        const updated: Medicine = {
          id: existing.id,
          name: data.name ?? existing.name,
          type: data.type ?? existing.type,
          status: data.status ?? existing.status,
          dosage: data.dosage ?? existing.dosage,
          notes: data.notes ?? existing.notes,
        };
        medicines[index] = updated;
        saveMedicines(medicines);
        return updated;
      }
    }
    throw new Error('药品未找到');
  }
}

export async function deleteMedicine(id: string): Promise<void> {
  try {
    await request<void>(`/api/medicines/${id}`, { method: 'DELETE' });
  } catch {
    const medicines = getStoredMedicines();
    const filtered = medicines.filter((m) => m.id !== id);
    saveMedicines(filtered);
  }
}

export async function recognizeMedicineImage(
  file: File,
): Promise<OcrRecognitionResult> {
  const formData = new FormData();
  formData.append('file', file);
  return requestUpload<OcrRecognitionResult>(
    '/api/medicines/ocr-recognize',
    formData,
  );
}

export async function lookupBarcode(
  barcode: string,
): Promise<BarcodeLookupResult> {
  return request<BarcodeLookupResult>('/api/medicines/barcode-lookup', {
    method: 'POST',
    body: JSON.stringify({ barcode }),
  });
}
