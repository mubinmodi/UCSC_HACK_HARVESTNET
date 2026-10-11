// Replace this adapter with backend calls. Every value returned here is synthetic.
export interface Household { size: number; neighborhood: string; time: string; fridge: string; avoid: string; snap: string; language: 'en' | 'es'; phone: string }
export const banks = [
  { id: 'mission', name: 'Mission Community Market', distance: '0.7', address: '701 Alabama Street', hours: 'Tue & Thu · 3–6 PM', tags: ['Fresh produce', 'Pantry staples'], windows: ['Thu, Oct 15 · 3:00–4:00 PM', 'Thu, Oct 15 · 5:00–6:00 PM'] },
  { id: 'buena', name: 'Buena Vista Family Pantry', distance: '1.2', address: '123 Example Street', hours: 'Wed & Sat · 10 AM–2 PM', tags: ['Fresh produce', 'Family groceries'], windows: ['Wed, Oct 14 · 10:00–11:00 AM', 'Sat, Oct 17 · 12:00–1:00 PM'] },
];
export const placeholderApi = {
  async submitHousehold(_household: Household) { return { requestId: 'example-request', fairShare: 24, banks }; },
  async confirmPickup(_requestId: string, _bankId: string, _window: string, _notes: string) { return { code: 'FS-4827', balance: 18 }; },
  async cancelPickup(_requestId: string) { return { cancelled: true }; },
};
