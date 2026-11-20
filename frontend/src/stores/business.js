import {loadAll,materialDetail} from '../api/business.js';
export const store={session:JSON.parse(localStorage.getItem('session')||'null'),data:{sources:[],periods:[],policies:[],runs:[],schedules:[],deliveries:[],audits:[],materials:[]},selected:null,mat:{name:null,detail:null,lines:null,verify:null}};
export async function reload(){store.data=await loadAll()}
export async function reloadMaterial(){store.mat.detail=store.mat.name?await materialDetail(store.mat.name):null}
export function setSession(value){store.session=value;if(value)localStorage.setItem('session',JSON.stringify(value));else localStorage.removeItem('session')}
