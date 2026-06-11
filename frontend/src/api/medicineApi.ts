import { request } from './client';

export interface Medicine {
  id: string;
  name: string;
  type: string;
  status: string;
  dosage: string;
  notes: string;
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

export async function getMedicines(): Promise<Medicine[]> {
  try {
    return request<Medicine[]>('/api/medicines');
  } catch {
    return getStoredMedicines();
  }
}

export async function createMedicine(data: {
  name: string;
  type: string;
  status?: string;
  dosage?: string;
  notes?: string;
}): Promise<Medicine> {
  try {
    return request<Medicine>('/api/medicines', {
      method: 'POST',
      body: JSON.stringify(data),
    });
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
    return request<Medicine>(`/api/medicines/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
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
