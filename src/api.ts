export type Status = 'Offered' | 'Negotiating' | 'Committed' | 'Delivered' | 'Unclaimed';
export interface Offer { id: string; item: string; quantity: number; unit: string; grade: string; deadline: string; recall: boolean; deliver: boolean; notes: string; status: Status; from: string; recommendation: string; reason: string; destination?: string; reached?: number; pickup?: string; code: string }
export interface Note { author: string; text: string; time: string }
export const profiles = ['Tomatoes', 'Lettuce', 'Carrots', 'Apples'];
export const fixtures: Offer[] = [
 { id:'tomatoes',item:'Tomatoes',quantity:500,unit:'lb',grade:'A',deadline:'2026-10-18',recall:false,deliver:true,notes:'Produce is freshly harvested and kept in cool storage.',status:'Negotiating',from:'Green Valley Farm',recommendation:'Suggested Accept',reason:'High demand, good condition, and fits your fair-share gap for fresh produce. Farm is 12 miles away and can deliver.',code:'8427' },
 { id:'lettuce',item:'Lettuce',quantity:300,unit:'lb',grade:'B',deadline:'2026-10-17',recall:false,deliver:false,notes:'Please collect in a refrigerated truck.',status:'Committed',from:'Sunny Fields',recommendation:'Review',reason:'Confirm refrigerated storage and truck availability before approving.',destination:'Buena Vista Family Pantry',pickup:'Oct 16, 10:00 AM',code:'7316' },
 { id:'carrots',item:'Carrots',quantity:200,unit:'lb',grade:'A',deadline:'2026-10-16',recall:false,deliver:true,notes:'Delivered in reusable crates.',status:'Delivered',from:'Coastal Growers',recommendation:'Delivered',reason:'The example delivery has been recorded.',destination:'Community Food Bank',reached:180,code:'6295' },
 { id:'apples',item:'Apples',quantity:400,unit:'lb',grade:'B',deadline:'2026-10-16',recall:false,deliver:true,notes:'Mixed varieties, ready to share.',status:'Unclaimed',from:'Harvest Ridge',recommendation:'Consider',reason:'Review dry storage capacity and available pickup windows.',code:'5184' },
];
// In-memory placeholders only. Replace these methods with the real backend adapter.
export const api = {
 async load() { return { offers: structuredClone(fixtures), profiles, storage:65, truck:'Ready', coolers:'Ready', temperature:36, households:2850, gap:620 }; },
 async submit(offer: Omit<Offer,'id'|'status'|'from'|'recommendation'|'reason'|'code'>): Promise<Offer> { return { ...offer,id:crypto.randomUUID(),status:'Offered',from:'Your organization',recommendation:'Review',reason:'New example offer awaiting review.',code:'0000' }; },
 async respond(_id:string,_action:string,_reason:string,_quantity?:number) { return { recorded:true }; },
 async condition(_id:string,_approved:boolean,_reason:string) { return { recorded:true }; },
 async pickup(id:string,code:string,offers:Offer[]) { if (offers.find(o=>o.id===id)?.code !== code.trim()) throw new Error('The example code does not match this offer.'); return { recorded:true }; },
 async relist(_id:string,_deadline:string) { return { recorded:true }; },
};
export type Dashboard = Awaited<ReturnType<typeof api.load>>;
