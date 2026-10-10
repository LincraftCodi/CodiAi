"""Budget the complete prompt and recover from a runner's exact token count."""
import copy,json,math,re
MAX_CONTEXT=16384

class ContextOverflow(RuntimeError):
 def __init__(self,required=0,available=0):
  self.required,self.available=required,available
  super().__init__('Запрос превышает рабочее окно локальной модели')

def model_error(detail):
 value=detail
 if isinstance(value,str):
  try:value=json.loads(value)
  except ValueError:pass
 node=value
 for _ in range(3):
  if not isinstance(node,dict) or 'error' not in node:break
  node=node['error']
 text=json.dumps(node,ensure_ascii=False) if isinstance(node,dict) else str(node)
 if 'exceed_context_size_error' in text or re.search(r'exceeds.*context size',text,re.I):
  required=node.get('n_prompt_tokens',0) if isinstance(node,dict) else 0
  available=node.get('n_ctx',0) if isinstance(node,dict) else 0
  match=re.search(r'request\s*\((\d+) tokens\)',text)
  if not required and match:required=int(match[1])
  match=re.search(r'context size\s*\((\d+) tokens\)',text)
  if not available and match:available=int(match[1])
  return ContextOverflow(int(required),int(available))
 return RuntimeError('Ollama: '+str(detail))

def estimate(payload):
 # Count tool schemas, tool arguments/results, template overhead and images too.
 messages=[{k:v for k,v in m.items() if k!='images'} for m in payload.get('messages',[])]
 data={'messages':messages,'tools':payload.get('tools',[])}
 size=len(json.dumps(data,ensure_ascii=False).encode('utf-8'))
 images=sum(len(m.get('images',[])) for m in payload.get('messages',[]))
 return math.ceil(size/3.5)+len(messages)*32+images*1024+512

def window(required,current):
 target=max(current,required)
 return min(MAX_CONTEXT,max(2048,2**math.ceil(math.log2(max(1,target)))))

def drop_old_turn(payload):
 messages=payload.get('messages',[])
 users=[n for n,m in enumerate(messages) if m.get('role')=='user']
 if len(users)<2:return False
 # Preserve the newest user request and all its assistant/tool exchanges.
 boundary=users[1]
 payload['messages']=[m for m in messages[:users[0]] if m.get('role')=='system']+messages[boundary:]
 return True

def prepare(payload):
 payload=copy.deepcopy(payload)
 current=int(payload.get('options',{}).get('num_ctx',4096))
 while estimate(payload)>MAX_CONTEXT and drop_old_turn(payload):pass
 payload.setdefault('options',{})['num_ctx']=window(estimate(payload),current)
 return payload

def recover(payload,error):
 updated=copy.deepcopy(payload);current=int(updated['options']['num_ctx'])
 if current<MAX_CONTEXT:
  updated['options']['num_ctx']=window(max(error.required+512,current+1),current)
  return updated
 target=int(estimate(updated)*MAX_CONTEXT/max(MAX_CONTEXT+1,error.required+512)*.9)
 if drop_old_turn(updated):
  while estimate(updated)>target and drop_old_turn(updated):pass
  return updated
 # A current file/tool result can dominate the context. Keep it valid JSON,
 # mark the excerpt explicitly, and let the model request a smaller portion.
 candidates=[m for m in updated.get('messages',[]) if m.get('role')=='tool' and len(m.get('content',''))>2000]
 if candidates:
  message=max(candidates,key=lambda m:len(m['content']));content=message['content'];length=max(1000,len(content)//3)
  try:original=json.loads(content)
  except ValueError:original={}
  original_status=original.get('status','unknown') if isinstance(original,dict) else 'unknown'
  message['content']=json.dumps({'status':original_status,'result':{'excerpt':content[:length]+'\n…\n'+content[-length:],'truncated':True,'notice':'Результат инструмента сокращён из-за размера окна. Это не полный файл; не утверждай, что прочитан полностью.'}},ensure_ascii=False)
  return updated
 return None
