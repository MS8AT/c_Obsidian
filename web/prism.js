/* Prism of distinctions. It evaluates only the bounded rule DSL implemented by the server. */
(()=>{
'use strict';
Object.assign(I18N.ru,{prismName:'Призма',prismTitle:'Лаборатория различений',prismDesc:'Вопрос → условия → основания → альтернативы → проверяемый вывод.',prismCase:'Исследовательский случай'});
Object.assign(I18N.en,{prismName:'Prism',prismTitle:'Distinction laboratory',prismDesc:'Question → conditions → grounds → alternatives → inspectable conclusion.',prismCase:'Research case'});
Object.assign(I18N.zh,{prismName:'棱镜',prismTitle:'区分实验室',prismDesc:'问题 → 条件 → 依据 → 替代方案 → 可检查结论。',prismCase:'研究案例'});

const state={cases:[],current:null,evaluation:null,perspective:'ALL',loading:false,editMode:'scenario',draftScenario:null};
const labels={
 ru:{create:'Создать пример',save:'Сохранить версию',evaluate:'Пересчитать',challenge:'Поставить под сомнение',conditions:'Условия',grounds:'Основания',alternatives:'Альтернативы',rules:'Правила и область действия',conclusions:'Выводы',unknown:'Неизвестно',yes:'Да',no:'Нет',question:'Вопрос',revision:'Версия',scenario:'Сценарное допущение',baseEdit:'Исправление исходных сведений',empty:'Случаев пока нет. Создайте встроенный проверяемый пример.',notice:'Результат — вычисление по принятым правилам. Это не приказ и не доказательство само по себе.',saved:'Новая версия сохранена.',conflict:'Случай уже изменён. Перезагрузите его перед сохранением.',change:'Какое условие или критерий меняется?',modelTitle:'Название альтернативной модели'},
 en:{create:'Create example',save:'Save version',evaluate:'Recalculate',challenge:'Challenge',conditions:'Conditions',grounds:'Grounds',alternatives:'Alternatives',rules:'Rules and scope',conclusions:'Conclusions',unknown:'Unknown',yes:'Yes',no:'No',question:'Question',revision:'Revision',scenario:'Scenario assumption',baseEdit:'Correct source information',empty:'No cases yet. Create the built-in inspectable example.',notice:'This result is computed from accepted rules. It is not an order or proof by itself.',saved:'A new revision was saved.',conflict:'The case changed. Reload it before saving.',change:'Which condition or criterion changes?',modelTitle:'Alternative model title'},
 zh:{create:'创建示例',save:'保存版本',evaluate:'重新计算',challenge:'质疑',conditions:'条件',grounds:'依据',alternatives:'替代方案',rules:'规则与范围',conclusions:'结论',unknown:'未知',yes:'是',no:'否',question:'问题',revision:'版本',scenario:'情景假设',baseEdit:'修正原始信息',empty:'暂无案例。创建内置可检查示例。',notice:'结果仅按已接受规则计算；它本身不是命令或证明。',saved:'新版本已保存。',conflict:'案例已改变，请刷新后再保存。',change:'哪个条件或标准发生变化？',modelTitle:'替代模型名称'}
};
Object.assign(labels.ru,{"newProject": "Новый проект", "saveAs": "Сохранить как", "projectTitle": "Название проекта", "projectQuestion": "Исследовательский вопрос", "exportProject": "Экспорт проекта", "importProject": "Импорт проекта", "cancelProject": "Отмена", "createProject": "Создать проект", "importTooLarge": "Проект превышает 8 МиБ.", "projectHistory": "История"});
Object.assign(labels.en,{"newProject": "New project", "saveAs": "Save as", "projectTitle": "Project name", "projectQuestion": "Research question", "exportProject": "Export project", "importProject": "Import project", "cancelProject": "Cancel", "createProject": "Create project", "importTooLarge": "Project exceeds 8 MiB.", "projectHistory": "History"});
Object.assign(labels.zh,{"newProject": "新建项目", "saveAs": "另存为", "projectTitle": "项目名称", "projectQuestion": "研究问题", "exportProject": "导出项目", "importProject": "导入项目", "cancelProject": "取消", "createProject": "创建项目", "importTooLarge": "项目超过 8 MiB。", "projectHistory": "历史"});
const t=key=>(labels[lang]||labels.ru)[key]||key;
const perspectives=['ALL','PROCESS','USER','ARCH','AI'];
const conditionKinds=new Set(['condition','test','observation','feature','criterion']);
const groundKinds=new Set(['evidence','observation','criterion','subject']);

function button(text,className='quiet') {return el('button',{type:'button',class:className},text);}
function card(node){
 const item=el('article',{class:'prism-card','data-node':node.id});
 item.append(el('span',{class:'prism-kind'},node.kind),el('h3',{},node.title));
 if(node.description)item.append(el('p',{},node.description));
 const meta=el('div',{class:'prism-meta'},(node.knowledge_status||'unknown')+' · '+(node.applicability||'applicable')+' · '+(node.origin||node.provenance_mode||'—'));
 if(node.perspectives?.length)meta.append(document.createTextNode(' · '+node.perspectives.join(' / ')));
 item.append(meta);
 if(node.basis){const details=el('details');details.append(el('summary',{},t('grounds')),el('p',{},node.basis));item.append(details);}
 return item;
}
function conditionCard(node){
 const item=card(node),control=button(valueLabel(effectiveNode(node)),'prism-value');control.dataset.condition=node.id;
 control.disabled=!status?.writable;
 control.onclick=()=>{if(state.editMode==='scenario')cycleScenario(node);else cycle(node);const shown=effectiveNode(node);control.textContent=valueLabel(shown);item.querySelector('.prism-meta').textContent=(shown.knowledge_status||'unknown')+' · '+(shown.applicability||'applicable')+' · '+(shown.origin||shown.provenance_mode||'—')+(node.perspectives?.length?' · '+node.perspectives.join(' / '):'');};
 item.append(control);return item;
}
function valueLabel(node){if(node.knowledge_status!=='established')return t('unknown');return node.value===true?t('yes'):node.value===false?t('no'):String(node.value??t('unknown'));}
function cycle(node){if(node.knowledge_status!=='established'){node.knowledge_status='established';node.value=true;}else if(node.value===true){node.value=false;}else{node.knowledge_status='unknown';delete node.value;}}
function effectiveNode(node){const override=state.draftScenario?.overrides.find(item=>item.node_id===node.id);return override?{...node,...override}:node;}
function cycleScenario(node){if(!state.draftScenario)state.draftScenario=newScenario();let override=state.draftScenario.overrides.find(item=>item.node_id===node.id);if(!override){override={node_id:node.id,knowledge_status:'established',provenance_mode:'assumption',origin:'assumption'};if(node.knowledge_status!=='established')override.value=true;else if(node.value===true)override.value=false;else{override.knowledge_status='unknown';}state.draftScenario.overrides.push(override);}else if(override.knowledge_status!=='established'){override.knowledge_status='established';override.value=true;}else if(override.value===true){override.value=false;}else{override.knowledge_status='unknown';delete override.value;}}
function newScenario(){return{id:'scenario-working',title:t('scenario'),base_revision:state.current?.revision||1,overrides:[]};}
function filtered(nodes){return state.perspective==='ALL'?nodes:nodes.filter(n=>n.perspectives?.includes(state.perspective));}

function panel(title,nodes,editable=false){
 const section=el('section',{class:'prism-panel'});section.append(el('h2',{},title));
 const list=el('div',{class:'prism-list'});for(const node of filtered(nodes))list.append(editable?conditionCard(node):card(node));
 if(!list.children.length)list.append(el('p',{class:'prism-empty'},t('unknown')));section.append(list);return section;
}
function resultPanel(){
 const section=el('section',{class:'prism-panel prism-results'});section.append(el('h2',{},t('conclusions')));
 const results=state.evaluation?.results||[];
 for(const result of results){const row=el('article',{class:'prism-result '+result.status});row.append(el('span',{class:'result-status'},result.status+' · '+(result.judgment_status||'unknown')),el('h3',{},result.title),el('p',{},result.scope));if(result.assumptions_used?.length)row.append(el('p',{class:'prism-assumption'},'Допущения: '+result.assumptions_used.join(', ')));section.append(row);}
 if(!results.length)section.append(el('p',{class:'prism-empty'},t('unknown')));
 section.append(el('p',{class:'prism-notice'},state.evaluation?.notice||t('notice')));return section;
}
function exprBlock(expr){
 const block=el('div',{class:'prism-ast '+(expr.op||'fact')});
 if(expr.op){block.append(el('span',{class:'ast-op'},expr.op));const children=expr.op==='not'?[expr.arg]:expr.args||[];for(const child of children)block.append(exprBlock(child));}
 else block.append(el('span',{class:'ast-fact'},`${expr.fact} · ${expr.equals!==undefined?'equals '+JSON.stringify(expr.equals):expr.in?'in '+JSON.stringify(expr.in):'exists'}`));
 return block;
}
function rulePanel(){
 const section=el('section',{class:'prism-panel prism-rules'});section.append(el('h2',{},t('rules')));
 for(const rule of state.current.rules){const item=el('details',{class:'prism-rule'});item.append(el('summary',{},`${rule.id} · ${rule.scope}`),exprBlock(rule.when));const pre=el('pre',{class:'prism-dsl'},JSON.stringify(rule,null,2));pre.setAttribute('aria-label','Read-only DSL');item.append(pre);section.append(item);}
 return section;
}
function toolbar(){
 const bar=el('div',{class:'prism-toolbar'}),select=el('select',{'aria-label':t('prismCase')});
 for(const item of state.cases){const option=el('option',{value:item.id},item.title+' · r'+item.revision);option.selected=item.id===state.current?.id;select.append(option);}
 select.onchange=()=>loadCase(select.value);
 select.id='prism-case-select';
 const filters=el('div',{class:'prism-perspectives',role:'group','aria-label':'Perspectives'});
 for(const name of perspectives){const control=button(name,name===state.perspective?'active':'');control.dataset.perspective=name;control.onclick=()=>{state.perspective=name;draw();};filters.append(control);}
 const recalc=button(t('evaluate'));recalc.id='prism-evaluate';recalc.onclick=evaluateCurrent;
 const mode=el('select',{'aria-label':t('scenario'),id:'prism-edit-mode'});mode.append(el('option',{value:'scenario'},t('scenario')),el('option',{value:'base'},t('baseEdit')));mode.value=state.editMode;mode.onchange=()=>{state.editMode=mode.value;draw();};
 const save=button(t('save'),'primary');save.id='prism-save';save.disabled=!status?.writable;save.onclick=saveCurrent;
 const challenge=button(t('challenge'));challenge.id='prism-challenge';challenge.disabled=!status?.writable;challenge.onclick=challengeCurrent;
 const create=button(t('newProject'));create.id='prism-new-project';create.disabled=!status?.writable;create.onclick=()=>projectDialog(false);
 const copy=button(t('saveAs'));copy.id='prism-save-as';copy.disabled=!status?.writable;copy.onclick=()=>projectDialog(true);
 const out=button(t('exportProject'));out.id='prism-export-project';out.onclick=exportProject;
 const incoming=button(t('importProject'));incoming.id='prism-import-project';incoming.disabled=!status?.writable;incoming.onclick=importProject;
 const history=button(t('projectHistory'));history.id='prism-project-history';history.onclick=showProjectHistory;
 bar.append(select,create,copy,mode,filters,recalc,challenge,save,out,incoming,history);return bar;
}
function draw(){
 document.body.classList.toggle('prism-mode',view==='prism');if(view!=='prism')return;
 $('view-title').textContent=tr('prismTitle');$('view-description').textContent=tr('prismDesc');$('map-caption').textContent=tr('prismName').toLocaleUpperCase();
 const root=$('map');root.replaceChildren();
 if(state.loading){root.append(el('p',{class:'prism-empty'},'…'));return;}
 if(!state.current){const empty=el('div',{class:'prism-welcome'});empty.append(el('h2',{},tr('prismTitle')),el('p',{},t('empty')));const create=button(t('create'),'primary');create.disabled=!status?.writable;create.id='prism-create-example';create.onclick=createExample;const named=button(t('newProject'));named.disabled=!status?.writable;named.onclick=()=>projectDialog(false);named.id='prism-new-project';empty.append(create,named);const incoming=button(t('importProject'));incoming.disabled=!status?.writable;incoming.onclick=importProject;incoming.id='prism-import-project';empty.append(incoming);root.append(empty);return;}
 root.append(toolbar());
 const intro=el('section',{class:'prism-question'});intro.append(el('span',{class:'prism-kind'},t('question')),el('h2',{},state.current.question),el('p',{},`${t('revision')}: ${state.current.revision} · ${state.current.domain||'—'}`));root.append(intro);
 const grid=el('div',{class:'prism-grid'}),conditions=state.current.nodes.filter(n=>conditionKinds.has(n.kind)),grounds=state.current.nodes.filter(n=>groundKinds.has(n.kind));
 grid.append(panel(t('conditions'),conditions,true),panel(t('grounds'),grounds),resultPanel());root.append(grid);
 const bottom=el('div',{class:'prism-bottom'});bottom.append(rulePanel());
 const alternatives=el('section',{class:'prism-panel'});alternatives.append(el('h2',{},t('alternatives')));for(const scenario of state.current.scenarios||[]){const open=button(scenario.title+' · '+scenario.overrides.length+' override','prism-card prism-scenario');open.onclick=()=>{state.editMode='scenario';state.draftScenario=JSON.parse(JSON.stringify(scenario));evaluateCurrent();};alternatives.append(open);}for(const model of state.current.models||[])alternatives.append(el('article',{class:'prism-card'},model.title+' — '+model.change));if(!(state.current.models||[]).length&&!(state.current.scenarios||[]).length)alternatives.append(el('p',{class:'prism-empty'},t('unknown')));bottom.append(alternatives);root.append(bottom);
}
async function loadCases(){state.loading=true;draw();try{const data=await json('/api/prism/v1/cases');state.cases=data.cases||[];if(state.cases.length)await loadCase(state.current?.id||state.cases[0].id);else{state.current=null;state.evaluation=null;}}catch(error){message(failure(error));}finally{state.loading=false;draw();}}
async function loadCase(id){state.loading=true;draw();try{state.current=await json('/api/prism/v1/cases/'+encodeURIComponent(id));state.draftScenario=newScenario();state.evaluation=await json('/api/prism/v1/cases/'+encodeURIComponent(id)+'/evaluate',{method:'POST',body:'{}'});}catch(error){message(failure(error));}finally{state.loading=false;draw();}}
async function createExample(){try{const model=await json('/api/prism/v1/example',{method:'POST',body:'{}'});state.current=model;await loadCases();message(t('saved'));}catch(error){message(failure(error));}}
async function evaluateCurrent(){if(!state.current)return;try{const scenario=state.editMode==='scenario'&&state.draftScenario?.overrides.length?state.draftScenario:null;state.evaluation=await json('/api/prism/v1/cases/'+encodeURIComponent(state.current.id)+'/evaluate',{method:'POST',body:JSON.stringify({scenario})});draw();}catch(error){message(failure(error));}}
async function saveCurrent(){if(!state.current)return;try{const revision=state.current.revision;if(state.editMode==='scenario'&&state.draftScenario?.overrides.length){state.current.scenarios=(state.current.scenarios||[]).filter(item=>item.id!==state.draftScenario.id);state.current.scenarios.push(state.draftScenario);}state.current=await json('/api/prism/v1/cases/'+encodeURIComponent(state.current.id),{method:'PUT',body:JSON.stringify({expected_revision:revision,model:state.current})});await loadCases();message(t('saved'));}catch(error){message(error.message==='revision_conflict'?t('conflict'):failure(error));}}
async function challengeCurrent(){if(!state.current)return;const title=prompt(t('modelTitle'));if(!title)return;const change=prompt(t('change'));if(!change)return;try{const result=await json('/api/prism/v1/cases/'+encodeURIComponent(state.current.id)+'/challenge',{method:'POST',body:JSON.stringify({expected_revision:state.current.revision,title,change})});state.current=result.model;await evaluateCurrent();await loadCases();}catch(error){message(error.message==='revision_conflict'?t('conflict'):failure(error));}}


function projectDialog(copy){
 if(!status?.writable)return;
 const dialog=el('dialog',{id:'prism-project-dialog'}),form=el('form');
 const heading=el('h2',{},t(copy?'saveAs':'newProject'));
 const title=el('input',{id:'prism-project-title',required:'',maxlength:'240'});
 title.value=copy?state.current.title:'';
 const question=el('textarea',{id:'prism-project-question',required:'',maxlength:'2000',rows:'3'});
 question.value=copy?state.current.question:'';
 const error=el('p',{role:'alert',id:'prism-project-error'});
 const cancel=button(t('cancelProject'));cancel.onclick=()=>dialog.close();
 const submit=el('button',{type:'submit',class:'primary'},t('createProject'));
 form.append(heading,el('label',{for:'prism-project-title'},t('projectTitle')),title,el('label',{for:'prism-project-question'},t('projectQuestion')),question,error,cancel,submit);
 form.onsubmit=async event=>{
  event.preventDefault();submit.disabled=true;
  try{
   const payload=copy?JSON.parse(JSON.stringify(state.current)):{};
   for(const key of ['id','revision','created_at','updated_at','results'])delete payload[key];
   for(const scenario of payload.scenarios||[])scenario.base_revision=1;
   payload.title=title.value;payload.question=question.value;
   const result=await json('/api/prism/v1/cases',{method:'POST',body:JSON.stringify(payload)});
   state.current=result;dialog.close();await loadCases();message(t('saved'));
  }catch(cause){error.textContent=failure(cause);submit.disabled=false;}
 };
 dialog.append(form);dialog.addEventListener('close',()=>dialog.remove(),{once:true});document.body.append(dialog);dialog.showModal();
}
function downloadProject(data,name){
 const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json;charset=utf-8'}));
 const link=el('a',{href:url,download:name});document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
async function exportProject(){
 if(!state.current)return;
 try{const data=await json('/api/prism/v1/cases/'+encodeURIComponent(state.current.id)+'/export');downloadProject(data,state.current.id+'.prism.json');}catch(error){message(failure(error));}
}
function importProject(){
 const input=el('input',{type:'file',accept:'.json,application/json',hidden:''});input.id='prism-project-import-file';
 input.onchange=async()=>{
  const file=input.files[0];if(!file)return;
  try{
   if(file.size>8*1024*1024)throw new Error(t('importTooLarge'));
   const data=JSON.parse(await file.text());
   const checked=await json('/api/prism/v1/import/validate',{method:'POST',body:JSON.stringify({package:data})});
   state.current=await json('/api/prism/v1/import/commit',{method:'POST',body:JSON.stringify({package:data,expected_package_sha256:checked.package_sha256})});
   await loadCases();message(t('saved'));
  }catch(error){message(failure(error));}finally{input.remove();}
 };document.body.append(input);input.click();
}
async function showProjectHistory(){
 if(!state.current)return;
 try{
  const data=await json('/api/prism/v1/cases/'+encodeURIComponent(state.current.id)+'/history');
  const dialog=el('dialog',{class:'prism-history-dialog'}),close=button(t('cancelProject'));
  close.onclick=()=>dialog.close();dialog.append(el('h2',{},t('projectHistory')),el('pre',{},JSON.stringify(data.events,null,2)),close);
  dialog.addEventListener('close',()=>dialog.remove(),{once:true});document.body.append(dialog);dialog.showModal();
 }catch(error){message(failure(error));}
}

const atlasRender=render;
render=function(){if(view==='prism'){draw();return;}document.body.classList.remove('prism-mode');atlasRender();};
const atlasTranslate=translate;
translate=function(){atlasTranslate();if(view==='prism')draw();};
document.querySelectorAll('[data-view]').forEach(control=>control.addEventListener('click',()=>{if(control.dataset.view==='prism')loadCases();}));
if(view==='prism')loadCases();
})();
