'use strict';
let studyTimer=null,studySaved=-1,memorySections={studies:false,memories:false},memoryOffset=0,memoryQuery='',readerPage=null,readerHistory=[];
function stopLearningPoll(){if(studyTimer)clearTimeout(studyTimer);studyTimer=null;}
const studyStates={queued:'В очереди',running:'Изучает',stopping:'Останавливается',completed:'Сохранено',partial:'Сохранено частично',stopped:'Остановлено',interrupted:'Прервано перезапуском',error:'Не удалось изучить',imported:'Перенесено'};
function memoryPlural(n,one,few,many){const tail=n%100,unit=n%10;return tail>=11&&tail<=14?many:unit===1?one:unit>=2&&unit<=4?few:many;}
async function refreshLearning(){
 if(!$('study-jobs'))return;
 const jobs=await api('/api/learn');if(!$('study-jobs'))return;
 $('study-jobs').innerHTML=jobs.length?jobs.slice(0,10).map(j=>`<div class="study-card"><div class="study-top"><strong>${esc(j.topic)}</strong><span class="study-state ${esc(j.status)}">${esc(studyStates[j.status] || j.status)}</span></div><div class="study-progress"><strong>${j.progress_percent ?? 0}% плана изучения</strong><progress max="100" value="${j.progress_percent ?? 0}" aria-label="Прогресс изучения темы"></progress><small>Сохранено ${j.saved} из ${j.progress_target || j.max_pages} запланированных источников</small></div><p>${esc(j.progress)}</p><div class="study-footer"><span>${j.saved} ${memoryPlural(j.saved,'источник','источника','источников')} · ${j.minutes?'до '+j.minutes+' мин':'из файла'}</span><button data-study-details="${j.id}">Источники и конспекты</button>${['queued','running','stopping'].includes(j.status)?`<button data-stop-study="${j.id}">Остановить</button>`:`<button class="primary" data-resume-study="${j.id}">${j.saved>=j.max_pages?'Изучить ещё':'Продолжить изучение'}</button><button data-delete-study="${j.id}">Удалить тему и её память</button>`}</div></div>`).join(''):'<p class="panel-description">Изученных тем пока нет. Напишите «изучи математику» или вставьте ссылку выше.</p>';
 const saved=jobs.reduce((n,j)=>n+j.saved,0);if(studySaved>=0 && saved!==studySaved)await renderMemoryList();studySaved=saved;
 if(jobs.some(j=>['queued','running','stopping'].includes(j.status)))studyTimer=setTimeout(()=>guard(refreshLearning)(),1800);
}
async function renderMemoryList(){
 const result=await api('/api/memory/list?q='+encodeURIComponent(memoryQuery)+'&offset='+memoryOffset);if(!$('memory-list'))return;
 $('memory-count').textContent=result.total+' '+memoryPlural(result.total,'запись','записи','записей');
 $('memory-list').innerHTML=result.items.map(m=>`<details class="memory-card"><summary><span>${esc(m.content.slice(0,100))}${m.content.length>100?'…':''}</span><small>${esc(({preferences:'Предпочтение',knowledge:'Изученный материал',learning:'Учебная память'})[m.scope] || m.scope)}</small></summary><div><p class="memory-text">${esc(m.content)}</p><button data-delete-memory="${m.id}">Забыть запись</button></div></details>`).join('') || '<p class="panel-description">Память пуста или по запросу ничего не найдено.</p>';
 $('memory-pagination').innerHTML=`${memoryOffset?'<button id="memory-prev">Предыдущие</button>':''}${memoryOffset+result.items.length<result.total?'<button id="memory-next">Следующие 50</button>':''}`;
}
async function memoryPanel(){
 stopLearningPoll();memoryOffset=0;studySaved=-1;
 openDialog('Память и изучение',`<p class="panel-description">Сохраните факт, поручите изучить тему или вставьте ссылку. CodiAI ищет разные сайты, сохраняет конспекты и сопоставляет цитаты. Достоверность и противоречия требуют проверки по источникам. Процент показывает выполнение выбранного плана по источникам; 100% означает завершение этого плана.</p><form id="memory-form"><label class="field">Что запомнить или изучить?<textarea id="memory-content" rows="3" maxlength="2000" required placeholder="изучи математику\nили ссылка на статью / видео / YouTube-канал\nили факт: я учусь программировать"></textarea></label><div class="memory-options"><label class="field">Область записи<select id="memory-scope"><option value="preferences">Общие предпочтения</option><option value="learning">Учебная память</option>${state.chat?'<option value="current">Текущий разговор / проект</option>':''}</select></label><label class="field">Время изучения<select id="study-minutes"><option value="1">До 1 минуты</option><option value="3" selected>До 3 минут</option><option value="5">До 5 минут</option><option value="10">До 10 минут</option></select></label><button class="primary" type="submit">Добавить</button></div></form><div class="memory-transfer"><div><strong>Перенести память</strong><p>Скачать файл и загрузить его в CodiAI на другом устройстве.</p></div><div class="toolbar"><button id="download-memory">${icon('folder')}Скачать память</button><button id="upload-memory">${icon('attach')}Загрузить память</button></div></div><details id="study-section" class="memory-section" ${memorySections.studies?'open':''}><summary>Изучение сайтов и видео</summary><p class="panel-description">Видео разбираются по доступным субтитрам. Изучение можно остановить; сохранённые материалы останутся. Это пополнение базы знаний, а не обучение весов.</p><div id="study-jobs"></div></details><details id="memories-section" class="memory-section" ${memorySections.memories?'open':''}><summary>Воспоминания</summary><div class="memory-search"><h3>Воспоминания <small id="memory-count"></small></h3><input id="memory-query" placeholder="Поиск в памяти…" value="${esc(memoryQuery)}"><button id="find-memory">Найти</button></div><div id="memory-list"></div><div id="memory-pagination" class="toolbar"></div></details>`);
 for(const [id,key] of [['study-section','studies'],['memories-section','memories']])$(id).ontoggle=()=>{memorySections[key]=$(id).open;};
 $('memory-form').onsubmit=guard(async e=>{
  e.preventDefault();const text=$('memory-content').value.trim(),button=e.target.querySelector('[type=submit]');button.disabled=true;
  try{
   if(/^(изучи|изучить|выучи|исследуй|научись|найди сайты|найди туториалы|найди руководства)\b/i.test(text) || /https?:\/\/\S+/i.test(text)){
    const job=await api('/api/learn',{topic:text,minutes:Number($('study-minutes').value),max_pages:4});toast('Начато изучение: '+job.topic);
   }else{
    let scope=$('memory-scope').value;if(scope==='current')scope=state.chat.mode==='roleplay'?'story:'+state.chat.id:state.chat.mode==='teacher'?'learning':state.settings.workspace?'project:'+state.settings.workspace:'chat:'+state.chat.id;
    await api('/api/memories',{content:text,scope,chat_id:state.chat?.id});toast('Запись сохранена');
   }
   state.settings=(await api('/api/bootstrap')).settings;applyAppearance();$('memory-content').value='';await renderMemoryList();stopLearningPoll();await refreshLearning();
  }finally{button.disabled=false;}
 });
 await Promise.all([renderMemoryList(),refreshLearning()]);
}
async function studyDetails(id){
 const job=await api('/api/learn/'+id);
 openDialog('Изучение: '+job.topic,`<p class="panel-description">${esc(job.progress)}</p><div class="toolbar"><button data-panel="memory">Вернуться в память</button>${['running','queued','stopping'].includes(job.status)?`<button data-stop-study="${id}">Остановить</button>`:`<button class="primary" data-resume-study="${id}">${job.saved>=job.max_pages?'Изучить ещё':'Продолжить изучение'}</button><button data-delete-study="${id}">Удалить тему и её память</button>`}</div>${job.comparison?`<div class="study-card"><h3>Сравнение источников</h3><small>Сайтов: ${job.comparison.domains}. Согласие источников само по себе не доказывает истину.</small><p class="memory-text">${esc(job.comparison.content)}</p></div>`:""}${job.error?`<details class="study-errors"><summary>Недоступные источники</summary><p class="memory-text">${esc(job.error)}</p></details>`:''}${job.sources.map(s=>`<div class="study-card"><strong>${esc(s.title)}</strong><p class="source-url">${esc(s.url)}</p><small>${esc(({video_transcript:'Расшифровка видео',web_text:'Текст сайта',browser_text:'Текст открытой страницы',text:'Текстовый источник'})[s.method] || s.method)}</small><div class="memory-text">${esc(s.summary)}</div><div class="toolbar"><button data-reader-url="${esc(s.url)}">Открыть в браузере</button><button data-delete-memory="${s.memory_id}">Забыть материал</button></div></div>`).join('') || '<p class="panel-description">Конспекты появятся после завершения чтения первого источника.</p>'}`);
}
function readerFrame(){
 openDialog('Браузер CodiAI',`<p class="panel-description">Читайте сайты прямо в приложении или откройте полный браузер. Изученные страницы сохраняются в памяти вместе со ссылками.</p><form id="reader-form" class="browser-address"><input id="reader-url" aria-label="Адрес сайта или тема" placeholder="https://… или тема для поиска" value="${esc(readerPage?.url || '')}" required><button class="primary" type="submit">Открыть</button></form><div class="toolbar browser-actions"><button id="reader-back">Назад</button><button id="native-browser">Полный браузер</button><button id="study-current-page">Изучить страницу</button><button data-panel="memory">Память и прогресс</button></div><div id="reader-view" class="reader-view"><div class="reader-empty">${icon('search')}<h3>Найдём новое</h3><p>Введите ссылку на статью или видео, либо тему — например «алгебра».</p><small>Режим чтения показывает текст. Полный браузер открывает оригинальные сайты с видео и JavaScript.</small></div></div>`);
 $('reader-form').onsubmit=guard(async e=>{e.preventDefault();const value=$('reader-url').value.trim();if(/^https?:\/\//i.test(value))await browseRead(value);else await browseSearch(value);});
}
async function browserPanel(){readerFrame();if(readerPage)paintReader(readerPage);}
function paintReader(page){
 if(!$('reader-view'))return;
 $('reader-url').value=page.url;
 $('reader-view').innerHTML=`<article class="reader-article"><small class="source-url">${esc(page.url)}</small><h2>${esc(page.title)}</h2><div class="reader-method">${page.method==='video_transcript'?'Расшифровка видео с отметками времени':'Текст страницы'}</div><div class="reader-text">${esc(page.text)}</div>${page.links?.length?`<h3>Ссылки страницы</h3><div class="reader-links">${page.links.slice(0,30).map(l=>`<button data-reader-url="${esc(l.url)}">${esc(l.title || l.url)}</button>`).join('')}</div>`:''}</article>`;
}
async function browseRead(url){
 if(!$('reader-view'))readerFrame();$('reader-url').value=url;$('reader-view').innerHTML='<p class="panel-description">Читаю источник…</p>';
 try{const page=await api('/api/browser/read',{url});if(readerPage?.url!==page.url && readerPage)readerHistory.push(readerPage);readerPage=page;paintReader(page);}
 catch(e){if($('reader-view'))$('reader-view').innerHTML=`<div class="reader-empty"><h3>Источник не прочитан</h3><p>${esc(e.message)}</p><button id="native-browser">Открыть оригинал в полном браузере</button></div>`;throw e;}
}
async function browseSearch(topic){
 $('reader-view').innerHTML='<p class="panel-description">Ищу страницы…</p>';const results=await api('/api/browser/search',{topic});if(!$('reader-view'))return;
 $('reader-view').innerHTML=`<h3>Результаты поиска</h3>${results.map(r=>`<button class="search-result" data-reader-url="${esc(r.url)}"><strong>${esc(r.title)}</strong><small>${esc(r.url)}</small></button>`).join('')}`;
}
document.addEventListener('click',guard(async e=>{
 const b=e.target.closest('button');if(!b)return;
 if(b.dataset.studyDetails)return studyDetails(b.dataset.studyDetails);
 if(b.dataset.resumeStudy){b.disabled=true;try{await api('/api/learn/resume',{id:b.dataset.resumeStudy});await memoryPanel();toast('Продолжаю изучение. Сохранённые страницы пропускаются');}finally{b.disabled=false;}return;}
 if(b.dataset.deleteStudy){b.disabled=true;try{await api('/api/learn/delete',{id:b.dataset.deleteStudy});await memoryPanel();toast('Тема, её конспекты и воспоминания удалены. Резервная копия сохранена');}finally{b.disabled=false;}return;}
 if(b.dataset.stopStudy){await api('/api/learn/stop',{id:b.dataset.stopStudy});toast('Изучение останавливается. Сохранённая память останется');if($('study-jobs')){stopLearningPoll();await refreshLearning();}return;}
 if(b.dataset.readerUrl)return browseRead(b.dataset.readerUrl);
 if(b.id==='reader-back'){if(readerHistory.length){readerPage=readerHistory.pop();paintReader(readerPage);}return;}
 if(b.id==='native-browser'){const value=$('reader-url')?.value.trim();await api('/api/browser/open',{url:/^https?:\/\//i.test(value || '')?value:readerPage?.url || 'https://duckduckgo.com/'});toast('Открыт встроенный браузер CodiAI');return;}
 if(b.id==='study-current-page'){const value=$('reader-url').value.trim();if(!/^https?:\/\//i.test(value))throw new Error('Откройте страницу или введите её полный адрес');await api('/api/learn',{topic:readerPage?.title || value,url:value,minutes:3,max_pages:1});await memoryPanel();toast('Страница отправлена на изучение');return;}
 if(b.id==='download-memory'){b.disabled=true;try{downloadJSON(await api('/api/memory/export'),'CodiAI-memory-'+new Date().toLocaleDateString('sv-SE')+'.json');toast('Файл памяти подготовлен');}finally{b.disabled=false;}return;}
 if(b.id==='upload-memory'){$('memory-import-input').click();return;}
 if(b.id==='find-memory'){memoryQuery=$('memory-query').value.trim();memoryOffset=0;await renderMemoryList();return;}
 if(b.id==='memory-prev' || b.id==='memory-next'){memoryOffset=Math.max(0,memoryOffset+(b.id==='memory-next'?50:-50));await renderMemoryList();}
}));
$('memory-import-input').onchange=guard(async()=>{
 const file=$('memory-import-input').files[0];if(!file)return;
 try{
  if(file.size>60000000)throw new Error('Файл памяти больше 60 МБ');
  toast('Переношу воспоминания…');const bundle=JSON.parse(await file.text());const result=await api('/api/memory/import',bundle);
  state.settings=(await api('/api/bootstrap')).settings;applyAppearance();await memoryPanel();toast(`Перенесено: ${result.added.memories} воспоминаний, ${result.added.documents} материалов. Совпадения пропущены: ${result.duplicates_skipped}`);
 }finally{$('memory-import-input').value='';}
});
$('panel').addEventListener('close',stopLearningPoll);
