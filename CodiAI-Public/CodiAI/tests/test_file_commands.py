import unittest
from unittest.mock import patch
from tests import test_super_and_widget_actions as fixtures
from codi.file_commands import parse_create

class FileCommandTests(unittest.TestCase):
 setUp=fixtures.SuperAndWidgetTests.setUp
 tearDown=fixtures.SuperAndWidgetTests.tearDown
 def command(self,text,context=None):
  return self.app.desktop.command(text,context or {'folder':str(self.root)},self.app.store.create_chat('desktop'))
 def test_folder_name_labels_and_colons(self):
  for n,text in enumerate(('создавай папку с названием документы','создай папку: с названием: Архив','сделай папку под названием Мои проекты','создай папку с именем Фото')):
   result=self.command(text)
   expected=('документы','Архив','Мои проекты','Фото')[n]
   self.assertEqual(result['context']['folder'],str(self.root/expected));self.assertTrue((self.root/expected).is_dir())
 def test_quoted_name_is_literal_and_not_a_second_command(self):
  name='с названием документы и создай папку сюрприз'
  self.command('создай папку «'+name+'»')
  self.assertTrue((self.root/name).is_dir());self.assertFalse((self.root/'сюрприз').exists())
 def test_tool_folder_name_label(self):
  self.app.desktop.create_folder('с названием: Документы',{'folder':str(self.root)})
  self.assertTrue((self.root/'Документы').is_dir())
 def test_file_contents_are_literal_not_location_or_command(self):
  content='На рабочем столе лежит книга и создай папку ловушка.'
  result=self.command('создай текстовый файл с названием заметка с текстом '+content)
  file=self.root/'заметка.txt'
  self.assertEqual(file.read_text(encoding='utf-8'),content);self.assertFalse((self.root/'ловушка').exists());self.assertEqual(result['context']['file'],str(file))
 def test_nested_unicode_files_and_parent_of_selected_file(self):
  existing=self.root/'old.txt';existing.write_text('original',encoding='utf-8')
  result=self.command('создай файл «Проект/страница.html» с кодом <h1>Привет!</h1>',{'file':str(existing)})
  self.assertEqual((self.root/'Проект/страница.html').read_text(encoding='utf-8'),'<h1>Привет!</h1>')
  self.assertEqual(result['context']['folder'],str(self.root/'Проект'))
 def test_existing_files_and_binary_formats_are_preserved(self):
  file=self.root/'keep.txt';file.write_text('important',encoding='utf-8')
  for text in ('создай файл keep.txt с текстом другое','создай файл fake.apk','создай файл ../escape.txt','создай файл CON.txt'):
   with self.assertRaises(ValueError):self.command(text)
  self.assertEqual(file.read_text(encoding='utf-8'),'important');self.assertFalse((self.root/'fake.apk').exists())
 def test_write_content_and_backup(self):
  file=self.root/'keep.txt';file.write_text('original',encoding='utf-8')
  result=self.command('запиши в этот файл текст: Привет и создай папку нет.',{'file':str(file)})
  self.assertEqual(file.read_text(encoding='utf-8'),'Привет и создай папку нет.')
  from pathlib import Path
  self.assertEqual(Path(result['action']['backup']).read_text(encoding='utf-8'),'original');self.assertFalse((self.root/'нет').exists())
 def test_desktop_location_and_quoted_location_name(self):
  desktop=self.root/'desktop';desktop.mkdir()
  with patch.object(self.app.desktop,'desktop_folder',return_value=desktop):
   self.command('создай папку с названием документы на рабочем столе')
  self.assertTrue((desktop/'документы').is_dir())
  self.command('создай файл «на рабочем столе.txt» с текстом «Привет.»')
  self.assertEqual((self.root/'на рабочем столе.txt').read_text(encoding='utf-8'),'Привет.')

if __name__=='__main__':unittest.main()
