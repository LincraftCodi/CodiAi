import json
import tempfile
import unittest
from pathlib import Path
from codi.answers import AnswerFilter, visible_answer
from codi.engine import Operation
from server import Application
from tests.test_core import FakeLLM, TEMP

class RefinementTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=TEMP)
        self.root=Path(self.temp.name)
        self.app=Application(self.root/'data',FakeLLM())

    def tearDown(self):
        self.temp.cleanup()

    def test_edit_and_restore_full_conversation(self):
        store=self.app.store
        chat=store.create_chat('general'); ident=chat['id']
        first=store.add_message(ident,'user','Первый вопрос')
        store.add_message(ident,'assistant','Первый ответ')
        store.add_message(ident,'user','Второй вопрос')
        store.add_message(ident,'assistant','Второй ответ')
        changed=store.edit_message(ident,first,'Исправленный вопрос')
        self.assertEqual(len(changed['messages']),1)
        self.assertEqual(changed['title'],'Исправленный вопрос')
        self.assertTrue(changed['has_revision'])
        store.add_message(ident,'assistant','Новый ответ')
        restored=store.restore_revision(ident)
        self.assertEqual(len(restored['messages']),4)
        self.assertEqual(restored['messages'][0]['content'],'Первый вопрос')
        self.assertFalse(restored['has_revision'])
        self.assertEqual(len(store.chats()),1)

    def test_recent_sort_pin_and_no_empty_chats(self):
        store=self.app.store
        first=store.create_chat('general'); second=store.create_chat('general')
        store.create_chat('general')
        store.add_message(first['id'],'user','Старый')
        store.add_message(second['id'],'user','Новый')
        self.assertEqual([c['id'] for c in store.chats()],[second['id'],first['id']])
        with store.db() as db:
            db.execute('UPDATE chats SET pinned=1 WHERE id=?',(first['id'],))
        self.assertEqual([c['id'] for c in store.chats()],[first['id'],second['id']])

    def test_reasoning_never_leaks_across_token_boundaries(self):
        raw='<think>private steps</think>Только ответ.'
        for split in range(len(raw)+1):
            parser=AnswerFilter()
            answer=parser.feed(raw[:split])+parser.feed(raw[split:])+parser.finish()
            self.assertEqual(answer,'Только ответ.')
        self.assertEqual(visible_answer('<think>unfinished'),'')
        self.assertEqual(visible_answer('Ответ <analysis>секрет</analysis> готов'),'Ответ  готов')
        self.assertEqual(visible_answer('if x < 3: return x'),'if x < 3: return x')
        self.assertEqual(visible_answer('legacy private</think>Ответ'),'Ответ')

    def test_stream_and_persistence_filter_reasoning(self):
        def stream(payload,operation):
            yield {'message':{'thinking':'hidden field','content':'<thi'}}
            yield {'message':{'content':'nk>private</think>Ответ'},'done':True}
        self.app.llm.stream=stream
        chat=self.app.store.create_chat('general'); ident=chat['id']
        self.app.store.add_message(ident,'user','Вопрос')
        events=list(self.app.engine.generate(ident,self.app.engine.reserve(ident)))
        self.assertEqual(''.join(e['text'] for e in events if e['type']=='token'),'Ответ')
        self.assertEqual(self.app.store.chat(ident)['messages'][-1]['content'],'Ответ')
        self.assertNotIn('private',json.dumps(events))

    def test_vibe_tools_and_syntax_check_do_not_execute_code(self):
        project=self.root/'project';project.mkdir()
        file=project/'main.py';file.write_text("raise RuntimeError('must not run')",encoding='utf-8')
        settings={**self.app.store.settings(),'workspace':str(project),'tools_enabled':True}
        self.app.store.save_settings(settings)
        checked=self.app.tools.execute('project_check',{'path':'main.py'},settings)
        self.assertFalse(checked['executed'])
        file.write_text('if broken',encoding='utf-8')
        with self.assertRaises(SyntaxError):
            self.app.tools.execute('project_check',{'path':'main.py'},settings)
        chat=self.app.store.create_chat('vibecoding');ident=chat['id']
        self.app.store.add_message(ident,'user','Изучи проект')
        list(self.app.engine.generate(ident,self.app.engine.reserve(ident)))
        names={s['function']['name'] for s in self.app.llm.payloads[-1]['tools']}
        self.assertTrue({'project_read','project_check','propose_write'} <= names)

    def test_text_diff_becomes_real_reviewable_proposal(self):
        project=self.root/'project';project.mkdir()
        (project/'main.py').write_text('old = 1',encoding='utf-8')
        self.app.store.save_settings({**self.app.store.settings(),'workspace':str(project),'tools_enabled':True,'project_autowrite':False})
        rounds=iter([
            {'tool_calls':[{'function':{'name':'project_read','arguments':{'path':'main.py'}}}]},
            {'content':'```diff\nincorrect provisional diff\n```'},
            {'tool_calls':[{'function':{'name':'propose_write','arguments':{'path':'main.py','content':'new = 2'}}}]}
        ])
        def stream(payload,operation):
            yield {'message':next(rounds),'done':True}
        self.app.llm.stream=stream
        chat=self.app.store.create_chat('vibecoding');ident=chat['id']
        self.app.store.add_message(ident,'user','Исправь main.py')
        events=list(self.app.engine.generate(ident,self.app.engine.reserve(ident)))
        content=self.app.store.chat(ident)['messages'][-1]['content']
        self.assertNotIn('incorrect provisional',content)
        self.assertIn('Файлы пока не изменены',content)
        self.assertEqual((project/'main.py').read_text(),'old = 1')
        with self.app.store.db() as db:
            self.assertEqual(db.execute('SELECT content FROM proposals').fetchone()['content'],'new = 2')

if __name__=='__main__':
    unittest.main()
