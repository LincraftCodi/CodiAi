import io,json,unittest
from unittest.mock import Mock,patch
from codi.context_budget import ContextOverflow,estimate,prepare,recover,model_error
from codi.llm import Ollama
from codi.engine import Operation

class ContextBudgetTests(unittest.TestCase):
 def test_exact_reported_overflow_retries_and_keeps_message(self):
  llm=Ollama();op=Operation();error={'error':{'code':400,'message':'request (4169 tokens) exceeds the available context size (4096 tokens), try increasing it','type':'exceed_context_size_error','n_prompt_tokens':4169,'n_ctx':4096}}
  response=io.BytesIO(b'{"message":{"content":"OK"},"done":true}\n')
  llm.request=Mock(side_effect=[model_error(error),response]);payload={'model':'qwen3:4b-instruct','messages':[{'role':'user','content':'Do not lose this request'}],'options':{'num_ctx':4096}}
  rows=list(llm.stream(payload,op));self.assertEqual(rows[0]['message']['content'],'OK')
  self.assertEqual(llm.request.call_args_list[1].args[1]['options']['num_ctx'],8192)
  self.assertEqual(llm.request.call_args_list[1].args[1]['messages'],payload['messages']);self.assertTrue(response.closed);self.assertIsNone(op.response)
 def test_tools_arguments_and_results_are_budgeted(self):
  small={'messages':[{'role':'user','content':'hi'}],'options':{'num_ctx':4096}}
  big={**small,'tools':[{'description':'описание инструмента '*900}]}
  self.assertGreater(estimate(big),estimate(small));self.assertGreater(prepare(big)['options']['num_ctx'],4096)
 def test_old_turns_compacted_without_orphaned_tools_or_losing_latest_input(self):
  messages=[{'role':'system','content':'identity'}]
  for n in range(10):messages.extend([{'role':'user','content':'old'+str(n)+'x'*9000},{'role':'assistant','content':'answer'}])
  messages.extend([{'role':'user','content':'latest request'},{'role':'assistant','content':'','tool_calls':[{'function':{'name':'project_read','arguments':{'path':'app.py'}}}]},{'role':'tool','content':'file result'}])
  payload={'messages':messages,'options':{'num_ctx':4096}}
  result=prepare(payload)
  self.assertEqual(payload['messages'],messages);self.assertLess(len(result['messages']),len(messages));self.assertEqual(result['messages'][-3:],messages[-3:]);self.assertEqual(result['messages'][0],messages[0])
 def test_large_current_tool_result_is_explicitly_marked_as_excerpt(self):
  p={'messages':[{'role':'user','content':'keep latest'},{'role':'assistant','tool_calls':[]},{'role':'tool','content':json.dumps({'status':'ok','result':{'content':'z'*20000}})}],'options':{'num_ctx':16384}}
  updated=recover(p,ContextOverflow(18000,16384));self.assertEqual(updated['messages'][0],p['messages'][0]);self.assertTrue(json.loads(updated['messages'][-1]['content'])['result']['truncated']);self.assertLess(len(updated['messages'][-1]['content']),len(p['messages'][-1]['content']))
 def test_unrelated_failure_is_not_retried(self):
  llm=Ollama();llm.request=Mock(side_effect=model_error('model not found'))
  with self.assertRaisesRegex(RuntimeError,'model not found'):list(llm.stream({'model':'qwen3:4b-instruct','messages':[]},Operation()))
  self.assertEqual(llm.request.call_count,1)
 def test_stop_prevents_overflow_retry(self):
  llm=Ollama();op=Operation()
  def request(*a,**kw):op.cancel();raise ContextOverflow(4169,4096)
  llm.request=Mock(side_effect=request)
  self.assertEqual(list(llm.stream({'model':'qwen3:4b-instruct','messages':[]},op)),[])
  self.assertEqual(llm.request.call_count,1)

 def test_compacted_tool_error_does_not_become_success(self):
  p={'messages':[{'role':'user','content':'latest'},{'role':'tool','content':json.dumps({'status':'error','error':'x'*12000})}],'options':{'num_ctx':16384}}
  updated=recover(p,ContextOverflow(18000,16384))
  self.assertEqual(json.loads(updated['messages'][-1]['content'])['status'],'error')

 def test_engine_preserves_entire_latest_request_for_adapter_budgeting(self):
  import tempfile
  from pathlib import Path
  from server import Application
  from tests.test_core import TEMP,FakeLLM
  with tempfile.TemporaryDirectory(dir=TEMP) as root:
   app=Application(Path(root)/'data',FakeLLM());chat=app.store.create_chat('general')
   request='First important requirement '+('word '*2500)+' final requirement'
   app.store.add_message(chat['id'],'user',request)
   messages,_=app.engine.context(app.store.chat(chat['id']),app.store.settings())
   self.assertEqual(messages[-1]['content'].removesuffix('\n/no_think'),request)

if __name__=='__main__':unittest.main()
