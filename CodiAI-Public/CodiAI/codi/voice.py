"""Local dictation with explicit capture, native device rates and finalization."""
import json,queue,threading,time,math
from array import array
from .config import ROOT

class Voice:
 def __init__(self):
  self.lock=threading.Lock();self.cancel=threading.Event();self.model=None;self.device=None
  self.state=self.empty()
 def empty(self):return {'active':False,'loading':False,'phase':'idle','text':'','partial':'','error':'','level':0,'seconds':0,'device':'','warning':''}
 def status(self):
  with self.lock:return dict(self.state)
 def devices(self):
  import sounddevice as sd
  items=sd.query_devices();apis=sd.query_hostapis();default=int(sd.default.device[0]);result=[]
  for n,d in enumerate(items):
   if d['max_input_channels']>0:
    result.append({'id':n,'name':d['name'],'api':apis[d['hostapi']]['name'],'rate':int(d['default_samplerate']),'default':n==default})
  return {'devices':result,'default':default}
 def choose_device(self,sd):
  if self.device is not None:
   info=sd.query_devices(self.device,'input');return self.device,info
  # Use the actual Windows default instead of forcing its WASAPI duplicate.
  default=sd.query_devices(kind='input')
  return None,default
 def open_stream(self,sd,callback):
  items=sd.query_devices();apis=sd.query_hostapis();candidates=[];errors=[]
  try:candidates.append(self.choose_device(sd))
  except Exception as exc:errors.append(str(exc))
  try:
   default=sd.query_devices(kind='input')
   names={d['name'] for _,d in candidates}|{default['name']}
   # Try other APIs for the same physical microphone, never stereo mix/output.
   compatible=[(n,d) for n,d in enumerate(items) if d['max_input_channels']>0 and d['name'] in names]
   compatible.sort(key=lambda item:0 if apis[item[1]['hostapi']]['name']=='MME' else 1)
   candidates.extend(compatible);candidates.append((None,default))
  except Exception as exc:errors.append(str(exc))
  seen=set()
  for device,info in candidates:
   if self.cancel.is_set():return None
   if device in seen:continue
   seen.add(device);stream=None
   try:
    rate=int(info['default_samplerate'])
    stream=sd.RawInputStream(device=device,samplerate=rate,blocksize=max(800,rate//8),dtype='int16',channels=1,callback=callback)
    stream.__enter__()
    return stream,rate,info
   except Exception as exc:
    errors.append(info['name']+': '+str(exc))
    if stream is not None:
     try:stream.close()
     except Exception:pass
  raise RuntimeError('Не удалось открыть доступные входы. Выберите микрофон в панели записи, проверьте доступ Windows и переподключите устройство. '+('; '.join(errors))[-800:])
 def start(self,device=None):
  if device is not None and (type(device) is not int or device<0):raise ValueError('Выберите микрофон из списка')
  with self.lock:
   if self.state['active']:raise ValueError('Микрофон уже используется. Завершите запись')
   self.device=device;self.cancel=threading.Event();self.state={**self.empty(),'active':True,'loading':True,'phase':'loading'}
  threading.Thread(target=self.record,daemon=True).start();return self.status()
 def stop(self):
  with self.lock:
   if self.state['active']:self.state['phase']='processing'
  self.cancel.set();return self.status()
 def record(self):
  try:
   from vosk import Model,KaldiRecognizer,SetLogLevel
   import sounddevice as sd
   SetLogLevel(-1)
   if self.model is None:self.model=Model(str(ROOT/'runtime/speech/vosk-model-small-ru-0.22'))
   if self.cancel.is_set():return
   chunks=queue.Queue(maxsize=64);started=time.monotonic();peak=0
   def callback(data,frames,timing,status):
    nonlocal peak
    raw=bytes(data);samples=array('h',raw)[::8]
    rms=math.sqrt(sum(v*v for v in samples)/max(1,len(samples)))/32768
    peak=max(peak,rms);seconds=time.monotonic()-started
    with self.lock:
     self.state['level']=min(100,round(rms*650));self.state['seconds']=round(seconds,1)
     self.state['warning']='Звук не поступает. Проверьте выбранный микрофон, его громкость и доступ Windows.' if seconds>3 and peak<.0003 else ''
    try:chunks.put_nowait(raw)
    except queue.Full:
     with self.lock:self.state['warning']='Распознавание не успевает за записью. Завершите запись и дождитесь обработки.'
   def consume(data):
    if recognizer.AcceptWaveform(data):
     value=json.loads(recognizer.Result()).get('text','')
     with self.lock:self.state['text']=(self.state['text']+' '+value).strip();self.state['partial']=''
    else:
     with self.lock:self.state['partial']=json.loads(recognizer.PartialResult()).get('partial','')
   opened=self.open_stream(sd,callback)
   if opened is None:return
   stream,rate,info=opened
   try:
    recognizer=KaldiRecognizer(self.model,rate)
    with self.lock:self.state.update(loading=False,phase='recording',device=info['name'])
    while not self.cancel.is_set():
     try:data=chunks.get(timeout=.15)
     except queue.Empty:continue
     consume(data)
   finally:stream.__exit__(None,None,None)
   with self.lock:self.state['phase']='processing'
   while not chunks.empty():consume(chunks.get_nowait())
   final=json.loads(recognizer.FinalResult()).get('text','')
   with self.lock:
    self.state['text']=(self.state['text']+' '+final).strip();self.state['partial']=''
    if not self.state['text']:self.state['error']='Речь не распознана. '+('Звук с микрофона не поступил — выберите другой вход или проверьте доступ Windows.' if peak<.0003 else 'Звук поступает, но слова не распознаны. Говорите ближе к микрофону; используется русский язык.')
  except Exception as exc:
   with self.lock:self.state['error']='Не удалось включить микрофон или распознавание: '+str(exc)
  finally:
   with self.lock:self.state.update(active=False,loading=False,level=0,phase='error' if self.state['error'] else 'ready' if self.state['text'] else 'idle')
