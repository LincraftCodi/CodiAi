"""Exercise the actual widget sender without creating windows or capturing a screen."""
import json
import queue
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from widget import Widget
from codi.screen_tasks import SCREEN_TRANSLATE,SCREEN_ANSWER
from tests.test_core import TEMP

class WidgetSendTests(unittest.TestCase):
 def test_selected_region_hides_helper_and_sends_cropped_image(self):
  from unittest.mock import patch
  widget=Widget.__new__(Widget);widget.busy=False;widget.capturing=False;widget.root=Mock();widget.panel=Mock();widget.status=Mock();widget.events=queue.Queue();widget.run_job=lambda work:work();widget.root.after.side_effect=lambda delay,callback:callback();widget.upload=Mock(return_value={'id':'b'*32})
  region=(20,30,450,220)
  with patch('widget.ImageGrab.grab',return_value=Mock()) as grab:
   widget.capture(SCREEN_TRANSLATE,region);grab.assert_called_once_with(bbox=region)
  widget.root.withdraw.assert_called_once();widget.panel.withdraw.assert_called_once()
  self.assertEqual(widget.events.get(),('captured',({'id':'b'*32},SCREEN_TRANSLATE)))
 def test_screen_requests_after_restart_and_with_selected_context(self):
  for saved in (False,True):
   for chosen in ({},{'folder':'D:/selected-by-user'}):
    for prompt in (SCREEN_TRANSLATE,SCREEN_ANSWER):
     with self.subTest(saved=saved,chosen=chosen,prompt=prompt),tempfile.TemporaryDirectory(dir=TEMP) as folder:
      widget=Widget.__new__(Widget)
      widget.session_path=Path(folder)/'widget-session.json';ident='a'*32
      if saved:widget.session_path.write_text(json.dumps({'chat_id':ident}),encoding='utf-8')
      widget.chat=None;widget.busy=False;widget.capturing=False;widget.images=[{'id':'b'*32}];widget.context=chosen.copy();widget.events=queue.Queue()
      widget.client=Mock();widget.input=Mock();widget.send_button=Mock();widget.status=Mock();widget.write=Mock();widget.run_job=lambda work:work()
      restored={'mode':'desktop','messages':[{'metadata':{'desktop_context':{'folder':'D:/restored-from-chat'}}}]}
      def request(path,data=None):
       if path=='/api/bootstrap':return {'chats':[]}
       if path=='/api/chats':return {'id':ident}
       if path=='/api/chats/'+ident:return restored
       raise AssertionError(path)
      widget.client.request.side_effect=request;widget.client.stream.return_value=iter([{'type':'token','text':'Ответ'}])
      widget.send(prompt)
      sent=widget.client.stream.call_args.args[0]
      self.assertEqual(sent['message'],prompt);self.assertEqual(sent['images'],['b'*32])
      self.assertEqual(sent['desktop_context'],chosen or ({'folder':'D:/restored-from-chat'} if saved else {}))
      self.assertTrue(widget.session_path.is_file())
      self.assertIn(('done',None),list(widget.events.queue))

if __name__=='__main__':unittest.main()
