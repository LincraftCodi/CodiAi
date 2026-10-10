'use strict';
const $ = (id) => document.getElementById(id);
let state = { token: '', settings: {}, modes: {}, chat: null, chats: [], busy: false, status: null, images: [] };
let toastTimer, pullTimer, chatsRequest=0,panelRequest=0;
const icon = name => `<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const modeIcons={artist:'palette',super:'search',desktop:'spark',general:'spark',vibecoding:'code',programmer:'code',teacher:'book',roleplay:'moon',researcher:'search',writer:'edit',translator:'language',analyst:'chart',planner:'clock',designer:'palette'};
const modeDescriptions = {artist:'3D-ассеты, Blender-скрипты и SVG-персонажи',super:'Ответ с поиском и сопоставлением сайтов · без скачивания',desktop:'Экран, программы, файлы и память ваших действий',general:'Повседневные вопросы и идеи',vibecoding:'Идея → план → код → проверка правок',programmer:'Код, архитектура и объяснения',teacher:'Понятные примеры и упражнения',roleplay:'Истории, миры и персонажи',researcher:'Исследование ваших документов',writer:'Тексты и редактура',translator:'Перевод с сохранением смысла',analyst:'Числа, расчёты и выводы',planner:'Планы и задачи по шагам',designer:'Идеи оформления и интерфейсов'};
function modesPanel(){openDialog('Чем займёмся?',`<p class="panel-description">Выберите задачу. Режим подстроит ответы и доступные действия.</p><div class="mode-grid">${Object.entries(state.modes).map(([id,m])=>`<button class="mode-card ${id===$('mode-select').value?'selected':''}" data-choose-mode="${esc(id)}">${icon(modeIcons[id] || 'spark')}<strong>${esc(m.name)}</strong><span>${esc(modeDescriptions[id] || 'Ваш собственный режим')}</span></button>`).join('')}</div>`);}
function editMessage(id){
  if(state.busy)throw new Error('Сначала остановите ответ');
  const message=state.chat?.messages.find(m=>m.id===id && m.role==='user');if(!message)return;
  openDialog('Изменить сообщение',`<p class="panel-description">CodiAI ответит заново. Сообщения после выбранного будут заменены; прежний разговор можно вернуть кнопкой под ответом.</p><form id="edit-form"><label class="field">Сообщение<textarea id="edit-content" maxlength="16000" required>${esc(message.content)}</textarea></label><div class="toolbar"><button class="primary" type="submit">Сохранить и получить ответ</button><button type="button" id="cancel-edit">Отмена</button></div></form>`);
  $('cancel-edit').onclick=()=>$('panel').close();
  $('edit-form').onsubmit=guard(async e=>{e.preventDefault();const submit=e.target.querySelector('[type=submit]');submit.disabled=true;try{state.chat=await api('/api/messages/edit',{chat_id:state.chat.id,message_id:id,content:$('edit-content').value});$('panel').close();renderChat();await send(false,true);}finally{submit.disabled=false;}});
}
const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function toast(message, error=false) { $('toast').textContent = message; $('toast').classList.toggle('error', error); $('toast').hidden = false; clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('toast').hidden=true, 5500); }
async function api(path, data, retry=true) {
  const response = await fetch(path, data === undefined ? {signal:AbortSignal.timeout(8000)} : { method:'POST', headers:{'Content-Type':'application/json','X-Codi-Token':state.token}, body:JSON.stringify(data),signal:AbortSignal.timeout(['/api/documents','/api/workspace/pick','/api/memory/import'].includes(path)?180000:['/api/browser/read','/api/browser/search'].includes(path)?90000:15000) });
  const result = await response.json();
  if(response.status===403 && retry && result.error==='Недействительный токен локальной сессии') {
    const session=await api('/api/bootstrap',undefined,false);state.token=session.token;
    return api(path,data,false);
  }
  if (!response.ok) throw new Error(result.error || 'Ошибка запроса');
  return result;
}
function guard(fn) { return (...args) => Promise.resolve(fn(...args)).catch(e=>toast(e.message,true)); }
function applyAppearance() {
  document.documentElement.dataset.theme = state.settings.theme || 'codi';
  document.documentElement.classList.toggle('no-motion', !state.settings.animations);
  $('mascot').src = `/assets/${state.settings.skin || 'original'}.png`;
  $('workspace-short').textContent=state.settings.workspace ? state.settings.workspace.split(/[\\/]/).pop() : 'Папка не выбрана';
  $('tools-toggle').classList.toggle('active', state.settings.tools_enabled);
  $('thinking-toggle').classList.toggle('active', state.settings.thinking);
  const tier = state.status?.models.find(m=>m.backend===state.settings.model);
  $('model-shortcut').textContent = (tier?.name || 'Initial 0.2') + ' ▾';
  $('backend-note').textContent = 'CodiAI · локальный запуск';
}
async function saveSettings(patch) { state.settings = await api('/api/settings', patch); applyAppearance(); }
function fillModes() {
  $('mode-select').innerHTML = Object.entries(state.modes).map(([id,m])=>`<option value="${esc(id)}">${esc(m.name)}</option>`).join('');
  $('mode-select').value = state.chat?.mode || state.settings.mode;
  const selected=$('mode-select').value;
  $('mode-name').textContent=state.modes[selected]?.name || 'Ассистент';
  $('mode-hint').textContent=modeDescriptions[selected] || 'Ваш собственный режим';
  $('coding-bar').hidden=selected!=='vibecoding';
}
async function refreshChats() {
  const request=++chatsRequest, rows=await api('/api/chats');if(request!==chatsRequest)return;
  state.chats=[...new Map(rows.map(c=>[c.id,c])).values()].sort((a,b)=>b.pinned-a.pinned || b.updated-a.updated);
  $('chat-list').innerHTML = state.chats.length ? state.chats.map(c=>`<div class="chat-item ${c.id===state.chat?.id?'active':''} ${c.pinned?'pinned':''}"><button data-chat="${c.id}" title="${esc(c.title)}">${c.pinned?icon('pin'):''}<span>${esc(c.title)}<small class="chat-time">${new Date(c.updated*1000).toLocaleString('ru-RU',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})}</small></span></button><button class="chat-control" data-pin-chat="${c.id}" aria-label="${c.pinned?'Открепить':'Закрепить'} чат" title="${c.pinned?'Открепить':'Закрепить'}">${icon('pin')}</button><button class="chat-control" data-delete-chat="${c.id}" aria-label="Удалить чат" title="Удалить">${icon('trash')}</button></div>`).join('') : '<div class="empty-list">Начните разговор — он появится здесь</div>';
}
function inline(text) {
  return esc(text).replace(/`([^`]+)`/g,'<code>$1</code>').replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>').replace(/\*([^*\n]+)\*/g,'<em>$1</em>');
}
function markdown(text) {
  const pieces = text.split(/(```[\s\S]*?(?:```|$))/g);
  return pieces.map(piece=>{
    if (piece.startsWith('```')) {
      const firstNewline = piece.indexOf('\n');
      const language = firstNewline<0 ? '' : piece.slice(3,firstNewline).trim();
      let code = firstNewline<0 ? piece.slice(3) : piece.slice(firstNewline+1);
      if (code.endsWith('```')) code=code.slice(0,-3);
      return `<div class="code-block"><div class="code-label"><span>${esc(language || 'код')}</span><button class="copy-code">Копировать</button></div><pre><code>${esc(code)}</code></pre></div>`;
    }
    return piece.split(/\n\s*\n/).filter(Boolean).map(paragraph=>{
      const lines=paragraph.split('\n');
      if (lines.every(l=>/^\s*[-*]\s/.test(l))) return '<ul>'+lines.map(l=>`<li>${inline(l.replace(/^\s*[-*]\s/,''))}</li>`).join('')+'</ul>';
      return '<p>'+lines.map(l=>/^#{1,4}\s/.test(l)?`<strong class="md-heading">${inline(l.replace(/^#{1,4}\s/,''))}</strong>`:inline(l)).join('<br>')+'</p>';
    }).join('');
  }).join('');
}
function toolLabel(tool) { return {calculator:'Вычисление',knowledge_search:'Поиск в документах',project_list:'Файлы проекта',project_read:'Чтение файла',project_search:'Поиск по проекту',project_mkdir:'Создание папки',project_check:'Проверка синтаксиса',propose_write:'Предложение изменения',ask_user:'Уточнение'}[tool] || tool; }
function messageNode(message) {
  const div=document.createElement('article'); div.className=`message ${message.role}`; div.dataset.id=message.id;
  div.innerHTML=`<div class="message-label"><span class="avatar">${message.role==='user'?'Вы':'<img src="/assets/original.png" alt="">'}</span><span>${message.role==='user'?'Вы':esc(state.settings.name)}</span></div><div class="message-content"></div><div class="message-extras"></div><div class="message-actions"></div>`;
  if (message.role==='user') {
    div.querySelector('.message-content').innerHTML=esc(message.content)+(message.metadata?.images?.length ? '<div class="message-images">'+message.metadata.images.map(i=>`<a href="${esc(i.url)}" target="_blank"><img src="${esc(i.url)}" alt="${esc(i.name)}" loading="lazy"></a>`).join('')+'</div>' : '');
    div.querySelector('.message-actions').innerHTML=`<button data-edit-message="${message.id}" ${state.busy?'disabled':''}>${icon('edit')}Изменить</button>`;
  }
  else {
    div.querySelector('.message-content').innerHTML=markdown(message.content);
    if(!message.content && message.status==='complete')div.querySelector('.message-content').textContent='Этот старый ответ не сохранился корректно. Нажмите «Другой ответ», чтобы получить новый.';
    const extras=div.querySelector('.message-extras');
    for (const tool of message.metadata?.tools || []) if(tool.name!=='ask_user')appendTool(extras,tool.name,tool.result);
    if(message.metadata?.question && state.chat?.messages.at(-1)?.id===message.id)appendQuestion(extras,message.metadata.question);
    if (message.metadata?.sources?.length) { const sources=document.createElement('div');sources.className='source-list';sources.textContent='Источники: '+[...new Set(message.metadata.sources.map(s=>s.name))].join(', '); extras.append(sources); }
    if (message.status==='error') {const note=document.createElement('div');note.className='notice';note.textContent='Ответ прерван ошибкой. Проверьте состояние модели и повторите.';extras.append(note);}
    if (message.status==='stopped' || message.status==='interrupted') {const note=document.createElement('div');note.className='notice';note.textContent='Генерация остановлена';extras.append(note);}
    if(message.status==='limited'){const note=document.createElement('div');note.className='notice';note.textContent='Этот ответ был оборван в прежней версии. Нажмите «Повторить», чтобы получить полный ответ.';extras.append(note);}
    div.querySelector('.message-actions').innerHTML=`<button class="copy-message">${icon('copy')}Копировать</button>`;
    div.dataset.raw=message.content;
  }
  return div;
}
function appendTool(container, name, result) {
  const el=document.createElement('div');el.className='tool-event'+(result.status==='error'?' error':'');
  el.textContent=toolLabel(name)+(result.status==='error'?': '+result.error:' · выполнено');
  if (result.result?.proposal_id) {el.textContent=(result.result.file_written?'Сохранён файл ':'Правка ')+result.result.path+(result.result.file_written?' · можно откатить':' · ждёт подтверждения');const button=document.createElement('button');button.textContent='Посмотреть правки';button.dataset.panel='tools';el.append(button);}
  else if(name==='calculator' && result.result) el.textContent+=': '+result.result.value;
  container.append(el);
}
function appendQuestion(container,question) {
  const card=document.createElement('div');card.className='question-card';
  const title=document.createElement('strong');title.textContent='Выберите вариант или напишите свой ответ';card.append(title);
  const choices=document.createElement('div');choices.className='question-choices';
  const answer=guard(async(text)=>{if(state.busy)return;$('message').value=text;await send();});
  for(const option of question.options || []){const button=document.createElement('button');button.type='button';button.textContent=option;button.disabled=state.busy;button.addEventListener('click',()=>answer(option));choices.append(button);}
  card.append(choices);
  const form=document.createElement('form');form.className='question-custom';
  const input=document.createElement('input');input.placeholder='Свой ответ';input.setAttribute('aria-label','Свой ответ на уточнение');input.maxLength=16000;
  const submit=document.createElement('button');submit.type='submit';submit.textContent='Ответить';submit.disabled=state.busy;
  form.append(input,submit);form.addEventListener('submit',event=>{event.preventDefault();if(input.value.trim())answer(input.value.trim());});card.append(form);container.append(card);
}
function renderChat() {
  const hasMessages=state.chat?.messages?.length;
  $('welcome').hidden=!!hasMessages; $('messages').hidden=!hasMessages;
  $('suggestions').hidden=!!hasMessages;
  $('messages').replaceChildren(...(state.chat?.messages || []).map(messageNode));
  if(hasMessages && state.chat.messages.at(-1).role==='assistant') {
    const button=document.createElement('button');button.className='regenerate';button.innerHTML=icon('refresh')+'Другой ответ';button.disabled=state.busy;button.addEventListener('click',guard(()=>send(true)));
    $('messages').lastElementChild.querySelector('.message-actions').append(button);
  }
  if(state.chat?.has_revision && !state.busy){const restore=document.createElement('button');restore.className='restore-version';restore.dataset.restoreChat=state.chat.id;restore.innerHTML=icon('refresh')+'Вернуть разговор до редактирования';$('messages').append(restore);}
  fillModes();scrollBottom();
}
function scrollBottom(){ $('messages').scrollTop=$('messages').scrollHeight; }
async function newChat() { if(state.busy) throw new Error('Сначала остановите текущий ответ');state.chat=null;state.images=[];renderAttachments();$('message').value='';$('activity').textContent='';renderChat();await refreshChats();$('message').focus(); }
async function openChat(id) { if(state.busy) throw new Error('Дождитесь ответа или нажмите «Стоп»');state.chat=await api('/api/chats/'+id);$('activity').textContent='';renderChat();await refreshChats();document.querySelector('.sidebar').classList.remove('open'); }
async function changeMode(mode) {
  if(state.busy) throw new Error('Сначала остановите генерацию');
  if(state.chat) state.chat=await api('/api/chats/mode',{id:state.chat.id,mode});
  await saveSettings({mode,...(['programmer','vibecoding','desktop'].includes(mode)?{tools_enabled:true}:{})});fillModes();await refreshChats();
}
function busy(value) {state.busy=value;$('send-button').disabled=value || Boolean(window.codiVoiceRecording);$('mode-select').disabled=value;$('mode-picker').disabled=value;$('stop-button').hidden=!value;document.body.classList.toggle('generating',value);}
async function send(regenerate=false,continueEdited=false) {
  if(state.busy || state.uploading || window.codiVoiceRecording) return;
  const text=$('message').value.trim();if(!regenerate && !continueEdited && !text && !state.images.length) return;
  busy(true);$('activity').textContent='Готовлю ответ…';
  let assistant=null, answer='', renderTimer=null;
  const paint=()=>{renderTimer=null;if(assistant){assistant.querySelector('.message-content').innerHTML=markdown(answer);assistant.dataset.raw=answer;scrollBottom();}};
  const schedulePaint=()=>{if(renderTimer===null)renderTimer=setTimeout(paint,160);};
  const requestAbort=new AbortController();
  const requestTimeout=null;
  try {
    const session=await api('/api/bootstrap');state.token=session.token;
    if(!state.chat)state.chat=await api('/api/chats',{mode:$('mode-select').value || state.settings.mode});
    const response=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','X-Codi-Token':state.token},body:JSON.stringify({chat_id:state.chat.id,message:text,images:regenerate||continueEdited?[]:state.images.map(i=>i.id),regenerate,continue_edited:continueEdited}),signal:requestAbort.signal});
    if(!response.ok){const result=await response.json();throw new Error(result.error);}
    if(response.headers.get('content-type')?.includes('application/json')) {await response.json();$('message').value='';$('activity').textContent='Готово';state.settings=(await api('/api/bootstrap')).settings;applyAppearance();return;}
    $('message').value='';$('message').style.height='auto';
    if(regenerate) state.chat.messages.pop();else if(!continueEdited)state.chat.messages.push({id:'pending-user',role:'user',content:text || 'Что изображено на картинке?',metadata:{images:[...state.images]},status:'complete'});
    state.images=[];renderAttachments();renderChat();$('welcome').hidden=true;$('messages').hidden=false;
    const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
    const handle=(event)=>{
      if(event.type==='start') {assistant=messageNode({id:event.message_id,role:'assistant',content:'',metadata:{sources:event.sources},status:'streaming'});$('messages').append(assistant);}
      if(event.type==='token' && assistant){answer+=event.text;schedulePaint();if($('activity').textContent!=='Пишет ответ…')$('activity').textContent='Пишет ответ…';}
      if(event.type==='tool_start') $('activity').textContent=toolLabel(event.name)+'…';
      if(event.type==='activity')$('activity').textContent=event.text;
      if(event.type==='progress') $('activity').textContent='Готовлю ответ…';
      if(event.type==='tool' && event.name!=='ask_user' && assistant) appendTool(assistant.querySelector('.message-extras'),event.name,event);
      if(event.type==='notice') toast(event.text);
      if(event.type==='error') toast(event.message,true);
      if(event.type==='done') $('activity').textContent=event.status==='stopped'?'Остановлено':event.status==='complete'?`Готово · ${event.duration_seconds} с`:'Ответ завершён с ограничением';
      if(event.type!=='token'&&event.type!=='progress')scrollBottom();
    };
    while(true){const {done,value}=await reader.read();if(done)break;buffer+=decoder.decode(value,{stream:true});let index;while((index=buffer.indexOf('\n'))>=0){const line=buffer.slice(0,index);buffer=buffer.slice(index+1);if(line.trim())handle(JSON.parse(line));}}
    buffer+=decoder.decode();if(buffer.trim())handle(JSON.parse(buffer));
  } catch(e) {toast(e.message,true);$('activity').textContent='Не удалось получить ответ';}
  finally {clearTimeout(requestTimeout);if(renderTimer!==null)clearTimeout(renderTimer);paint();busy(false);try{if(state.chat)state.chat=await api('/api/chats/'+state.chat.id);renderChat();await refreshChats();}catch(e){toast('Соединение с CodiAI потеряно. Перезапустите приложение.',true);}}
}
async function refreshStatus() {
  state.status=await api('/api/status');
  const ready=state.status.capabilities.chat==='ready';
  $('connection').textContent=ready?'● Модель готова':state.status.ollama_online?'● Выберите модель':'● Движок отключён';
  $('connection').classList.toggle('offline',!ready);$('setup-banner').hidden=ready;applyAppearance();
}
function openDialog(title, html) {if(typeof stopLearningPoll==='function')stopLearningPoll();$('panel-title').textContent=title;$('panel-content').innerHTML=html;if(!$('panel').open)$('panel').showModal();}
const titles={models:'Локальные модели',knowledge:'База знаний',memory:'Память ассистента',tools:'Проект и изменения',settings:'Настройки ассистента'};
async function panel(name) {
  const ticket=++panelRequest;
  if(pullTimer){clearTimeout(pullTimer);pullTimer=null;}
  if(name==='settings')return settingsPanel();
  openDialog(titles[name] || 'CodiAI','<p class="panel-description">Загрузка…</p>');
  if(name==='models') {
    await refreshStatus();if(ticket!==panelRequest || !$('panel').open)return;
    openDialog(titles.models,`<p class="panel-description">Модели работают на вашем компьютере без платного AI API. Initial — названия уровней CodiAI; лицензия указана ниже. Оценки размера приблизительные, скорость зависит от железа.</p><div class="list-card"><h3>Поиск · без скачивания</h3><p>Ответ с поиском и сопоставлением разных интернет-источников. Использует установленную модель, работает дольше. В поиск отправляется только текст вопроса. Достоверность не гарантируется.</p><p>Источников: ${state.settings.super_sources || 8}. Выберите глубину поиска:</p><div class="toolbar"><button data-super-sources="4">4 сайта</button><button data-super-sources="8">8 сайтов</button><button data-super-sources="12">12 сайтов</button></div><button class="primary" data-choose-mode="super">Включить Поиск</button></div><div class="model-grid">${state.status.models.map(m=>`<div class="model-card ${state.settings.model===m.backend?'selected':''}"><h3>${esc(m.name)}</h3><div class="backend">Локальная модель · Apache-2.0</div><p>${esc(m.description)}</p><small>Загрузка ≈ ${m.size_gb} ГБ · RAM от ${m.ram_gb} ГБ<br>Статус: ${m.installed?'установлена':'не установлена'}<br>${esc(m.verification || '')}</small><button ${m.installed?`data-use-model="${m.backend}"`:`data-pull-model="${m.backend}"`}>${m.installed?(state.settings.model===m.backend?'✓ Активная':'Использовать'):'↓ Скачать'}</button></div>`).join('')}</div><div id="pull-progress" class="progress-text"></div><div class="list-card"><div><strong>Семантический поиск</strong><button ${state.status.embedding_ready?'disabled':'data-pull-model="embeddinggemma"'}>${state.status.embedding_ready?'✓ Установлен':'↓ Установить ≈ 0,62 ГБ'}</button></div><p>embeddinggemma строит векторы документов для поиска по смыслу. Без неё доступен поиск по словам.</p></div><div class="list-card"><div><strong>Зрение · локальная модель</strong><button ${state.status.vision_ready?'disabled':'data-pull-model="qwen3-vl:2b-instruct"'}>${state.status.vision_ready?'✓ Установлено':'Установить ≈ 1,9 ГБ'}</button></div><p>Анализ картинок и снимков экрана локально, без отправки в облако.</p></div><h3>Возможности этой версии</h3><div class="capabilities">${Object.entries(state.status.capabilities).map(([key,value])=>`<div class="capability ${value!=='ready'?'planned':''}"><span>${esc(({chat:'Локальный чат',history:'История',modes:'Режимы',memory:'Память',documents:'Документы',semantic_rag:'Поиск по смыслу',project_tools:'Инструменты проекта',file_diff_backup_undo:'Diff и откат',terminal_sandbox:'Изолированный терминал',web_search:'Веб-поиск',browser:'Встроенный браузер',web_learning:'Изучение сайтов',memory_transfer:'Перенос памяти',video_transcripts:'Расшифровки видео',voice:'Голос',vision:'Распознавание изображений',image_generation:'Генерация изображений',video:'Анализ кадров видео',floating_desktop:'Виджет рабочего стола',training:'Дообучение'})[key] || key)}</span><span>${value==='ready'?'готово':value==='planned'?'в плане':'недоступно'}</span></div>`).join('')}</div>`);
  }
  if(name==='knowledge') {
    const documents=await api('/api/documents');if(ticket!==panelRequest || !$('panel').open)return;
    openDialog(titles.knowledge,`<p class="panel-description">Добавьте текстовые документы, код или заметки. CodiAI найдёт подходящие фрагменты и использует их в ответах с указанием источника. Поддерживаются TXT, Markdown, CSV и текстовый код до 300 000 символов. Это база знаний, а не обучение весов.</p><div class="toolbar"><button id="upload-document" class="primary">＋ Добавить документ</button><input id="knowledge-query" placeholder="Найти в документах…"><button id="search-knowledge">Найти</button></div><div id="knowledge-results"></div><div>${documents.length?documents.map(d=>`<div class="list-card"><div><strong>${esc(d.name)}</strong><button data-delete-document="${d.id}">Удалить</button></div><small>${d.chunks} фрагментов · ${d.embedded===d.chunks?'поиск по смыслу':'поиск по словам'}</small></div>`).join(''):'<p class="panel-description">Пока нет документов. Добавьте первый файл.</p>'}</div>`);
  }
  if(name==='memory')return memoryPanel();
  if(name==='browser')return browserPanel();
  if(name==='tools') {
    const proposals=(await api('/api/proposals')).filter(p=>p.workspace===state.settings.workspace).slice(0,20);if(ticket!==panelRequest || !$('panel').open)return;
    openDialog(titles.tools,`<p class="panel-description">Выберите папку обычным окном Windows. В Code With Codi ассистент создаёт папки, пишет и изменяет текстовые файлы. Каждая запись сохраняет прежнюю версию для отката. Python и JSON проверяются перед записью. Доступны запуск проверки и сборки проекта. APK создаётся сборщиком Android, когда SDK и Gradle установлены.</p><div class="toolbar"><button data-pick-workspace="true" class="primary">Выбрать папку…</button></div><label class="check"><input id="auto-write" type="checkbox" ${state.settings.project_autowrite?'checked':''}>Записывать файлы автоматически в Code With Codi и режиме «Компьютер»</label><label class="field">Папка проекта<input id="project-path" value="${esc(state.settings.workspace)}" placeholder="D:\\Мои проекты\\игра"></label><div class="toolbar"><button id="save-project" class="primary">Подключить папку</button><button id="list-project">Показать файлы</button><button id="show-audit">Журнал действий</button></div><div id="project-results"></div><h3>Предложения изменений</h3>${proposals.map(p=>`<div class="list-card"><div><strong>${esc(p.path)}</strong><small>${esc(({pending:'Ожидает решения',applied:'Применено',undone:'Отменено'})[p.status] || p.status)}</small></div><pre class="diff">${esc(p.diff || 'Содержимое не изменилось')}</pre>${p.status==='pending'?`<button class="primary" data-apply="${p.id}">Применить изменение</button>`:p.status==='applied'?`<button data-undo="${p.id}">Откатить изменение</button>`:''}</div>`).join('') || '<p class="panel-description">Предложений пока нет. Попросите ассистента изменить текстовый файл.</p>'}`);
  }
}
function selectOptions(values, current) { return values.map(v=>`<option ${v===current?'selected':''}>${esc(v)}</option>`).join(''); }
function settingsPanel() {
  const s=state.settings;
  openDialog(titles.settings,`<p class="panel-description">Настройте общение, оформление и возможности. Все настройки хранятся локально на диске D вместе с приложением.</p><form id="settings-form"><div class="form-grid"><label class="field">Имя ассистента<input name="name" value="${esc(s.name)}" maxlength="60"></label><label class="field">Язык ответа<select name="language">${selectOptions(['ru','en'],s.language)}</select></label><label class="field">Тон<select name="tone">${selectOptions(['Дружелюбный','Спокойный','Деловой','С юмором'],s.tone)}</select></label><label class="field">Длина ответа<select name="verbosity">${selectOptions(['Короткая','Средняя','Подробная'],s.verbosity)}</select></label><label class="field">Образ персонажа<select name="skin"><option value="original" ${s.skin==='original'?'selected':''}>Основной</option><option value="programmer" ${s.skin==='programmer'?'selected':''}>Программист</option><option value="teacher" ${s.skin==='teacher'?'selected':''}>Учитель</option></select></label><label class="field">Уровень ученика<select name="teacher_level">${selectOptions(['Начинающий','Средний','Продвинутый'],s.teacher_level)}</select></label><div class="field wide">Цветовая тема<div class="theme-picker">${[['codi','Codi'],['ice','Ледяная'],['violet','Лаванда'],['rose','Розовая'],['amber','Песочная'],['graphite','Графит']].map(([id,label])=>`<button type="button" class="theme-choice ${s.theme===id?'selected':''}" data-theme-choice="${id}"><span class="theme-swatch swatch-${id}"></span>${label}</button>`).join('')}</div></div><label class="field">Творчество · ${s.temperature}<input name="temperature" type="range" min="0" max="1.5" step="0.1" value="${s.temperature}"></label><label class="field">Окно контекста<select name="num_ctx">${[2048,4096,8192,16384].map(n=>`<option value="${n}" ${n===s.num_ctx?'selected':''}>${n} токенов</option>`).join('')}</select></label><label class="field wide">Дополнительные инструкции<textarea name="custom_instruction" maxlength="5000" placeholder="Ваши предпочтения для всех режимов">${esc(s.custom_instruction)}</textarea></label><label class="field">Мир для ролёвки<textarea name="roleplay_world" maxlength="1500">${esc(s.roleplay_world)}</textarea></label><label class="field">Персонаж ассистента в ролёвке<textarea name="roleplay_character" maxlength="1500">${esc(s.roleplay_character)}</textarea></label></div><label class="check"><input type="checkbox" name="animations" ${s.animations?'checked':''}>Плавные анимации интерфейса</label><label class="check"><input type="checkbox" name="memory_enabled" ${s.memory_enabled?'checked':''}>Использовать сохранённую память</label><label class="check"><input type="checkbox" name="rag_enabled" ${s.rag_enabled?'checked':''}>Искать в загруженных документах</label><label class="check"><input type="checkbox" name="semantic_rag" ${s.semantic_rag?'checked':''}>Поиск по смыслу, если embedding-модель установлена</label><label class="check"><input type="checkbox" name="tools_enabled" ${s.tools_enabled?'checked':''}>Разрешить инструменты проекта и калькулятор</label><label class="check"><input type="checkbox" name="thinking" ${s.model.endsWith('-instruct')?'disabled':' '} ${s.thinking?'checked':''}>Тщательная проверка ответа — медленнее, внутренние рассуждения скрыты</label><div class="settings-footer"><button type="submit" class="primary">Сохранить настройки</button><button type="button" id="export-data">Экспортировать мои данные</button><button type="button" id="import-profile">Импорт настроек</button><button type="button" id="export-profile">Экспорт настроек</button></div></form><h3>Свой режим</h3><p class="panel-description">Создайте собственную роль. Режим меняет поведение, но не выдаёт дополнительные разрешения.</p><form id="custom-mode-form"><label class="field">Название<input id="custom-mode-name" maxlength="60" required placeholder="Например: наставник по разработке игр"></label><label class="field">Как ассистент должен отвечать<textarea id="custom-mode-instruction" maxlength="4000" required></textarea></label><button class="primary">Создать режим</button></form>`);
  $('settings-form').onsubmit=guard(async e=>{e.preventDefault();const form=new FormData(e.target);const patch={};for(const [key,value] of form)patch[key]=value;for(const key of ['animations','memory_enabled','rag_enabled','semantic_rag','tools_enabled','thinking'])patch[key]=e.target.elements[key].checked;patch.temperature=Number(patch.temperature);patch.num_ctx=Number(patch.num_ctx);await saveSettings(patch);$('panel').close();toast('Настройки сохранены');});
  $('custom-mode-form').onsubmit=guard(async e=>{e.preventDefault();state.modes=await api('/api/modes',{name:$('custom-mode-name').value,instruction:$('custom-mode-instruction').value});fillModes();toast('Режим добавлен в список');$('custom-mode-name').value='';$('custom-mode-instruction').value='';});
}
function downloadJSON(value, filename) {const blob=new Blob([JSON.stringify(value,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
async function pollPull(id) {const result=await api('/api/pulls/'+id);const el=$('pull-progress');if(el)el.textContent=result.state==='error'?result.error:result.state==='complete'?'Модель установлена':`${result.model}: ${result.status} ${result.total?Math.round(result.completed/result.total*100)+'%':''}`;if(result.state==='running' && $('panel').open)pullTimer=setTimeout(()=>guard(()=>pollPull(id))(),2000);else if(result.state==='complete'){toast('Файлы модели проверены');await refreshStatus();if($('panel').open && $('panel-title').textContent===titles.models)await panel('models');}}
document.addEventListener('click',guard(async e=>{
  const button=e.target.closest('button');if(!button)return;
  if(button.dataset.pickWorkspace){const result=await api('/api/workspace/pick');if(!result.cancelled){state.settings=result.settings;applyAppearance();toast('Папка подключена');if($('panel').open)await panel('tools');}return;}
  if(button.dataset.removeImage){state.images=state.images.filter(i=>i.id!==button.dataset.removeImage);renderAttachments();return;}
  if(button.dataset.panel)return panel(button.dataset.panel);
  if(button.dataset.superSources){await saveSettings({super_sources:Number(button.dataset.superSources)});toast('Глубина поиска сохранена');return panel('models');}
  if(button.dataset.chooseMode){await changeMode(button.dataset.chooseMode);$('panel').close();$('message').focus();return;}
  if(button.dataset.editMessage)return editMessage(button.dataset.editMessage);
  if(button.dataset.restoreChat){if(state.busy)throw new Error('Сначала остановите ответ');state.chat=await api('/api/messages/restore',{chat_id:button.dataset.restoreChat});renderChat();await refreshChats();toast('Прежняя версия восстановлена');return;}
  if(button.dataset.pinChat){const chat=state.chats.find(c=>c.id===button.dataset.pinChat);await api('/api/chats/pin',{chat_id:chat.id,pinned:!chat.pinned});await refreshChats();return;}
  if(button.dataset.vibe){$('message').value=button.dataset.vibe;$('message').focus();return;}
  if(button.dataset.readFile){const result=await api('/api/tools',{name:'project_read',arguments:{path:button.dataset.readFile}});openDialog(result.path,`<div class="toolbar"><button data-panel="tools">Вернуться к проекту</button><button data-check-file="${esc(result.path)}">Проверить синтаксис</button><button data-discuss-file="${esc(result.path)}">Обсудить файл</button></div><pre class="diff">${esc(result.content)}</pre>`);return;}
  if(button.dataset.checkFile){const result=await api('/api/tools',{name:'project_check',arguments:{path:button.dataset.checkFile}});toast('Синтаксис корректен. Код не запускался.');return;}
  if(button.dataset.discussFile){$('panel').close();await changeMode('vibecoding');$('message').value=`Изучи файл ${button.dataset.discussFile}. Объясни его назначение и предложи улучшения.`;$('message').focus();return;}
  if(button.dataset.chat)return openChat(button.dataset.chat);
  if(button.dataset.deleteChat){if(confirm('Удалить этот разговор и его отдельную память?')){await api('/api/chats/delete',{id:button.dataset.deleteChat});if(state.chat?.id===button.dataset.deleteChat){state.chat=null;renderChat();}await refreshChats();}return;}
  if(button.dataset.prompt){if(button.dataset.mode)await changeMode(button.dataset.mode);$('message').value=button.dataset.prompt;$('message').focus();return;}
  if(button.dataset.useModel){await saveSettings({model:button.dataset.useModel});await panel('models');toast('Модель выбрана');return;}
  if(button.dataset.pullModel){const model=button.dataset.pullModel;const tier=state.status.models.find(m=>m.backend===model);if(confirm(`Загрузить ${model} на диск D?\nОбъём ≈ ${tier?.size_gb || (button.dataset.pullModel.startsWith('qwen3-vl:')?1.9:0.62)} ГБ. Нужен интернет.${tier?.id==='maximum'?'\nНа этом компьютере модель может быть слишком тяжёлой.':''}`)){const result=await api('/api/models/pull',{model});await pollPull(result.id);}return;}
  if(button.dataset.deleteDocument){if(confirm('Удалить документ и его индекс?')){await api('/api/documents/delete',{id:button.dataset.deleteDocument});await panel('knowledge');}return;}
  if(button.dataset.deleteMemory){await api('/api/memories/delete',{id:button.dataset.deleteMemory});return panel('memory');}
  if(button.dataset.apply){if(confirm('Применить показанное изменение файла? Будет сохранена резервная копия.')){await api('/api/proposals/apply',{id:button.dataset.apply});await panel('tools');toast('Изменение применено');}return;}
  if(button.dataset.undo){if(confirm('Вернуть файл к состоянию до этого изменения?')){await api('/api/proposals/undo',{id:button.dataset.undo});await panel('tools');toast('Изменение отменено');}return;}
  if(button.dataset.themeChoice){await saveSettings({theme:button.dataset.themeChoice});document.querySelectorAll('.theme-choice').forEach(b=>b.classList.toggle('selected',b===button));return;}
  if(button.classList.contains('copy-code')){await navigator.clipboard.writeText(button.closest('.code-block').querySelector('code').textContent);toast('Код скопирован');return;}
  if(button.classList.contains('copy-message')){await navigator.clipboard.writeText(button.closest('.message').dataset.raw || '');toast('Ответ скопирован');return;}
  switch(button.id){
    case 'desktop-widget':await api('/api/widget/start',{});toast('Помощник появился в правом нижнем углу. Нажмите на девочку.');break;
    case 'image-button':if(!state.busy)$('image-input').click();break;
    case 'upload-document':case 'attach-button':$('file-input').click();break;
    case 'save-project':await saveSettings({workspace:$('project-path').value,tools_enabled:true});toast('Папка подключена, инструменты включены');break;
    case 'list-project':{const result=await api('/api/tools',{name:'project_list',arguments:{}});$('project-results').innerHTML=result.files.map(path=>`<button data-read-file="${esc(path)}">${icon('code')}${esc(path)}</button>`).join('') || 'Текстовых файлов не найдено';$('project-results').className='file-browser';break;}
    case 'show-audit':{const result=await api('/api/audit');$('project-results').textContent=result.map(r=>new Date(r.created*1000).toLocaleString()+' · '+r.action+' · '+r.detail).join('\n') || 'Журнал пуст';$('project-results').className='diff';break;}
    case 'search-knowledge':{const results=await api('/api/knowledge/search',{query:$('knowledge-query').value});$('knowledge-results').innerHTML=results.map(r=>`<div class="list-card"><strong>${esc(r.name)} · фрагмент ${r.position+1}</strong><p>${esc(r.content)}</p></div>`).join('') || '<p class="panel-description">Совпадений не найдено</p>';break;}
    case 'export-data':downloadJSON(await api('/api/export'),'CodiAI-my-data.json');break;
    case 'export-profile':downloadJSON(state.settings,'CodiAI-settings.json');break;
    case 'import-profile':{const input=document.createElement('input');input.type='file';input.accept='.json';input.onchange=guard(async()=>{if(!input.files[0])return;if(input.files[0].size>100000)throw new Error('Файл настроек слишком большой');const settings=JSON.parse(await input.files[0].text());if(confirm('Заменить настройки параметрами из файла? Включённые инструменты и память также будут изменены.')){await saveSettings(settings);fillModes();settingsPanel();toast('Настройки импортированы');}});input.click();break;}
  }
}));
$('composer').onsubmit=guard(async e=>{e.preventDefault();await send();});
$('message').onkeydown=guard(async e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();await send();}});
$('message').oninput=()=>{$('message').style.height='auto';$('message').style.height=Math.min($('message').scrollHeight,160)+'px';};
$('new-chat').onclick=guard(newChat);$('refresh-chats').onclick=guard(refreshChats);
$('mode-select').onchange=guard(()=>changeMode($('mode-select').value));
$('mode-picker').onclick=guard(modesPanel);
$('stop-button').onclick=guard(async()=>{await api('/api/stop',{chat_id:state.chat.id});$('activity').textContent='Останавливаю…';});
$('tools-toggle').onclick=guard(()=>{openDialog('Действия ассистента',`<p class="panel-description">${state.settings.tools_enabled?'Включены':'Выключены'}. Когда действия включены, CodiAI может считать, читать подключённый проект и предлагать правки. В Code With Codi включена автоматическая запись с резервной копией; её можно отключить в разделе «Проект».</p><div class="toolbar"><button id="enable-actions" class="primary">${state.settings.tools_enabled?'Выключить действия':'Включить действия'}</button><button data-panel="tools">Подключить проект и посмотреть правки</button><button data-panel="knowledge">Документы и поиск</button></div>`);$('enable-actions').onclick=guard(async()=>{await saveSettings({tools_enabled:!state.settings.tools_enabled});$('panel').close();toast(state.settings.tools_enabled?'Действия включены':'Действия выключены');});});
$('thinking-toggle').onclick=guard(()=>saveSettings({thinking:!state.settings.thinking}));
$('close-panel').onclick=()=>{if(typeof stopLearningPoll==='function')stopLearningPoll();$('panel').close();if(pullTimer)clearTimeout(pullTimer);};
$('panel').onclick=e=>{if(e.target===$('panel')){const r=$('panel').getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)$('panel').close();}};
$('mobile-menu').onclick=()=>{if(window.innerWidth>650)document.body.classList.remove('sidebar-collapsed');else document.querySelector('.sidebar').classList.toggle('open');};
$('sidebar-collapse').onclick=()=>document.body.classList.toggle('sidebar-collapsed');
$('file-input').onchange=guard(async()=>{const file=$('file-input').files[0];if(!file)return;try{if(file.size>1000000)throw new Error('Документ слишком большой. Разделите его на части.');const text=await file.text();if(text.includes('\0'))throw new Error('Загрузите текстовый файл в UTF-8');$('activity').textContent='Индексирую документ…';const result=await api('/api/documents',{name:file.name,text});toast(result.warning?'Добавлено с поиском по словам: embedding-модель недоступна':`Добавлено: ${result.chunks} фрагментов`);if($('panel').open)await panel('knowledge');}finally{$('file-input').value='';$('activity').textContent='';}});
guard(async()=>{const bootstrap=await api('/api/bootstrap');Object.assign(state,bootstrap);fillModes();applyAppearance();await refreshChats();await refreshStatus();setInterval(()=>guard(refreshStatus)(),15000);})().catch(()=>{});

function renderAttachments(){const el=$('attachments');el.hidden=!state.images.length;el.innerHTML=state.images.map(i=>`<div class="attachment"><img src="${esc(i.url)}" alt="${esc(i.name)}"><span>${esc(i.name)}</span><button type="button" data-remove-image="${i.id}" aria-label="Убрать картинку">${icon('close')}</button></div>`).join('');}
async function uploadImages(files){
 if(state.busy || state.uploading)throw new Error('Дождитесь завершения текущего действия');
 state.uploading=true;$('send-button').disabled=true;
 try{for(const file of files){
  if(!['image/png','image/jpeg','image/webp'].includes(file.type))continue;
  if(state.images.length>=2)throw new Error('К одному сообщению можно приложить две картинки');
  if(file.size>15000000)throw new Error('Картинка больше 15 МБ');
  $('activity').textContent='Добавляю картинку…';
  try{const bitmap=await createImageBitmap(file);const scale=Math.min(1,1280/Math.max(bitmap.width,bitmap.height));const canvas=document.createElement('canvas');canvas.width=Math.round(bitmap.width*scale);canvas.height=Math.round(bitmap.height*scale);canvas.getContext('2d').fillStyle='#ffffff';canvas.getContext('2d').fillRect(0,0,canvas.width,canvas.height);canvas.getContext('2d').drawImage(bitmap,0,0,canvas.width,canvas.height);bitmap.close();const data=canvas.toDataURL('image/jpeg',0.88).split(',')[1];state.images.push(await api('/api/images',{name:file.name,data}));renderAttachments();}finally{$('activity').textContent='';}
 }}finally{state.uploading=false;$('send-button').disabled=state.busy;}
}
$('image-input').onchange=guard(async()=>{try{await uploadImages([...$('image-input').files]);}finally{$('image-input').value='';}});
$('composer').addEventListener('paste',guard(async e=>{const files=[...(e.clipboardData?.files || [])].filter(f=>f.type.startsWith('image/'));if(files.length){e.preventDefault();await uploadImages(files);}}));
$('composer').addEventListener('dragover',e=>e.preventDefault());
$('composer').addEventListener('drop',guard(async e=>{e.preventDefault();await uploadImages([...e.dataTransfer.files]);}));
document.addEventListener('change',guard(async e=>{if(e.target.id==='auto-write')await saveSettings({project_autowrite:e.target.checked});}));

$('panel').addEventListener('close',()=>{if(!$('panel').open)panelRequest++;});
