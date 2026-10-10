import json,types,unittest
from unittest.mock import Mock,MagicMock,patch
from codi.voice import Voice

class VoiceCaptureTests(unittest.TestCase):
 def fake_sd(self,stream):
  inputs=[{'name':'Laptop mic','default_samplerate':44100,'max_input_channels':1,'hostapi':0},{'name':'Laptop mic','default_samplerate':48000,'max_input_channels':1,'hostapi':1}]
  def devices(device=None,kind=None):return inputs[0] if kind and device is None else inputs[device] if device is not None else inputs
  return types.SimpleNamespace(RawInputStream=stream,query_devices=devices,query_hostapis=lambda:[{'name':'MME'},{'name':'Windows WASAPI'}],default=types.SimpleNamespace(device=[0,0]))
 def test_native_rate_and_queued_audio_finalized_after_stop(self):
  voice=Voice();voice.model=object();voice.state['active']=True;rates=[];received=[]
  class Recognizer:
   def __init__(self,model,rate):rates.append(rate)
   def AcceptWaveform(self,data):received.append(data);return True
   def Result(self):return json.dumps({'text':'проверка голоса'})
   def FinalResult(self):return json.dumps({'text':'готово'})
  class Stream:
   def __init__(self,**kw):self.kw=kw
   def __enter__(self):
    self.kw['callback'](b'\x00\x10'*1000,1000,None,None);voice.stop();return self
   def __exit__(self,*a):pass
  with patch.dict('sys.modules',{'sounddevice':self.fake_sd(Stream),'vosk':types.SimpleNamespace(KaldiRecognizer=Recognizer,SetLogLevel=Mock(),Model=Mock())}):voice.record()
  result=voice.status();self.assertEqual(rates,[44100]);self.assertEqual(len(received),1);self.assertEqual(result['text'],'проверка голоса готово');self.assertEqual(result['phase'],'ready');self.assertFalse(result['active']);self.assertFalse(result['error'])
 def test_silence_is_an_error_not_false_success(self):
  voice=Voice();voice.model=object();voice.state['active']=True
  recognizer=Mock();recognizer.AcceptWaveform.return_value=False;recognizer.PartialResult.return_value='{}';recognizer.FinalResult.return_value='{}'
  class Stream:
   def __init__(self,**kw):self.kw=kw
   def __enter__(self):self.kw['callback'](b'\0'*2000,1000,None,None);voice.stop();return self
   def __exit__(self,*a):pass
  with patch.dict('sys.modules',{'sounddevice':self.fake_sd(Stream),'vosk':types.SimpleNamespace(KaldiRecognizer=Mock(return_value=recognizer),SetLogLevel=Mock(),Model=Mock())}):voice.record()
  self.assertEqual(voice.status()['phase'],'error');self.assertIn('Звук с микрофона не поступил',voice.status()['error'])
 def test_device_selection_and_validation(self):
  voice=Voice();sd=self.fake_sd(Mock())
  device,info=voice.choose_device(sd);self.assertIsNone(device);self.assertEqual(info['default_samplerate'],44100)
  voice.device=0;self.assertEqual(voice.choose_device(sd)[0],0)
  for device in (-1,'0',True):
   with self.assertRaises(ValueError):voice.start(device)
 def test_invalid_wasapi_falls_back_to_same_microphone_mme(self):
  voice=Voice();voice.device=1;attempts=[]
  class Stream:
   def __init__(self,**kw):
    attempts.append(kw['device'])
    if kw['device']==1:raise RuntimeError('Invalid device [PaErrorCode -9996]')
   def __enter__(self):return self
   def __exit__(self,*a):pass
  stream,rate,info=voice.open_stream(self.fake_sd(Stream),Mock())
  self.assertEqual(attempts,[1,0]);self.assertEqual(rate,44100)
 def test_stale_id_falls_back_to_windows_default(self):
  voice=Voice();voice.device=99
  stream,rate,info=voice.open_stream(self.fake_sd(MagicMock()),Mock())
  self.assertEqual(rate,44100)
 def test_stop_exposes_processing_state(self):
  voice=Voice();voice.state['active']=True
  self.assertEqual(voice.stop()['phase'],'processing');self.assertTrue(voice.cancel.is_set())

if __name__=='__main__':unittest.main()
