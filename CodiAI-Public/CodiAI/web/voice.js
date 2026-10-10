'use strict';
let voiceTimer=null,voiceBase='',voiceCancelled=false,voicePollBusy=false;
window.codiVoiceRecording=false;
const micMarkup=$('voice-button').innerHTML;
async function loadVoiceDevices(){
 const result=await api('/api/voice/devices'),select=$('voice-device');
 select.replaceChildren(new Option('Автоматически · основной микрофон',''));
 for(const d of result.devices){const option=new Option(`${d.name} · ${d.api}`,String(d.id));option.dataset.identity=JSON.stringify([d.name,d.api]);select.add(option);}
 const saved=localStorage.getItem('codi-voice-identity');
 const match=[...select.options].find(o=>o.dataset.identity===saved);
 if(match)select.value=match.value;
 select.onchange=()=>localStorage.setItem('codi-voice-identity',select.selectedOptions[0]?.dataset.identity || '');
}
function showVoice(v){
 const phase=v.phase || (v.active?'recording':'ready');
 window.codiVoiceRecording=v.active;
 $('send-button').disabled=state.busy || v.active;
 $('voice-button').disabled=phase==='processing';
 $('voice-button').setAttribute('aria-pressed',String(v.active));
 $('voice-button').setAttribute('aria-label',v.active?'Завершить запись голоса':'Записать голос');
 $('voice-button').innerHTML=v.active?'<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="3" fill="currentColor"/></svg><span>Стоп</span>':micMarkup;
 $('voice-panel').dataset.phase=phase;$('voice-device').disabled=v.active;
 $('voice-level').value=v.level || 0;
 const seconds=Math.floor(v.seconds || 0);$('voice-time').textContent=Math.floor(seconds/60)+':'+String(seconds%60).padStart(2,'0');
 $('voice-status').textContent=phase==='loading'?'Подключаю микрофон…':phase==='recording'?'Говорите — идёт запись':phase==='processing'?'Распознаю запись…':voiceCancelled?'Запись отменена':v.error?'Не удалось распознать речь':v.text?'Текст готов — проверьте и отправьте':'Запись завершена без текста';
 $('voice-hint').textContent=(voiceCancelled?'Можно записать ещё раз.':v.error || v.warning) || (v.active?'После речи нажмите «Готово». Запись обрабатывается локально.':voiceCancelled?'Можно записать ещё раз.':'Распознанный текст находится в поле сообщения.');
 $('voice-done').hidden=!v.active;$('voice-done').disabled=phase==='processing';
 $('voice-cancel').hidden=!v.active;
 if(!v.active && !voiceCancelled && v.text){$('message').value=[voiceBase,v.text].filter(Boolean).join(' ');$('message').dispatchEvent(new Event('input'));$('message').focus();}
}
async function pollVoice(){
 if(voicePollBusy)return;
 voicePollBusy=true;
 try{const v=await api('/api/voice');showVoice(v);if(v.active)voiceTimer=setTimeout(()=>guard(pollVoice)(),200);}
 catch(e){window.codiVoiceRecording=false;$('send-button').disabled=state.busy;$('voice-button').disabled=false;$('voice-status').textContent='Связь с микрофоном потеряна';$('voice-hint').textContent=e.message;}
 finally{voicePollBusy=false;}
}
async function finishVoice(cancel=false){
 voiceCancelled=cancel;
 const v=await api('/api/voice/stop',{});showVoice(v);
 if(cancel){$('message').value=voiceBase;$('message').dispatchEvent(new Event('input'));}
 if(voiceTimer)clearTimeout(voiceTimer);voiceTimer=setTimeout(()=>guard(pollVoice)(),100);
}
$('voice-button').onclick=guard(async()=>{
 const v=await api('/api/voice');
 if(v.active)return finishVoice();
 $('voice-panel').hidden=false;await loadVoiceDevices();
 voiceBase=$('message').value.trim();voiceCancelled=false;
 const selected=$('voice-device').value;
 showVoice(await api('/api/voice/start',{device:selected===''?null:Number(selected)}));
 if(voiceTimer)clearTimeout(voiceTimer);voiceTimer=setTimeout(()=>guard(pollVoice)(),100);
});
$('voice-done').onclick=guard(()=>finishVoice());
$('voice-cancel').onclick=guard(()=>finishVoice(true));

$('voice-close').onclick=guard(async()=>{
 // Hide immediately; Stop still finalizes the local recording in the background.
 $('voice-panel').hidden=true;
 const v=await api('/api/voice');
 if(v.active)await finishVoice();
 $('voice-button').focus();
});
$('voice-panel').addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();$('voice-close').click();}});
