"""Persistent task selection derived from verified chat actions, including old chats."""
from pathlib import Path

def chat_context(chat):
 for message in reversed(chat.get('messages',[])):
  meta=message.get('metadata') or {}
  selected=meta.get('desktop_context')
  if selected:return {k:v for k,v in selected.items() if k in ('file','folder') and isinstance(v,str)}
  action=meta.get('desktop_action') or {}
  path=action.get('path')
  if path and action.get('type') in ('mkdir','rename','write','open','copy','move'):
   target=Path(path)
   return {'folder':str(target)} if action['type']=='mkdir' or target.is_dir() else {'file':str(target),'folder':str(target.parent)}
  for call in reversed(meta.get('tools',[])):
   result=call.get('result',{})
   if result.get('status')=='ok':
    data=result.get('result',{})
    if isinstance(data,dict) and data.get('context'):return data['context']
 return {}
