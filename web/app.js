const $=s=>document.querySelector(s); let pairs=[],cur=null,queue=[],selCell=null,signed=false,activeReport=null,decisionMode='adj';
async function j(u,o){const r=await fetch(u,o);return r.json()}
function fmt(x){return (x>=0?"+":"")+Number(x).toFixed(4)}
function setText(el,lines){el.textContent='';(Array.isArray(lines)?lines:[lines]).forEach(t=>{const d=document.createElement('div');d.textContent=t;el.appendChild(d)})}
async function init(){
 const meta=await j('/api/meta');
 const badges=$('#liveBadges');badges.textContent='';
 Object.entries(meta.live).forEach(([k,v])=>{const s=document.createElement('span');const bold=document.createElement('b');bold.textContent=v;s.textContent=k+': ';s.appendChild(bold);badges.appendChild(s)});
 pairs=await j('/api/pairs');
 const pats=[...new Set(pairs.map(p=>p.patient))];
 const selP=$('#selPatient');selP.textContent='';pats.forEach(p=>{const o=document.createElement('option');o.textContent=p;selP.appendChild(o)});
 $('#selPatient').onchange=fillVisits; fillVisits(); renderPairs(); loadQueue(); updKappa();
 document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{document.querySelectorAll('nav button').forEach(x=>x.classList.remove('active'));b.classList.add('active');document.querySelectorAll('main section').forEach(s=>s.hidden=true);$('#view-'+b.dataset.view).hidden=false;});
 $('#selFrom').onchange=$('#selTo').onchange=showPair;
 $('#btnHealthy').onclick=()=>rate(0); $('#btnUnhealthy').onclick=()=>rate(1);
 $('#btnReport').onclick=genReport;
 $('#btnTamperNumber').onclick=()=>tamper('number'); $('#btnTamperAdvice').onclick=()=>tamper('advice'); $('#btnTamperPayload').onclick=()=>tamper('payload');
 $('#btnApprove').onclick=()=>signoff('Approved');
 $('#btnFlag').onclick=()=>signoff('Flagged');
 $('#btnNaive').onclick=()=>{decisionMode='naive';$('#btnNaive').classList.add('active');$('#btnAdj').classList.remove('active');showPair()};
 $('#btnAdj').onclick=()=>{decisionMode='adj';$('#btnAdj').classList.add('active');$('#btnNaive').classList.remove('active');showPair()};
 $('#btnDictate').onclick=dictate;
 loadBenchmark();
}
async function loadBenchmark(){try{const b=await j('/api/benchmark');
 if(b.status==='NOT_RUN'){setText($('#benchmarkCard'),'Live multi-model benchmark: not run yet — uv run python src/run_live_benchmark.py');return}
 setText($('#benchmarkCard'),['Live multi-model benchmark (cached real-data run, details in docs/LIVE_BENCHMARK.md)',`SAM 3.1 IoU vs author: mean ${b.sam_iou_mean} · median ${b.sam_iou_median} · range ${b.sam_iou_min}–${b.sam_iou_max} · ≥0.80: ${b.sam_iou_ge80_frac} (n=${b.sam_ok})`,'Structured Spark second rater: see docs/RATERS.md (keyword agreement figure removed as invalid)',`Cloud vs Open-Weight audit parity: ${b.parity_n}/${b.pairs_n} pairs`]);}catch(e){$('#benchmarkCard').textContent='Live benchmark: unavailable ('+e+')'}}
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
 else $('#voiceState').textContent=`Voice ${r.status}: ${r.detail||''} — type the note instead.`}
function visits(){return [...new Set(pairs.filter(p=>p.patient===$('#selPatient').value).flatMap(p=>[p.from,p.to]))]}
function fillOpts(el,vals){el.textContent='';vals.forEach(x=>{const o=document.createElement('option');o.textContent=x;el.appendChild(o)})}
function fillVisits(){const v=visits();fillOpts($('#selFrom'),v);fillOpts($('#selTo'),v);if(v.length>1)$('#selTo').selectedIndex=1;showPair()}
function pair(){return pairs.find(p=>p.patient===$('#selPatient').value&&p.from===$('#selFrom').value&&p.to===$('#selTo').value)}
function showPair(){cur=pair();activeReport=null; if(!cur){$('#pairContext').textContent='No such consecutive pair — select a patient and visits.';setText($('#decisionCard'),'No pair selected.');return}
 setText($('#pairContext'),[`${cur.patient} ${cur.from} → ${cur.to} · Treatment: ${cur.treatment}`,`Δ raw ${fmt(cur.delta_raw)} · Δ flow-adjusted ${fmt(cur.delta_adj)} · RCV95 ${Number(cur.RCV95).toFixed(4)} · Decision: ${cur.decision}`]);
 const naiveDecision=Math.abs(cur.delta_raw)>Number(cur.RCV95)?'exceeds_RCV (naive, raw vs RCV95)':'within_RCV (naive)';
 const decLines=decisionMode==='naive'
  ? [`${cur.patient} ${cur.from} → ${cur.to} (${cur.treatment}) — Naive view`,`Raw change: ${fmt(cur.delta_raw)} read at face value against RCV95 ±${Number(cur.RCV95).toFixed(4)}`,`Naive call: ${naiveDecision}`,`Frozen flow-adjusted decision: ${cur.decision} — toggle to Flow-adjusted for the signed decision.`]
  : [`${cur.patient} ${cur.from} → ${cur.to} (${cur.treatment}) — Flow-adjusted view`,`Raw change: ${fmt(cur.delta_raw)}`,`Flow-adjusted change: ${fmt(cur.delta_adj)}`,`RCV95 band: ±${Number(cur.RCV95).toFixed(4)}`,`Decision: ${cur.decision}`];
 if(cur.decision==='indeterminate_QC')decLines.push('QC-blocked: degraded skip rate / low kept cells — system refuses to decide.');
 setText($('#decisionCard'),decLines);
 signed=false;$('#signoffState').textContent='Not reviewed';$('#reportBox').textContent='';setText($('#gateBox'),'');renderChart();}
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
 $('#planOut').textContent=`${runs} runs/visit (${runs*cells} cells) → MDC95 ≈ ${achieved.toFixed(3)} (target ${target})`;}
document.addEventListener('click',e=>{if(e.target.id==='btnPlan')planner()});
function renderPairs(){$('#pairsTable').innerHTML='<table><tr><th>Pair</th><th>Δ raw</th><th>Δ adj</th><th>Decision</th></tr>'+pairs.map(p=>`<tr><td>${p.patient} ${p.from}→${p.to}</td><td>${fmt(p.delta_raw)}</td><td>${fmt(p.delta_adj)}</td><td>${p.decision}</td></tr>`).join('')+'</table>'}
async function loadQueue(){queue=await j('/api/queue');
 const list=$('#queueList');list.textContent='';
 queue.slice(0,200).forEach((q,i)=>{const d=document.createElement('div');d.className='qitem';d.dataset.i=i;d.textContent=`${q.has_frame?'[REAL FRAME] ':''}${q.patient} ${q.visit} cell ${q.cell} · author health=${q.health} · pred=${q.pred} · conf=${Number(q.confidence).toFixed(2)}`;list.appendChild(d)});
 document.querySelectorAll('.qitem').forEach(el=>el.onclick=()=>selectCell(queue[+el.dataset.i]));
 if(queue.length)selectCell(queue[0]);}
function clearOverlays(){$('#cellPoly').setAttribute('points','');$('#stripPoly').setAttribute('points','');
 document.querySelectorAll('#cellSvg polygon:not(#cellPoly)').forEach(p=>p.remove());$('#samBox').textContent='';}
async function selectCell(q){selCell=q;clearOverlays();
 document.querySelectorAll('.qitem').forEach(el=>el.classList.toggle('active',queue[+el.dataset.i]===q));
 const c=await j(`/api/cell/${q.patient}/${q.date}/${q.cell}`);
 const info=await j(`/api/frameinfo/${q.patient}/${q.date}/${q.cell}`);
 const fh=info.frame_height||48, fw=info.frame_width||1280;
 $('#cellSvg').setAttribute('viewBox',`0 0 200 ${fh}`);$('#stripSvg').setAttribute('viewBox',`0 0 ${fw} ${fh}`);
 if(info.contour_crop){$('#cellPoly').setAttribute('points',info.contour_crop.map(p=>p.join(',')).join(' '));
  $('#stripPoly').setAttribute('points',(info.contour_full||[]).map(p=>p.join(',')).join(' '));
  $('#cropImg').src=`/api/frame/${q.patient}/${q.date}/${q.cell}/crop.png`; $('#stripImg').src=`/api/frame/${q.patient}/${q.date}/${q.cell}/strip.png`;
  setText($('#cellInfo'),[`${q.patient} ${q.visit} cell ${q.cell} · REAL FRAME ${info.frame} (pos_x ${info.pos_x})`,`Author health=${q.health} · Classifier pred=${q.pred} (conf ${Number(q.confidence).toFixed(2)})`,`Frames tracked: ${c.n_frames??'—'} — judge spicules on the grayscale crop, not the outline.`]);}
 else{clearOverlays();setText($('#cellInfo'),[`${q.patient} ${q.visit} cell ${q.cell}`,`Author health=${q.health} · Classifier pred=${q.pred} (conf ${Number(q.confidence).toFixed(2)})`,'Real frame not extracted for this cell yet (sample: P1 0w M10 cells 4, 11, 19).']);$('#cropImg').removeAttribute('src');$('#stripImg').removeAttribute('src');}}
async function rate(v){if(!selCell)return alert('Select a cell first');await j('/api/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({patient:selCell.patient,date:selCell.date,cell:selCell.cell,rater:v})});updKappa()}
async function updKappa(){const k=await j('/api/kappa');setText($('#kappaBox'),k.n?[`Second-rater labels: ${k.reviews} · vs author n=${k.n}`,`Agreement ${k.agreement} · Cohen κ ${k.kappa} · Gwet AC1 ${k.ac1}`]:'No second-rater labels yet — label cells to compute κ / AC1.')}
async function genReport(){const p=pair();if(!p){setText($('#gateBox'),'Select a valid visit pair first.');return}
 const r=await j(`/api/report/${p.patient}/${p.from}/${p.to}`);
 $('#reportBox').textContent=r.report||'';
 activeReport=r.envelope?{payload_sha256:r.envelope.payload.payload_sha256,report_sha256:r.envelope.payload.report_sha256}:null;
 signed=false;$('#signoffState').textContent=activeReport?'Not reviewed — report generated, awaiting sign-off':'Not reviewed';
 const ow=r.open_weight||{};
 setText($('#gateBox'),['Cloud vs Open-Weight verification',`Cloud muse-spark-1.3 narrative: ${r.narrative_source} · Checker: ${r.verified?'PASS':'FAIL'} ${(r.verify_errors||[]).join('; ')}`,`Local rule auditor: ${r.audit_ok?'PASS':'BLOCK'} ${(r.audit_errors||[]).join('; ')}`,`Open-weight auditor meta-models/muse-spark-open (Baseten): ${ow.status||'—'} ${ow.detail||''} ${ow._cache?'(cache '+ow._cache+')':''}`]);}
async function runSam(){if(!selCell)return alert('Select a cell first');$('#samBox').textContent='SAM 3.1 running (cached after first call)…';
 const r=await j(`/api/sam/${selCell.patient}/${selCell.date}/${selCell.cell}`);
 if(r.sam&&r.sam.status==='OK'){const svg=document.querySelector('#cellSvg');const poly=document.createElementNS('http://www.w3.org/2000/svg','polygon');
  poly.setAttribute('points',r.sam.polygon.map(p=>p.join(',')).join(' '));poly.setAttribute('fill','rgba(245,158,11,.18)');poly.setAttribute('stroke','#d97706');poly.setAttribute('stroke-width','1.5');svg.appendChild(poly);
  $('#samBox').textContent=`SAM 3.1 (amber) vs author contour (teal) · IoU ${r.iou_vs_author} · cache ${r.sam._cache}`;}
 else $('#samBox').textContent=`SAM 3.1 ${(r.sam&&r.sam.status)||'BLOCKED'}: ${(r.sam&&r.sam.detail)||r.detail||''}`;}
async function runSpark(){if(!selCell)return alert('Select a cell first');$('#samBox').textContent='Muse Spark visual check running…';
 const r=await j(`/api/sparkcheck/${selCell.patient}/${selCell.date}/${selCell.cell}`);
 setText($('#samBox'),r.status==='OK'?[`muse-spark-1.3 visual check (cache ${r._cache}):`,r.text||'']:`Muse Spark ${r.status}: ${r.detail||''}`);}
document.addEventListener('click',e=>{if(e.target.id==='btnSam')runSam();if(e.target.id==='btnSpark')runSpark();});
async function tamper(mode){const p=pair();if(!p){setText($('#gateBox'),'Select a valid visit pair first.');return}
 activeReport=null;const r=await j('/api/tamper',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({patient:p.patient,from:p.from,to:p.to,mode})});
 $('#reportBox').textContent=r.report||JSON.stringify(r,null,1);
 const blocked=r.auditor_blocks_report||r.checker_blocks;
 setText($('#gateBox'),[`TAMPER SIMULATION (${r.tampered}): ${blocked?'BLOCKED':'NOT BLOCKED'}`,...((r.auditor_errors||r.verify_errors||[]))]);
 $('#signoffState').textContent='Not reviewed — tampered view is not signable. Generate a fresh verified report.';}
async function signoff(decision){const p=pair();if(!p){$('#signoffState').textContent='Select a valid visit pair first.';return}
 if(!activeReport){$('#signoffState').textContent='Generate a verified report first — sign-off is bound to its hashes.';return}
 const note=$('#reviewNote').value.trim();
 const r=await j('/api/signoff',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({patient:p.patient,from:p.from,to:p.to,decision,note,payload_sha256:activeReport.payload_sha256,report_sha256:activeReport.report_sha256})});
 if(r.error){$('#signoffState').textContent='Sign-off rejected: '+r.error;return}
 signed=true;
 $('#signoffState').textContent=`Signed for ${activeReport.payload_sha256.slice(0,12)} — ${decision} by qualified researcher (overlay review complete)${note?` — note saved: “${note}”`:''}. Required before any result is final.`}
init();
