import unittest
from codi.identity import identity_reply
from codi.desktop_controls import quick_command
from tests import test_super_and_widget_actions as fixtures

class IdentityTests(unittest.TestCase):
 setUp=fixtures.SuperAndWidgetTests.setUp
 tearDown=fixtures.SuperAndWidgetTests.tearDown
 def test_direct_identity_in_every_mode_ignores_wrong_history(self):
  for mode in self.app.engine.modes():
   chat=self.app.store.create_chat(mode)
   self.app.store.add_message(chat['id'],'assistant','Я Codex.')
   for question in ('Кто ты?', 'Как тебя зовут?', 'ты кодекс?', 'ты Codex или CodiAI?'):
    reply=self.app.desktop.command(question,{},self.app.store.chat(chat['id']))
    self.assertIn('Я CodiAI',reply['reply']);self.assertTrue(quick_command(question))
  self.assertIsNone(identity_reply('Кто ты в этой истории?'))
  self.assertIsNone(identity_reply('Объясни, как работает Codex'))

 def test_identity_in_special_contexts(self):
  for mode,metadata,prompt in (
   ('general',{},'Привет'),
   ('super',{'research':{'sources':[],'error':'Недоступно'}},'Вопрос'),
   ('desktop',{'vision':'Sample','ocr_text':'Sample'},'Переведи'),
   ('desktop',{'vision':'Sample','ocr_text':'Sample','image_reader':'windows_ocr'},'Ответь на вопрос')):
    chat=self.app.store.create_chat(mode)
    self.app.store.add_message(chat['id'],'user',prompt,metadata=metadata)
    messages,_=self.app.engine.context(self.app.store.chat(chat['id']),self.app.store.settings())
    self.assertTrue(messages[0]['content'].startswith('Ты CodiAI'))

if __name__=='__main__':unittest.main()
