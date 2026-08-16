const COLORS={market:'#2f67a6',size:'#6f5499',value:'#c2413a',momentum:'#b76b13',quality:'#16795a',tech:'#202b26'};
const LABELS={market:'市场',size:'规模',value:'价值代理',momentum:'动量',quality:'防御代理',tech:'科技'};
const METHOD_OPTIONS=[{id:'RBSA-6',label:'6 月收益风格',source:'Sharpe (1992)'},{id:'RBSA-12',label:'12 月收益风格',source:'Sharpe (1992)'},{id:'RBSA-18',label:'18 月收益风格',source:'Sharpe (1992)'},{id:'HOLDINGS',label:'季度持仓集中度',source:'Chan et al. (2002)'}];
const IS_STATIC_HOST=location.hostname.endsWith('github.io')||location.protocol==='file:';
let state=null,researchState=null,discoveryState=null,currentMode='analysis',activeFactors=new Set(['market','size','value','tech']),activeKgTypes=new Set(),selectedKgNode=null;

const $=id=>document.getElementById(id);
function setText(id,value){$(id).textContent=value}
function formatDelta(v){return `${v>=0?'+':''}${v.toFixed(3)}`}

function renderDeepSeekConfig(config){
  const status=config.status||((config.configured)?'configured':'disabled'),labels={connected:'连接成功',configured:'已配置',disabled:'未配置',error:'连接失败'};
  setText('deepseek-config-status',labels[status]||status);$('deepseek-dot').className=status;
  if(config.model)$('deepseek-model').value=config.model;if(config.base_url)$('deepseek-base-url').value=config.base_url;
  const source=config.key_source==='session'?'当前会话内存':config.key_source==='environment'?'服务环境变量':'无';
  setText('deepseek-config-detail',status==='error'?(config.reason||'连接失败，检查 Key 后重试'):`凭据来源：${source} · 报告结论保持 immutable`);
}

async function loadDeepSeekConfig(){
  if(IS_STATIC_HOST){renderDeepSeekConfig({status:'disabled',configured:false,key_source:'none',model:'deepseek-chat',base_url:'https://api.deepseek.com'});setText('deepseek-config-detail','静态站点不接收 API Key，请使用本地研究台');return}
  try{const res=await fetch('/api/deepseek/config',{cache:'no-store'});if(!res.ok)throw new Error(`HTTP ${res.status}`);renderDeepSeekConfig(await res.json())}
  catch(err){renderDeepSeekConfig({status:'error',reason:err.message})}
}

async function saveDeepSeekConfig({clear=false}={}){
  const button=$('deepseek-save');button.disabled=true;setText('deepseek-config-status',clear?'正在清除':'正在验证');$('deepseek-dot').className='testing';
  try{const payload={model:$('deepseek-model').value,base_url:$('deepseek-base-url').value,clear_api_key:clear,test_connection:!clear};const key=$('deepseek-api-key').value.trim();if(key&&!clear)payload.api_key=key;const res=await fetch('/api/deepseek/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload),cache:'no-store'});const body=await res.json().catch(()=>({}));if(!res.ok)throw new Error(body.error||`HTTP ${res.status}`);$('deepseek-api-key').value='';renderDeepSeekConfig(body)}
  catch(err){renderDeepSeekConfig({status:'error',reason:err.message})}
  finally{button.disabled=false}
}

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
  try{const prompt=$('harness-prompt')?.value.trim()||'';if(IS_STATIC_HOST&&fundId!=='159552')throw new Error('GitHub Pages 为 159552 真实数据快照；任意基金研究请运行本地 Python 服务');const res=await fetch(IS_STATIC_HOST?'data/discovery-159552.json':'/api/research/discover',IS_STATIC_HOST?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fund_id:fundId,prompt}),cache:'no-store'});if(!res.ok){const body=await res.json().catch(()=>({}));throw new Error(body.error||`HTTP ${res.status}`)}discoveryState=await res.json();researchState=null;renderDiscovery();}
  catch(err){setText('research-title','研究运行失败');setText('research-question',err.message);}
  finally{document.body.classList.remove('loading');$('refresh').disabled=false;}
}

async function executeDirection(directionId){
  document.body.classList.add('loading');document.querySelectorAll('.direction-confirm').forEach(x=>x.disabled=true);
  const fundId=$('fund-id').value.trim()||'159552',prompt=$('harness-prompt')?.value.trim()||'',direction=discoveryState.directions.find(x=>x.id===directionId),methods=direction.methods;
  try{const url=IS_STATIC_HOST?`data/research-159552-${directionId.toLowerCase()}.json`:'/api/research/execute',options=IS_STATIC_HOST?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fund_id:fundId,prompt,direction_id:directionId,methods}),cache:'no-store'};const res=await fetch(url,options);if(!res.ok){const body=await res.json().catch(()=>({}));throw new Error(body.error||`HTTP ${res.status}`)}researchState=await res.json();renderResearch();}
  catch(err){setText('research-title','实验运行失败');setText('research-question',err.message);}
  finally{document.body.classList.remove('loading');document.querySelectorAll('.direction-confirm').forEach(x=>x.disabled=false)}
}

function renderDiscovery(){
  const d=discoveryState;setText('research-title','文献知识图谱与研究缺口');setText('research-question','请选择并确认一个方向；确认前不会生成代码或运行实验');setText('hypothesis-count',String(d.directions.length));setText('harness-status','等待确认');
  $('direction-gate').hidden=false;$('program-panel').hidden=true;$('execution-log').innerHTML='';$('experiment-list').innerHTML='';
  $('direction-list').innerHTML=d.directions.map(x=>`<article class="direction-card ${x.feasibility}"><header><b>${x.id}</b><em>${x.feasibility==='ready'?'可直接运行':'部分数据受阻'}</em></header><h3>${x.title}</h3><p>${x.gap}</p><dl><div><dt>问题</dt><dd>${x.question}</dd></div><div><dt>预注册假设</dt><dd>${x.hypothesis}</dd></div><div><dt>证据</dt><dd>${x.literature_ids.join(' · ')}</dd></div><div><dt>数据 / 方法</dt><dd>${x.required_data.join('、')} / ${x.methods.join('、')}</dd></div></dl><button type="button" class="direction-confirm" data-direction="${x.id}">确认并开始研究</button></article>`).join('');
  $('literature-list').innerHTML=d.literature.map(x=>`<article class="literature-item"><header><b>${x.citation_id}</b><span>${x.authors} · ${x.year}</span></header><h3>${x.title}</h3><dl><div><dt>测度</dt><dd>${x.extracted.measure}</dd></div><div><dt>机制</dt><dd>${x.extracted.mechanism}</dd></div><div><dt>局限</dt><dd>${x.extracted.limitation}</dd></div></dl></article>`).join('');
  $('gap-list').innerHTML=d.directions.map(x=>`<div class="gap-item"><b>${x.id}</b><span>${x.gap}</span><em>${x.feasibility}</em></div>`).join('');$('hypothesis-list').innerHTML=d.directions.map(x=>`<li><b>${x.id}</b>：${x.hypothesis}<span class="hypothesis-state">待确认</span></li>`).join('');
  renderKnowledgeGraph(d.knowledge_graph);renderHarness(d.harness);renderResearchPerspectives([]);setText('kg-summary',`${d.knowledge_graph.nodes.length} 节点 · ${d.knowledge_graph.edges.length} 关系 · discovery`);setText('footer-run','文献分析完成 · 等待研究方向确认');
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
  $('direction-gate').hidden=true;const program=r.generated_program;$('program-panel').hidden=!program;if(program){setText('program-policy',program.execution_policy);setText('program-hash',`SHA-256 ${program.sha256}`);setText('program-source',program.source)}$('execution-log').innerHTML=(r.execution_log||[]).map(x=>`<div><b>${String(x.step).padStart(2,'0')} · ${x.agent}</b><span>${x.action}</span><em>${x.status}</em><code>${x.outputs.join(' · ')}</code></div>`).join('');
  $('binding-list').innerHTML=r.evidence_bindings.map(x=>`<div class="binding-row"><b>${x.claim_id}</b><span>${x.claim}<br><code>${x.evidence_ids.join(' · ')}</code></span><em class="audit-state ${x.status==='supported'?'ok':''}">${x.status}</em></div>`).join('');
  $('citation-list').innerHTML=r.citation_audit.map(x=>`<div class="citation-row"><b>${x.citation_id.replace('CIT-','')}</b><span><code>${x.doi}</code><br>${x.verification_status}</span><em class="audit-state ${x.doi_format_valid&&x.metadata_complete?'ok':''}">${x.doi_format_valid&&x.metadata_complete?'格式通过':'待修复'}</em></div>`).join('');
  const version=r.version;$('version-info').innerHTML=`<div>code: ${version.code.environment_version}</div><div>data: ${version.data.dataset_version}</div><div>schema: ${version.data.schema_sha256}</div>${r.data_manifest.map(x=>`<div class="manifest-row"><b>${x.dataset_id}</b><span>${x.source}</span><em>${x.status}</em></div>`).join('')}`;
  const cost=r.reproduction_cost;$('cost-info').innerHTML=`<div>runtime: ${cost.runtime_seconds}s</div><div>LLM calls: ${cost.llm_calls}</div><div>network calls: ${cost.network_calls}</div><div>external API cost: ¥${cost.external_api_cost.toFixed(2)}</div><div>${cost.cost_note}</div>`;
  renderDeepSeekReport(r.deepseek_report);
  setText('research-conclusion',r.conclusion.interpretation);$('limitation-list').innerHTML=r.limitations.map(x=>`<li>${x}</li>`).join('');
  renderKnowledgeGraph(r.knowledge_graph);
  renderHarness(r.harness);
  renderMethodComparison(r.method_comparison);
  renderResearchPerspectives(r.experiments);
  renderDataAudit(r.data_audit||[]);
  setText('footer-run',`自主研究完成 · ${new Date().toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit',second:'2-digit'})}`);
}

function renderDeepSeekReport(report){
  if(!report){setText('deepseek-status','未请求');setText('deepseek-meta','');setText('deepseek-report','确认研究方向后生成；未配置 API Key 时保留本地确定性报告。');return}
  const labels={completed:'已生成',disabled:'未配置',error:'调用失败'};setText('deepseek-status',labels[report.status]||report.status);
  const usage=report.usage||{};$('deepseek-meta').innerHTML=`<span>model <b>${report.model||'—'}</b></span><span>request <code>${(report.request_fingerprint||'').slice(0,12)||'—'}</code></span><span>tokens <b>${usage.total_tokens??'—'}</b></span><span>canonical <b>${report.canonical_report_immutable?'immutable':'—'}</b></span>`;
  setText('deepseek-report',report.status==='completed'?report.content:(report.reason||'DeepSeek 报告不可用，已保留本地确定性报告。'));
}

function renderResearchPerspectives(experiments){
  const byId=Object.fromEntries(experiments.map(item=>[item.id,item.result])),manager=byId.E4,narrative=byId.E5,industry=byId.E6;
  const managerRows=[];
  (manager?.events||[]).forEach(event=>managerRows.push(`<div class="evidence-event"><time>${event.date}</time><div><b>${event.manager} · 经理变更</b><span>事件窗暴露位移 L2 = ${event.exposure_shift_l2}</span></div><em>量化事件</em></div>`));
  (narrative?.topic_profiles||[]).forEach(item=>managerRows.push(`<div class="evidence-event"><time>${item.published_date}</time><div><b>定期报告观点</b><span>${item.excerpt}</span><code>SHA ${item.document_sha256.slice(0,12)}</code></div><em>原文已核验</em></div>`));
  $('manager-timeline').innerHTML=managerRows.join('')||'<p class="empty-evidence">当前研究方向未运行经理事件或观点实验。</p>';
  setText('manager-evidence-status',narrative?`报告原文 ${narrative.extracted_report_count}/${narrative.report_metadata_count} · 外部宣讲 ${narrative.verified_external_communications}`:(manager?.status||'未运行'));
  const anomalyRows=(industry?.anomaly_months||[]).map(item=>`<div class="evidence-event"><time>${item.date}</time><div><b>异常残差 ${item.residual}</b><span>样本外 |z| = ${Math.abs(item.z_score).toFixed(3)}</span></div><em>${item.z_score>0?'正异常':'负异常'}</em></div>`);
  const shiftRows=(industry?.rolling_exposure_changes||[]).slice(0,3).map(item=>`<div class="evidence-event exposure-change"><time>暴露变化</time><div><b>${item.industry}</b><span>滚动系数首尾变化 ${item.change>=0?'+':''}${item.change}</span></div><em>行业代理</em></div>`);
  $('industry-anomalies').innerHTML=[...anomalyRows,...shiftRows].join('')||'<p class="empty-evidence">当前研究方向未运行行业残差实验。</p>';
  setText('industry-evidence-status',industry?.status==='completed'?`样本外 RMSE ${industry.metrics.rmse} · 异常占比 ${industry.anomaly_share}`:(industry?.status||'未运行'));
}

function renderDataAudit(rows){$('data-audit-list').innerHTML=rows.map(row=>`<div class="data-audit-row"><b>${row.id}</b><em class="data-kind ${row.kind}">${row.kind}</em><span>${row.source}<small>${row.instrument}</small></span><span>${row.start&&row.end?`${row.start} → ${row.end} · `:''}${row.observations} 条</span><code>${row.sha256?row.sha256.slice(0,12):'—'}</code></div>`).join('')}

function renderMethodOptions(){if(!$('method-options'))return;$('method-options').innerHTML=METHOD_OPTIONS.map(m=>`<label><input type="checkbox" value="${m.id}" checked><span><b>${m.label}</b><small>${m.id} · ${m.source}</small></span></label>`).join('')}
function renderMethodComparison(comparison){
  if(!comparison)return;const review=comparison.review;setText('method-consensus',`共识：${review.consensus} · 可运行 ${review.completed}/${comparison.methods.length}`);setText('method-warning',review.warning);
  $('method-results').innerHTML=comparison.methods.map(method=>{const x=method.result,completed=x.status==='completed';return `<article class="method-result"><header><span>${method.id}</span><em class="audit-state ${completed?'ok':''}">${x.status}</em></header><h3>${method.label}</h3><p>${completed?`信号：${x.drift_detected?'检测到漂移':'未检测到漂移'} · 方向 ${x.direction} · 样本 ${x.n_observations}`:x.reason}</p><dl><div><dt>效应量</dt><dd>${completed&&x.effect_delta!==undefined?x.effect_delta:'—'}</dd></div><div><dt>变化点</dt><dd>${completed&&x.change_points?.length?x.change_points.map(p=>p.date).join('、'):'未检出'}</dd></div></dl><small>${method.limitation}</small></article>`}).join('');
}

function renderHarness(harness){
  if(!harness)return;const labels={completed:'已完成',awaiting_confirmation:'等待确认',running:'运行中'};setText('harness-status',labels[harness.status]||harness.status);
  $('harness-stages').innerHTML=harness.stages.map((stage,index)=>`<article class="harness-stage ${stage.status}"><div class="harness-stage-index">0${index+1}</div><div class="harness-stage-main"><div><b>${stage.title}</b><span>${stage.status}</span></div><p>${stage.summary}</p><code>${stage.evidence_ids.slice(0,5).join(' · ')}</code></div></article>`).join('');
}

const KG_LABELS={literature:'文献',measure:'测度',method:'方法',mechanism:'机制',limitation:'局限',gap:'研究缺口',direction:'研究方向',hypothesis:'假设',experiment:'实验',dataset:'数据',conclusion:'结论'};
const KG_COLORS={literature:'#2f67a6',measure:'#527da5',method:'#206c78',mechanism:'#6f5499',limitation:'#b76b13',gap:'#8b6a23',direction:'#16795a',hypothesis:'#16795a',experiment:'#267762',dataset:'#56635c',conclusion:'#c2413a'};
const SVG_NS='http://www.w3.org/2000/svg';

function svgElement(name,attrs={}){const el=document.createElementNS(SVG_NS,name);Object.entries(attrs).forEach(([k,v])=>el.setAttribute(k,v));return el}
function kgLayer(node){if(node.id.startsWith('LIMIT-'))return 4;return {literature:0,measure:1,mechanism:1,limitation:1,gap:1,dataset:1,direction:2,method:2,hypothesis:2,experiment:3,conclusion:4}[node.type]??2}
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
$('deepseek-config-form').onsubmit=e=>{e.preventDefault();saveDeepSeekConfig()};
$('deepseek-clear').onclick=()=>saveDeepSeekConfig({clear:true});
$('deepseek-key-toggle').onclick=()=>{const input=$('deepseek-api-key'),show=input.type==='password';input.type=show?'text':'password';setText('deepseek-key-toggle',show?'隐藏':'显示');$('deepseek-key-toggle').setAttribute('aria-label',show?'隐藏 API Key':'显示 API Key')};
$('direction-list').onclick=e=>{const button=e.target.closest('.direction-confirm');if(button)executeDirection(button.dataset.direction)};
$('refresh').onclick=()=>currentMode==='analysis'?loadAnalysis():loadResearch();window.addEventListener('resize',()=>requestAnimationFrame(drawAll));loadAnalysis();
renderMethodOptions();
loadDeepSeekConfig();
