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
 $('#btnApprove').onclick=()=>signoff('Approved');
 $('#btnFlag').onclick=()=>signoff('Flagged');
 $('#btnDictate').onclick=dictate;
 loadBenchmark();
}
async function loadBenchmark(){try{const b=await j('/api/benchmark');
 if(b.status==='NOT_RUN'){$('#benchmarkCard').innerHTML=`<b>Live multi-model benchmark:</b> not run yet — <span class="mono">uv run python src/run_live_benchmark.py</span>`;return}
 $('#benchmarkCard').innerHTML=`<b>Live multi-model benchmark</b> (cached real-data run, details in docs/LIVE_BENCHMARK.md)<br>SAM 3.1 IoU vs author: mean <b>${b.sam_iou_mean}</b> · median ${b.sam_iou_median} · range ${b.sam_iou_min}–${b.sam_iou_max} · ≥0.80: ${b.sam_iou_ge80_frac} (n=${b.sam_ok})<br>Structured Spark second rater: see docs/RATERS.md (keyword agreement figure removed as invalid)<br>Cloud vs Open-Weight audit parity: <b>${b.parity_n}/${b.pairs_n} pairs</b>`;}catch(e){$('#benchmarkCard').textContent='Live benchmark: unavailable ('+e+')'}}
let recCtx=null,recBuf=[],recStream=null,recording=false;
function wavEncode(chunks,sampleRate){let len=0;for(const c of chunks)len+=c.length;const buf=new Float32Array(len);let o=0;for(const c of chunks){buf.set(c,o);o+=c.length}
 const ds=Math.floor(sampleRate/16000)||1, n=Math.floor(buf.length/ds), pcm=new Int16Array(n);
 for(let i=0;i<n;i++){const v=Math.max(-1,Math.min(1,buf[i*ds]));pcm[i]=v<0?v*32768:v*32767}
 const ab=new ArrayBuffer(44+pcm.length*2), d=new DataView(ab);
 const ws=(off,s)=>{for(let i=0;i<s.length;i++)d.setUint8(off+i,s.charCodeAt(i))};
 ws(0,'RIFF');d.setUint32(4,36+pcm.length*2,true);ws(8,'WAVEfmt ');d.setUint32(16,16,true);d.setUint16(20,1,true);d.setUint16(22,1,true);
 d.setUint32(24,16000,true);d.setUint32(28,32000,true);d.setUint16(32,2,true);d.setUint16(34,16,true);ws(36,'data');d.setUint32(40,pcm.length*2,true);
 for(let i=0;i<pcm.length;i++)d.setInt16(44+i*2,pcm[i],true); return new Uint8Array(ab);}
async function dictate(){const btn=$('#btnDictate');
 if(!recording){try{recStream=await navigator.mediaDevices.getUserMedia({audio:true});}catch(e){$('#voiceState').textContent='Microphone unavailable: '+e.message+' — type the note instead.';return}
  recCtx=new (window.AudioContext||window.webkitAudioContext)();recBuf=[];recording=true;btn.textContent='Stop & transcribe';
  const src=recCtx.createMediaStreamSource(recStream),proc=recCtx.createScriptProcessor(4096,1,1);
  proc.onaudioprocess=e=>recBuf.push(new Float32Array(e.inputBuffer.getChannelData(0)));src.connect(proc);proc.connect(recCtx.destination);recCtx._p=proc;$('#voiceState').textContent='Recording… click again to transcribe.';return}
 recording=false;btn.textContent='Dictate note (Muse Voice)';
 recStream.getTracks().forEach(t=>t.stop());const rate=recCtx.sampleRate;recCtx.close();
 const wav=wavEncode(recBuf,rate);$('#voiceState').textContent='Transcribing with muse-voice-transcribe…';
 let bin='';wav.forEach(b=>bin+=String.fromCharCode(b));
 const r=await j('/api/transcribe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({audio_b64:btoa(bin)})});
 if(r.status==='OK'){$('#reviewNote').value=($('#reviewNote').value+' '+r.text).trim();$('#voiceState').textContent=`Transcribed (${r.model}, cache ${r._cache}, ${r.audio_ms??'—'} ms). Review the text, then Approve/Flag.`}
 else $('#voiceState').innerHTML=`<span class="blocked">Voice ${r.status}:</span> ${r.detail||''} — type the note instead.`}
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
function planner(){const target=+$('#plTarget').value,p=+$('#plP').value,phi=+$('#plPhi').value,cells=+$('#plCells').value;
 // Label variance (0.391) deliberately excluded: it is classifier-vs-author disagreement,
 // not measurement noise of the fraction (v3 stats; sensitivity only in docs/STATS_VALIDATION.md).
 const varNeed=Math.pow(target/1.96,2)/2;const perCell=phi*p*(1-p);const N=Math.ceil(perCell/varNeed);const runs=Math.ceil(N/cells);
 const achieved=1.96*Math.sqrt(2*(perCell/(runs*cells)));
 $('#planOut').innerHTML=`<b>${runs} runs/visit</b> (${runs*cells} cells) → MDC95 ≈ ${achieved.toFixed(3)} (target ${target})`;}
document.addEventListener('click',e=>{if(e.target.id==='btnPlan')planner()});
function renderPairs(){$('#pairsTable').innerHTML='<table><tr><th>Pair</th><th>Δ raw</th><th>Δ adj</th><th>Decision</th></tr>'+pairs.map(p=>`<tr><td>${p.patient} ${p.from}→${p.to}</td><td>${fmt(p.delta_raw)}</td><td>${fmt(p.delta_adj)}</td><td>${p.decision}</td></tr>`).join('')+'</table>'}
async function loadQueue(){queue=await j('/api/queue');
 $('#queueList').innerHTML=queue.slice(0,200).map((q,i)=>`<div class="qitem" data-i="${i}">${q.has_frame?'<b>[REAL FRAME]</b> ':''}${q.patient} ${q.visit} cell ${q.cell} · author health=${q.health} · pred=${q.pred} · conf=${Number(q.confidence).toFixed(2)}</div>`).join('');
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
 const ow=r.open_weight||{};
 $('#gateBox').innerHTML=`<b>Cloud vs Open-Weight verification</b><br>Cloud muse-spark-1.3 narrative: ${r.narrative_source} · Checker: <b class="${r.verified?'ok':'blocked'}">${r.verified?'PASS':'FAIL'}</b> ${r.verify_errors.join('; ')}<br>Local rule auditor: <b class="${r.audit_ok?'ok':'blocked'}">${r.audit_ok?'PASS':'BLOCK'}</b> ${r.audit_errors.join('; ')}<br>Open-weight auditor meta-models/muse-spark-open-1026 (Baseten): <b>${ow.status||'—'}</b> ${ow.detail||''} ${ow._cache?'(cache '+ow._cache+')':''}`;}
async function runSam(){if(!selCell)return alert('Select a cell first');$('#samBox').textContent='SAM 3.1 running (cached after first call)…';
 const r=await j(`/api/sam/${selCell.patient}/${selCell.date}/${selCell.cell}`);
 if(r.sam&&r.sam.status==='OK'){const svg=document.querySelector('#cellSvg');const poly=document.createElementNS('http://www.w3.org/2000/svg','polygon');
  poly.setAttribute('points',r.sam.polygon.map(p=>p.join(',')).join(' '));poly.setAttribute('fill','rgba(245,158,11,.18)');poly.setAttribute('stroke','#d97706');poly.setAttribute('stroke-width','1.5');svg.appendChild(poly);
  $('#samBox').innerHTML=`SAM 3.1 (amber) vs author contour (teal) · <b>IoU ${r.iou_vs_author}</b> · cache ${r.sam._cache}`;}
 else $('#samBox').innerHTML=`<span class="blocked">SAM 3.1 ${(r.sam&&r.sam.status)||'BLOCKED'}:</span> ${(r.sam&&r.sam.detail)||r.detail||''}`;}
async function runSpark(){if(!selCell)return alert('Select a cell first');$('#samBox').textContent='Muse Spark visual check running…';
 const r=await j(`/api/sparkcheck/${selCell.patient}/${selCell.date}/${selCell.cell}`);
 $('#samBox').innerHTML=r.status==='OK'?`<b>muse-spark-1.3 visual check</b> (cache ${r._cache}):<br>${r.text}`:`<span class="blocked">Muse Spark ${r.status}:</span> ${r.detail||''}`;}
document.addEventListener('click',e=>{if(e.target.id==='btnSam')runSam();if(e.target.id==='btnSpark')runSpark();});
async function tamper(mode){const p=pair();const r=await j('/api/tamper',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({patient:p.patient,from:p.from,to:p.to,mode})});
 $('#reportBox').textContent=r.report||JSON.stringify(r,null,1);
 const blocked=r.auditor_blocks_report||r.checker_blocks;
 $('#gateBox').innerHTML=`<span class="blocked">TAMPER SIMULATION (${r.tampered}): ${blocked?'BLOCKED':'NOT BLOCKED'}</span><br>${(r.auditor_errors||r.verify_errors||[]).join('<br>')}`;}
async function signoff(decision){signed=true;const p=pair(),note=$('#reviewNote').value.trim();
 await j('/api/signoff',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({patient:p.patient,from:p.from,to:p.to,decision,note})});
 $('#signoffState').innerHTML=`<b>${decision} by qualified researcher</b> (overlay review complete)${note?` — note saved: “${note.replace(/</g,'&lt;')}”`:''}. Required before any result is final.`}
init();
