const COLORS={market:'#2f67a6',size:'#6f5499',value:'#c2413a',momentum:'#b76b13',quality:'#16795a',tech:'#202b26'};
const LABELS={market:'市场',size:'规模',value:'价值代理',momentum:'动量',quality:'防御代理',tech:'科技'};
const METHOD_OPTIONS=[{id:'RBSA-6',label:'6 月收益风格',source:'Sharpe (1992)'},{id:'RBSA-12',label:'12 月收益风格',source:'Sharpe (1992)'},{id:'RBSA-18',label:'18 月收益风格',source:'Sharpe (1992)'},{id:'HOLDINGS',label:'季度持仓集中度',source:'Chan et al. (2002)'}];
const IS_STATIC_HOST=location.hostname.endsWith('github.io')||location.protocol==='file:';
let state=null,researchState=null,currentMode='analysis',activeFactors=new Set(['market','size','value','tech']),activeKgTypes=new Set(),selectedKgNode=null;

const $=id=>document.getElementById(id);
function setText(id,value){$(id).textContent=value}
function formatDelta(v){return `${v>=0?'+':''}${v.toFixed(3)}`}

async function loadAnalysis(){
  document.body.classList.add('loading'); $('refresh').disabled=true;
  const fundId=$('fund-id').value.trim()||'159552';
  try{if(IS_STATIC_HOST&&fundId!=='159552')throw new Error('GitHub Pages 为 159552 真实数据快照；任意基金分析请运行本地 Python 服务');const url=IS_STATIC_HOST?'data/analysis-159552.json':`/api/analysis?fund_id=${encodeURIComponent(fundId)}`;const res=await fetch(url,{cache:'no-store'}); if(!res.ok)throw new Error(`HTTP ${res.status}`); state=await res.json(); render();}
  catch(err){setText('engine','运行失败'); setText('hypothesis',`无法加载分析：${err.message}`);}
  finally{document.body.classList.remove('loading'); $('refresh').disabled=false;}
}

async function loadResearch(){
  document.body.classList.add('loading'); $('refresh').disabled=true;
  const fundId=$('fund-id').value.trim()||'159552';
  try{const prompt=$('harness-prompt')?.value.trim()||'',methods=[...document.querySelectorAll('#method-options input:checked')].map(x=>x.value);if(!methods.length)throw new Error('请至少选择一种知识图谱研究方法');if(IS_STATIC_HOST&&fundId!=='159552')throw new Error('GitHub Pages 为 159552 真实数据快照；任意基金分析请运行本地 Python 服务');const res=await fetch(IS_STATIC_HOST?'data/research-159552.json':'/api/harness',IS_STATIC_HOST?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fund_id:fundId,prompt,methods}),cache:'no-store'});if(!res.ok){const body=await res.json().catch(()=>({}));throw new Error(body.error||`HTTP ${res.status}`)}researchState=await res.json();if(IS_STATIC_HOST)applyStaticSelection(researchState,methods,prompt);renderResearch();}
  catch(err){setText('research-title','研究运行失败');setText('research-question',err.message);}
  finally{document.body.classList.remove('loading');$('refresh').disabled=false;}
}

function applyStaticSelection(payload,methods,prompt){const r=payload.report,c=r.method_comparison;c.methods=c.methods.filter(m=>methods.includes(m.id));c.selected_ids=methods;const completed=c.methods.filter(m=>m.result.status==='completed'),signals=completed.map(m=>m.result.drift_detected),share=signals.length?signals.filter(Boolean).length/signals.length:0;c.review.completed=completed.length;c.review.not_testable=c.methods.length-completed.length;c.review.drift_vote_share=Number(share.toFixed(3));c.review.consensus=share>=.67?'drift':share<=.33?'no_drift':'mixed';const selected=new Set(methods),allMethods=new Set(METHOD_OPTIONS.map(m=>m.id));r.knowledge_graph.nodes=r.knowledge_graph.nodes.filter(n=>!allMethods.has(n.id)||selected.has(n.id));const ids=new Set(r.knowledge_graph.nodes.map(n=>n.id));r.knowledge_graph.edges=r.knowledge_graph.edges.filter(e=>ids.has(e.source)&&ids.has(e.target));r.harness.prompt=prompt;r.harness.stages[1].summary=`运行 ${c.methods.length} 种图谱方法与 ${r.experiments.length} 项实验`;r.harness.stages[1].evidence_ids=methods;r.harness.stages[2].summary=`方法共识 ${c.review.consensus}；不可检验 ${c.review.not_testable} 项；失败假设 ${r.failed_hypotheses.length} 项`}

function switchMode(mode){
  currentMode=mode;const isAnalysis=mode==='analysis';
  $('analysis-view').hidden=!isAnalysis;$('research-view').hidden=isAnalysis;
  $('mode-analysis').classList.toggle('active',isAnalysis);$('mode-research').classList.toggle('active',!isAnalysis);
  $('mode-analysis').setAttribute('aria-selected',String(isAnalysis));$('mode-research').setAttribute('aria-selected',String(!isAnalysis));
  if(isAnalysis){if(!state)loadAnalysis();else requestAnimationFrame(drawAll)}else if(!researchState)loadResearch();
}

function renderResearch(){
  const r=researchState.report;
  const isPublic=r.version.data.public_data_connected;setText('data-badge',isPublic?'公开真实数据':'验证数据');setText('data-note',isPublic?(IS_STATIC_HOST?'GitHub Pages：159552 真实公开数据快照；因子为 ETF 代理模型，动态分析需运行本地服务。':'已接入公开净值、季度持仓和规模页面；因子为 ETF 代理模型，资金流仍是数据缺口。'):'当前为可重复生成的合成样本，不构成真实市场结论或投资建议。');
  setText('research-title',r.title);setText('research-question',r.research_question);setText('hypothesis-count',String(r.hypotheses.length));
  $('literature-list').innerHTML=r.literature.map(x=>`<article class="literature-item"><header><b>${x.citation_id}</b><span>${x.authors} · ${x.year}</span></header><h3>${x.title}</h3><dl><div><dt>测度</dt><dd>${x.extracted.measure}</dd></div><div><dt>机制</dt><dd>${x.extracted.mechanism}</dd></div><div><dt>局限</dt><dd>${x.extracted.limitation}</dd></div></dl></article>`).join('');
  $('gap-list').innerHTML=r.gaps.map(g=>`<div class="gap-item"><b>${g.id}</b><span>${g.gap}</span><em>${g.priority}优先级</em></div>`).join('');
  $('hypothesis-list').innerHTML=r.hypotheses.map(h=>`<li><b>${h.id}</b>：${h.statement}<span class="hypothesis-state ${h.status}">${h.status}</span></li>`).join('');
  $('experiment-list').innerHTML=r.experiments.map(e=>`<article class="experiment"><span>${e.id}</span><h3>${e.question}</h3><p>${e.method}</p><pre>${JSON.stringify(e.result,null,2)}</pre></article>`).join('');
  $('binding-list').innerHTML=r.evidence_bindings.map(x=>`<div class="binding-row"><b>${x.claim_id}</b><span>${x.claim}<br><code>${x.evidence_ids.join(' · ')}</code></span><em class="audit-state ${x.status==='supported'?'ok':''}">${x.status}</em></div>`).join('');
  $('citation-list').innerHTML=r.citation_audit.map(x=>`<div class="citation-row"><b>${x.citation_id.replace('CIT-','')}</b><span><code>${x.doi}</code><br>${x.verification_status}</span><em class="audit-state ${x.doi_format_valid&&x.metadata_complete?'ok':''}">${x.doi_format_valid&&x.metadata_complete?'格式通过':'待修复'}</em></div>`).join('');
  const version=r.version;$('version-info').innerHTML=`<div>code: ${version.code.environment_version}</div><div>data: ${version.data.dataset_version}</div><div>schema: ${version.data.schema_sha256}</div>${r.data_manifest.map(x=>`<div class="manifest-row"><b>${x.dataset_id}</b><span>${x.source}</span><em>${x.status}</em></div>`).join('')}`;
  const cost=r.reproduction_cost;$('cost-info').innerHTML=`<div>runtime: ${cost.runtime_seconds}s</div><div>LLM calls: ${cost.llm_calls}</div><div>network calls: ${cost.network_calls}</div><div>external API cost: ¥${cost.external_api_cost.toFixed(2)}</div><div>${cost.cost_note}</div>`;
  setText('research-conclusion',r.conclusion.interpretation);$('limitation-list').innerHTML=r.limitations.map(x=>`<li>${x}</li>`).join('');
  renderKnowledgeGraph(r.knowledge_graph);
  renderHarness(r.harness);
  renderMethodComparison(r.method_comparison);
  renderDataAudit(r.data_audit||[]);
  setText('footer-run',`自主研究完成 · ${new Date().toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}`);
}

function renderDataAudit(rows){$('data-audit-list').innerHTML=rows.map(row=>`<div class="data-audit-row"><b>${row.id}</b><em class="data-kind ${row.kind}">${row.kind}</em><span>${row.source}<small>${row.instrument}</small></span><span>${row.start&&row.end?`${row.start} → ${row.end} · `:''}${row.observations} 条</span><code>${row.sha256?row.sha256.slice(0,12):'—'}</code></div>`).join('')}

function renderMethodOptions(){if(!$('method-options'))return;$('method-options').innerHTML=METHOD_OPTIONS.map(m=>`<label><input type="checkbox" value="${m.id}" checked><span><b>${m.label}</b><small>${m.id} · ${m.source}</small></span></label>`).join('')}
function renderMethodComparison(comparison){
  if(!comparison)return;const review=comparison.review;setText('method-consensus',`共识：${review.consensus} · 可运行 ${review.completed}/${comparison.methods.length}`);setText('method-warning',review.warning);
  $('method-results').innerHTML=comparison.methods.map(method=>{const x=method.result,completed=x.status==='completed';return `<article class="method-result"><header><span>${method.id}</span><em class="audit-state ${completed?'ok':''}">${x.status}</em></header><h3>${method.label}</h3><p>${completed?`信号：${x.drift_detected?'检测到漂移':'未检测到漂移'} · 方向 ${x.direction} · 样本 ${x.n_observations}`:x.reason}</p><dl><div><dt>效应量</dt><dd>${completed&&x.effect_delta!==undefined?x.effect_delta:'—'}</dd></div><div><dt>变化点</dt><dd>${completed&&x.change_points?.length?x.change_points.map(p=>p.date).join('、'):'未检出'}</dd></div></dl><small>${method.limitation}</small></article>`}).join('');
}

function renderHarness(harness){
  if(!harness)return;setText('harness-status',harness.status==='completed'?'已完成':'运行中');
  $('harness-stages').innerHTML=harness.stages.map((stage,index)=>`<article class="harness-stage ${stage.status}"><div class="harness-stage-index">0${index+1}</div><div class="harness-stage-main"><div><b>${stage.title}</b><span>${stage.status}</span></div><p>${stage.summary}</p><code>${stage.evidence_ids.slice(0,5).join(' · ')}</code></div></article>`).join('');
}

const KG_LABELS={literature:'文献',measure:'测度',method:'方法',mechanism:'机制',limitation:'局限',gap:'研究缺口',hypothesis:'假设',experiment:'实验',dataset:'数据',conclusion:'结论'};
const KG_COLORS={literature:'#2f67a6',measure:'#527da5',method:'#206c78',mechanism:'#6f5499',limitation:'#b76b13',gap:'#8b6a23',hypothesis:'#16795a',experiment:'#267762',dataset:'#56635c',conclusion:'#c2413a'};
const SVG_NS='http://www.w3.org/2000/svg';

function svgElement(name,attrs={}){const el=document.createElementNS(SVG_NS,name);Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,v));return el}
function kgLayer(node){if(node.id.startsWith('LIMIT-'))return 4;return {literature:0,measure:1,mechanism:1,limitation:1,gap:1,dataset:1,method:2,hypothesis:2,experiment:3,conclusion:4}[node.type]??2}
function shortLabel(node){const value=node.type==='literature'?node.id.replace('CIT-',''):node.label;return value.length>23?`${value.slice(0,22)}…`:value}

function renderKnowledgeGraph(graph){
  if(!graph)return;
  const types=[...new Set(graph.nodes.map(node=>node.type))];
  if(!activeKgTypes.size)types.forEach(type=>activeKgTypes.add(type));
  const filters=$('kg-filters');filters.replaceChildren();
  types.forEach(type=>{const button=document.createElement('button');button.type='button';button.dataset.type=type;button.className=activeKgTypes.has(type)?'active':'';button.textContent=KG_LABELS[type]||type;button.onclick=()=>{activeKgTypes.has(type)?activeKgTypes.delete(type):activeKgTypes.add(type);selectedKgNode=null;renderKnowledgeGraph(graph)};filters.append(button)});
  const reset=document.createElement('button');reset.type='button';reset.className='kg-reset';reset.textContent='全部';reset.onclick=()=>{activeKgTypes=new Set(types);selectedKgNode=null;renderKnowledgeGraph(graph)};filters.append(reset);
  const visible=graph.nodes.filter(node=>activeKgTypes.has(node.type)),visibleIds=new Set(visible.map(node=>node.id));
  const edges=graph.edges.filter(edge=>visibleIds.has(edge.source)&&visibleIds.has(edge.target));
  setText('kg-summary',`${visible.length} 个节点 · ${edges.length} 条关系 · ${graph.meta.data_version}`);
  const columns=Array.from({length:5},()=>[]);visible.forEach(node=>columns[kgLayer(node)].push(node));
  const width=1120,rowHeight=53,padY=42,height=Math.max(430,Math.max(...columns.map(column=>column.length))*rowHeight+padY*2);
  const svg=$('knowledge-graph');svg.replaceChildren();svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.setAttribute('height',height);
  const headings=['文献证据','概念与数据','可检验假设','实验验证','结论边界'],positions=new Map();
  columns.forEach((column,col)=>{const x=28+col*220,offset=(height-column.length*rowHeight)/2;column.forEach((node,row)=>positions.set(node.id,{x,y:offset+row*rowHeight,w:176,h:34}));const title=svgElement('text',{x:x+88,y:22,class:'kg-column-title','text-anchor':'middle'});title.textContent=headings[col];svg.append(title)});
  edges.forEach(edge=>{const a=positions.get(edge.source),b=positions.get(edge.target);svg.append(svgElement('path',{d:`M ${a.x+a.w} ${a.y+a.h/2} C ${a.x+a.w+45} ${a.y+a.h/2}, ${b.x-45} ${b.y+b.h/2}, ${b.x} ${b.y+b.h/2}`,class:'kg-edge','data-source':edge.source,'data-target':edge.target,'data-relation':edge.relation}))});
  visible.forEach(node=>{const p=positions.get(node.id),group=svgElement('g',{class:'kg-node',role:'button',tabindex:'0','data-id':node.id,'aria-label':`${KG_LABELS[node.type]||node.type}：${node.label}`}),rect=svgElement('rect',{x:p.x,y:p.y,width:p.w,height:p.h,rx:4,fill:KG_COLORS[node.type]||'#56635c'}),id=svgElement('text',{x:p.x+9,y:p.y+13,class:'kg-node-id'}),label=svgElement('text',{x:p.x+9,y:p.y+27,class:'kg-node-label'});id.textContent=node.id;label.textContent=shortLabel(node);group.append(rect,id,label);group.onclick=()=>selectKgNode(graph,node.id);group.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();selectKgNode(graph,node.id)}};svg.append(group)});
  $('kg-legend').innerHTML=[...new Set(edges.map(edge=>edge.relation))].map(relation=>`<span><i></i>${relation}</span>`).join('');
  if(selectedKgNode&&visibleIds.has(selectedKgNode))selectKgNode(graph,selectedKgNode);else renderKgInspector(graph,null);
}

function selectKgNode(graph,nodeId){
  selectedKgNode=nodeId;const linked=new Set([nodeId]);graph.edges.forEach(edge=>{if(edge.source===nodeId)linked.add(edge.target);if(edge.target===nodeId)linked.add(edge.source)});
  $('knowledge-graph').querySelectorAll('.kg-node').forEach(node=>node.classList.toggle('dimmed',!linked.has(node.dataset.id)));
  $('knowledge-graph').querySelectorAll('.kg-edge').forEach(edge=>{const active=edge.dataset.source===nodeId||edge.dataset.target===nodeId;edge.classList.toggle('active',active);edge.classList.toggle('dimmed',!active)});
  renderKgInspector(graph,graph.nodes.find(node=>node.id===nodeId));
}

function renderKgInspector(graph,node){
  const inspector=$('kg-inspector');inspector.replaceChildren();const eyebrow=document.createElement('p'),title=document.createElement('h3');eyebrow.textContent=node?(KG_LABELS[node.type]||node.type).toUpperCase():'NODE INSPECTOR';title.textContent=node?node.id:'选择一个节点';inspector.append(eyebrow,title);
  if(!node){const hint=document.createElement('span');hint.textContent='点击节点查看证据、状态与版本信息。';inspector.append(hint);return}
  const label=document.createElement('div');label.className='kg-inspector-label';label.textContent=node.label;inspector.append(label);
  const details=document.createElement('dl');Object.entries(node.details||{}).forEach(([key,value])=>{const row=document.createElement('div'),dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=key;dd.textContent=typeof value==='object'?JSON.stringify(value):String(value);row.append(dt,dd);details.append(row)});inspector.append(details);
  const links=graph.edges.filter(edge=>edge.source===node.id||edge.target===node.id),relation=document.createElement('div');relation.className='kg-neighbors';relation.textContent=links.length?links.map(edge=>`${edge.source===node.id?'→':'←'} ${edge.relation} · ${edge.source===node.id?edge.target:edge.source}`).join('\n'):'无直接关系';inspector.append(relation);
  const version=document.createElement('code');version.textContent=`code ${graph.meta.code_version} · data ${graph.meta.data_version} · schema ${graph.meta.schema_sha256}`;inspector.append(version);
}

function render(){
  const {meta,report,nodes}=state, cp=report.change_points[0];
  const isPublic=meta.data_source==='eastmoney_public';setText('data-badge',isPublic?'公开真实数据':'验证数据');setText('data-note',isPublic?`来源：东方财富公开页面 · ${meta.factor_model} · 非官方稳定 API，不构成投资建议。`:'当前为可重复生成的合成 A 股科技基金样本，不构成真实市场结论或投资建议。');
  setText('engine',`${meta.engine} · 已连接`); setText('dataset',meta.dataset); setText('period',meta.period);
  setText('graph-label',meta.graph); setText('change-date',cp?.date??'未检出'); setText('change-score',cp?`变化强度 z = ${cp.z}`:'没有持续性变化');
  setText('distance-pre',report.distance.pre.toFixed(3)); setText('distance-post',report.distance.post.toFixed(3));
  const pct=(report.distance.post/report.distance.pre-1)*100; setText('distance-change',`较前期 ${pct>=0?'+':''}${pct.toFixed(1)}%`);
  setText('robust-status',report.robustness.positive_drift?'支持漂移':'不支持漂移');
  setText('hypothesis',report.attribution.leading_hypothesis); setText('causal-status',report.attribution.causal_status);
  setText('footer-run',`最近运行 · ${new Date().toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}`);
  $('workflow').innerHTML=nodes.map((n,i)=>`<div class="node done"><span class="node-index">${String(i+1).padStart(2,'0')}</span><strong>${n.label}</strong><small>${n.detail}</small></div>`).join('');
  $('evidence-list').innerHTML=report.attribution.evidence.map(x=>`<span>${x}</span>`).join('');
  renderTabs(); renderComparison(); drawAll();
}

function renderTabs(){
  $('factor-tabs').innerHTML=Object.keys(LABELS).map(key=>`<button type="button" data-factor="${key}" class="${activeFactors.has(key)?'active':''}">${LABELS[key]}</button>`).join('');
  $('factor-tabs').querySelectorAll('button').forEach(btn=>btn.onclick=()=>{const k=btn.dataset.factor;if(activeFactors.has(k)&&activeFactors.size>1)activeFactors.delete(k);else activeFactors.add(k);renderTabs();drawExposure();});
}

function renderComparison(){
  const pre=state.report.mean_exposure_pre,post=state.report.mean_exposure_post;
  $('comparison-rows').innerHTML=Object.keys(LABELS).map(k=>{const d=post[k]-pre[k];return `<div class="comparison-row"><span>${LABELS[k]}</span><span>${pre[k].toFixed(3)}</span><span>${post[k].toFixed(3)}</span><span class="${d>=0?'delta-up':'delta-down'}">${formatDelta(d)}</span></div>`}).join('');
}

function setupCanvas(canvas){const rect=canvas.getBoundingClientRect(),dpr=window.devicePixelRatio||1;canvas.width=rect.width*dpr;canvas.height=rect.height*dpr;const ctx=canvas.getContext('2d');ctx.scale(dpr,dpr);return {ctx,w:rect.width,h:rect.height};}
function scales(rows,keys,w,h){const p={l:42,r:14,t:16,b:30};let vals=rows.flatMap(r=>keys.map(k=>r[k]));let min=Math.min(...vals),max=Math.max(...vals);const pad=(max-min||1)*.12;min-=pad;max+=pad;return {p,x:i=>p.l+i*(w-p.l-p.r)/(rows.length-1),y:v=>p.t+(max-v)*(h-p.t-p.b)/(max-min),min,max};}
function grid(ctx,w,h,s){ctx.strokeStyle='#e2e7e3';ctx.fillStyle='#77817c';ctx.lineWidth=1;ctx.font='10px Segoe UI';ctx.textAlign='left';for(let i=0;i<5;i++){const y=s.p.t+i*(h-s.p.t-s.p.b)/4;ctx.beginPath();ctx.moveTo(s.p.l,y);ctx.lineTo(w-s.p.r,y);ctx.stroke();const v=s.max-i*(s.max-s.min)/4;ctx.fillText(v.toFixed(1),4,y+3)}ctx.textAlign='center';[['2022',1],['2023',13],['2024',25],['2025',37]].forEach(([label,index])=>ctx.fillText(label,s.x(index),h-8));ctx.textAlign='left'}
function line(ctx,rows,key,s,color){ctx.strokeStyle=color;ctx.lineWidth=2;ctx.beginPath();rows.forEach((r,i)=>{const x=s.x(i),y=s.y(r[key]);i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke()}

function drawExposure(){if(!state)return;const canvas=$('exposure-chart'),{ctx,w,h}=setupCanvas(canvas),rows=state.exposure,keys=[...activeFactors],s=scales(rows,keys,w,h);grid(ctx,w,h,s);keys.forEach(k=>line(ctx,rows,k,s,COLORS[k]));bindTooltip(canvas,$('exposure-tooltip'),rows,s,(r)=>keys.map(k=>`${LABELS[k]} ${r[k].toFixed(2)}`).join(' · '));}
function drawDistance(){if(!state)return;const canvas=$('distance-chart'),{ctx,w,h}=setupCanvas(canvas),rows=state.distance,s=scales(rows,['value'],w,h);grid(ctx,w,h,s);ctx.fillStyle='#e7f3ed';ctx.beginPath();ctx.moveTo(s.x(0),s.y(rows[0].value));rows.forEach((r,i)=>ctx.lineTo(s.x(i),s.y(r.value)));ctx.lineTo(s.x(rows.length-1),h-s.p.b);ctx.lineTo(s.x(0),h-s.p.b);ctx.fill();line(ctx,rows,'value',s,'#16795a');const cp=state.report.change_points[0];if(cp){const i=rows.findIndex(r=>r.date===cp.date);ctx.strokeStyle='#c2413a';ctx.setLineDash([4,4]);ctx.beginPath();ctx.moveTo(s.x(i),s.p.t);ctx.lineTo(s.x(i),h-s.p.b);ctx.stroke();ctx.setLineDash([])}bindTooltip(canvas,$('distance-tooltip'),rows,s,r=>`漂移距离 ${r.value.toFixed(3)}`);}
function bindTooltip(canvas,tip,rows,s,format){canvas.onmousemove=e=>{const rect=canvas.getBoundingClientRect();const i=Math.max(0,Math.min(rows.length-1,Math.round((e.clientX-rect.left-s.p.l)/(rect.width-s.p.l-s.p.r)*(rows.length-1))));tip.style.display='block';tip.style.left=`${Math.min(rect.width-190,Math.max(8,e.clientX-rect.left+12))}px`;tip.style.top=`${Math.max(8,e.clientY-rect.top-35)}px`;tip.textContent=`${rows[i].date} · ${format(rows[i])}`};canvas.onmouseleave=()=>tip.style.display='none';}
function drawAll(){drawExposure();drawDistance()}

$('mode-analysis').onclick=()=>switchMode('analysis');$('mode-research').onclick=()=>switchMode('research');
$('fund-form').onsubmit=e=>{e.preventDefault();researchState=null;currentMode==='analysis'?loadAnalysis():loadResearch()};
$('harness-form').onsubmit=e=>{e.preventDefault();researchState=null;loadResearch()};
$('refresh').onclick=()=>currentMode==='analysis'?loadAnalysis():loadResearch();window.addEventListener('resize',()=>requestAnimationFrame(drawAll));loadAnalysis();
renderMethodOptions();
