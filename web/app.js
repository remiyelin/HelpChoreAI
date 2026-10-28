const $=s=>document.querySelector(s); let pairs=[],cur=null,queue=[],selCell=null,signed=false;
async function j(u,o){const r=await fetch(u,o);return r.json()}
function fmt(x){return (x>=0?"+":"")+Number(x).toFixed(4)}
async function init(){
 const meta=await j('/api/meta');
 $('#liveBadges').innerHTML=Object.entries(meta.live).map(([k,v])=>`<span>${k}: <b>${v}</b></span>`).join('');
 pairs=await j('/api/pairs');
 const pats=[...new Set(pairs.map(p=>p.patient))];
 $('#selPatient').innerHTML=pats.map(p=>`<option>${p}</option>`).join('');
 $('#selPatient').onchange=fillVisits; fillVisits(); renderPairs(); loadQueue(); updKappa();
 document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{document.querySelectorAll('nav button').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.querySelectorAll('main section').forEach(s=>s.hidden=true);$('#view-'+b.dataset.view).hidden=false;});
 $('#selFrom').onchange=$('#selTo').onchange=showPair;
 $('#btnHealthy').onclick=()=>rate(0); $('#btnUnhealthy').onclick=()=>rate(1);
 $('#btnReport').onclick=genReport;
 $('#btnTamperNumber').onclick=()=>tamper('number'); $('#btnTamperAdvice').onclick=()=>tamper('advice'); $('#btnTamperPayload').onclick=()=>tamper('payload');
 $('#btnApprove').onclick=()=>signoff('Approved by qualified researcher (overlay review complete)');
 $('#btnFlag').onclick=()=>signoff('Flagged by researcher — do not use until re-reviewed');
}
function visits(){return [...new Set(pairs.filter(p=>p.patient===$('#selPatient').value).flatMap(p=>[p.from,p.to]))]}
function fillVisits(){const v=visits();$('#selFrom').innerHTML=v.map(x=>`<option>${x}</option>`).join('');$('#selTo').innerHTML=v.map(x=>`<option>${x}</option>`).join('');if(v.length>1)$('#selTo').selectedIndex=1;showPair()}
function pair(){return pairs.find(p=>p.patient===$('#selPatient').value&&p.from===$('#selFrom').value&&p.to===$('#selTo').value)}
function showPair(){cur=pair(); if(!cur){$('#pairContext').textContent='No such consecutive pair.';return}
 $('#pairContext').innerHTML=`<b>${cur.patient} ${cur.from} → ${cur.to}</b> · Treatment: ${cur.treatment}<br>Δ raw ${fmt(cur.delta_raw)} · Δ flow-adjusted ${fmt(cur.delta_adj)} · RCV95 ${Number(cur.RCV95).toFixed(4)} · Decision: <b>${cur.decision}</b>`;
 $('#decisionCard').innerHTML=`<b>${cur.patient} ${cur.from} → ${cur.to}</b> (${cur.treatment})<br>Raw change: ${fmt(cur.delta_raw)}<br>Flow-adjusted change: ${fmt(cur.delta_adj)}<br>RCV95 band: ±${Number(cur.RCV95).toFixed(4)}<br>Decision: <b>${cur.decision}</b>${cur.decision==='indeterminate_QC'?'<br><span class="blocked">QC-blocked: degraded skip rate / low kept cells — system refuses to decide.</span>':''}`;
 signed=false;$('#signoffState').textContent='Not reviewed';$('#reportBox').textContent='';$('#gateBox').innerHTML='';renderChart();}
async function renderChart(){const patient=$('#selPatient').value;const d=await j('/api/longitudinal/'+patient);const vs=d.visits;if(!vs.length)return;
 const W=860,H=260,pl=46,pr=14,pt=14,pb=34,ymax=0.85;const X=i=>pl+i*(W-pl-pr)/Math.max(1,vs.length-1);const Y=v=>pt+(ymax-v)/ymax*(H-pt-pb);
 let s=`<svg viewBox="0 0 ${W} ${H}" width="100%"><rect x="0" y="0" width="${W}" height="${H}" fill="#fff"/>`;
 vs.forEach((v,i)=>{if(v.qc_blocked){const x0=i===0?pl:X(i)-(X(1)-X(0))/2;const wdt=(X(1)-X(0)||60);s+=`<rect x="${x0}" y="${pt}" width="${wdt}" height="${H-pt-pb}" fill="rgba(220,38,38,.13)"/>`}});
 const band=vs.map((v,i)=>`${X(i)},${Y(Math.min(ymax,v.frac_adj+1.96*Math.sqrt(v.var)))}`).join(' ')+' '+vs.map((v,i)=>`${X(i)},${Y(Math.max(0,v.frac_adj-1.96*Math.sqrt(v.var)))}`).reverse().join(' ');
 s+=`<polygon points="${band}" fill="rgba(13,118,110,.15)"/>`;
 s+=`<polyline fill="none" stroke="#6b7280" stroke-width="2" points="${vs.map((v,i)=>X(i)+','+Y(v.frac_raw)).join(' ')}"/>`;
 s+=`<polyline fill="none" stroke="#0d766e" stroke-width="2.5" points="${vs.map((v,i)=>X(i)+','+Y(v.frac_adj)).join(' ')}"/>`;
 vs.forEach((v,i)=>{s+=`<circle cx="${X(i)}" cy="${Y(v.frac_adj)}" r="3.5" fill="#0d766e"/><text x="${X(i)}" y="${H-12}" font-size="11" text-anchor="middle">${v.visit}</text>${v.qc_blocked?`<text x="${X(i)}" y="${pt+10}" font-size="10" fill="#b91c1c" text-anchor="middle">QC</text>`:''}`});
 s+=`<text x="${pl}" y="${pt+2}" font-size="11" fill="#6b7280">raw (gray) vs adjusted (teal)</text></svg>`;$('#longChart').innerHTML=s;}
function planner(){const target=+$('#plTarget').value,p=+$('#plP').value,phi=+$('#plPhi').value,cells=+$('#plCells').value,e=0.391;
 const varNeed=Math.pow(target/1.96,2)/2;const perCell=phi*p*(1-p)+e*(1-e);const N=Math.ceil(perCell/varNeed);const runs=Math.ceil(N/cells);
 const achieved=1.96*Math.sqrt(2*(perCell/(runs*cells)));
 $('#planOut').innerHTML=`<b>${runs} runs/visit</b> (${runs*cells} cells) → MDC95 ≈ ${achieved.toFixed(3)} (target ${target})`;}
document.addEventListener('click',e=>{if(e.target.id==='btnPlan')planner()});
function renderPairs(){$('#pairsTable').innerHTML='<table><tr><th>Pair</th><th>Δ raw</th><th>Δ adj</th><th>Decision</th></tr>'+pairs.map(p=>`<tr><td>${p.patient} ${p.from}→${p.to}</td><td>${fmt(p.delta_raw)}</td><td>${fmt(p.delta_adj)}</td><td>${p.decision}</td></tr>`).join('')+'</table>'}
async function loadQueue(){queue=await j('/api/queue');
 $('#queueList').innerHTML=queue.slice(0,120).map((q,i)=>`<div class="qitem" data-i="${i}">${q.patient} ${q.visit} cell ${q.cell} · author health=${q.health} · pred=${q.pred} · conf=${Number(q.confidence).toFixed(2)}</div>`).join('');
 document.querySelectorAll('.qitem').forEach(el=>el.onclick=()=>selectCell(queue[+el.dataset.i]));}
async function selectCell(q){selCell=q;const c=await j(`/api/cell/${q.patient}/${q.date}/${q.cell}`);
 const info=await j(`/api/frameinfo/${q.patient}/${q.date}/${q.cell}`);
 if(info.contour_crop){$('#cellPoly').setAttribute('points',info.contour_crop.map(p=>p.join(',')).join(' '));
  $('#stripPoly').setAttribute('points',(info.contour_full||[]).map(p=>p.join(',')).join(' '));
  $('#cropImg').src=`/api/frame/${q.patient}/${q.date}/${q.cell}/crop.png`; $('#stripImg').src=`/api/frame/${q.patient}/${q.date}/${q.cell}/strip.png`;
  $('#cellInfo').innerHTML=`${q.patient} ${q.visit} cell ${q.cell} · REAL FRAME ${info.frame} (pos_x ${info.pos_x})<br>Author health=${q.health} · Classifier pred=${q.pred} (conf ${Number(q.confidence).toFixed(2)})<br>Frames tracked: ${c.n_frames??'—'} — judge spicules on the grayscale crop, not the outline.`;}
 else{$('#cellInfo').innerHTML=`${q.patient} ${q.visit} cell ${q.cell}<br>Author health=${q.health} · Classifier pred=${q.pred} (conf ${Number(q.confidence).toFixed(2)})<br>Real frame not extracted for this cell yet (sample: P1 0w M10 cells 4, 11, 19). Contour-only view below.`;$('#cropImg').removeAttribute('src');$('#stripImg').removeAttribute('src');}}
async function rate(v){if(!selCell)return alert('Select a cell first');await j('/api/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({patient:selCell.patient,date:selCell.date,cell:selCell.cell,rater:v})});updKappa()}
async function updKappa(){const k=await j('/api/kappa');$('#kappaBox').innerHTML=k.n?`Second-rater labels: ${k.reviews} · vs author n=${k.n}<br>Agreement ${k.agreement} · Cohen κ <b>${k.kappa}</b> · Gwet AC1 <b>${k.ac1}</b>`:'No second-rater labels yet — label cells to compute κ / AC1.'}
async function genReport(){const p=pair();const r=await j(`/api/report/${p.patient}/${p.from}/${p.to}`);
 $('#reportBox').textContent=r.report;
 $('#gateBox').innerHTML=`Checker verify: <b class="${r.verified?'ok':'blocked'}">${r.verified?'PASS':'FAIL'}</b> ${r.verify_errors.join('; ')}<br>Local auditor: <b class="${r.audit_ok?'ok':'blocked'}">${r.audit_ok?'PASS':'BLOCK'}</b> ${r.audit_errors.join('; ')}<br>Open-weight auditor (Baseten): <b>${r.open_weight.status}</b> — ${r.open_weight.detail}`;}
async function tamper(mode){const p=pair();const r=await j('/api/tamper',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({patient:p.patient,from:p.from,to:p.to,mode})});
 $('#reportBox').textContent=r.report||JSON.stringify(r,null,1);
 const blocked=r.auditor_blocks_report||r.checker_blocks;
 $('#gateBox').innerHTML=`<span class="blocked">TAMPER SIMULATION (${r.tampered}): ${blocked?'BLOCKED':'NOT BLOCKED'}</span><br>${(r.auditor_errors||r.verify_errors||[]).join('<br>')}`;}
function signoff(t){signed=true;$('#signoffState').innerHTML=`<b>${t}</b> — required before any result is final.`}
init();
