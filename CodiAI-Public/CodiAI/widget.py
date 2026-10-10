"""Lightweight native corner assistant. Requests stay on localhost."""
import base64
import ctypes
import io
import json
import os
import queue
import re
import logging
from codi.desktop_controls import quick_command
from codi.screen_tasks import SCREEN_TRANSLATE,SCREEN_ANSWER,needs_screen
import threading
import urllib.request
import urllib.error
import webbrowser
from pathlib import Path

ROOT=Path(__file__).resolve().parent
(ROOT/'data/logs').mkdir(parents=True,exist_ok=True)
logging.basicConfig(filename=str(ROOT/'data/logs/widget-exceptions.log'),level=logging.ERROR,encoding='utf-8')
# Bundled Python has Tcl here; a standard Python/venv discovers its own Tcl.
if (ROOT/'runtime/python/tcl/tcl8.6').is_dir():
 os.environ.setdefault('TCL_LIBRARY',str(ROOT/'runtime/python/tcl/tcl8.6'))
 os.environ.setdefault('TK_LIBRARY',str(ROOT/'runtime/python/tcl/tk8.6'))
import tkinter as tk
from tkinter import filedialog,simpledialog
from tkinter.scrolledtext import ScrolledText
from PIL import Image, ImageGrab, ImageTk

class Client:
    def __init__(self,base='http://127.0.0.1:8765'):
        self.base=base.rstrip('/')
        self.opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));self.token=''
    def request(self,path,data=None):
        if data is not None and not self.token:self.token=self.request('/api/bootstrap')['token']
        request=urllib.request.Request(self.base+path,data=None if data is None else json.dumps(data).encode('utf-8'),headers={'Content-Type':'application/json','X-Codi-Token':self.token})
        try:
            with self.opener.open(request,timeout=360) as response:return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code==403:
                self.token=self.request('/api/bootstrap')['token']
                request.headers['X-codi-token']=self.token
                with self.opener.open(request,timeout=360) as response:return json.load(response)
            try:message=json.load(exc)['error']
            except Exception:message='Не удалось выполнить действие'
            raise RuntimeError(message) from exc
    def stream(self,data):
        self.token=self.request('/api/bootstrap')['token']
        request=urllib.request.Request(self.base+'/api/chat',data=json.dumps(data).encode('utf-8'),headers={'Content-Type':'application/json','X-Codi-Token':self.token})
        try:
            with self.opener.open(request,timeout=None) as response:
                if 'application/json' in response.headers.get('Content-Type',''):
                    result=json.load(response)
                    if result.get('desktop_context'):yield {'type':'context','value':result['desktop_context'],'workspace_change':True}
                    yield {'type':'token','text':result.get('reply','Готово')};return
                for line in response:
                    if line.strip():yield json.loads(line)
        except urllib.error.HTTPError as exc:
            try:message=json.load(exc)['error']
            except Exception:message='Не удалось выполнить запрос'
            raise RuntimeError(message) from exc

class Widget:
    bg='#202633';surface='#2b3444';accent='#78a6ff';text='#eef4ff'
    def __init__(self):
        self.client=Client();self.events=queue.Queue();self.chat=None;self.busy=False;self.capturing=False;self.images=[];self.context={};self.drag=None
        self.session_path=ROOT/'data/widget-session.json'
        self.root=tk.Tk();self.root.title('CodiAI — маленький ассистент');self.root.overrideredirect(True);self.root.attributes('-topmost',True)
        self.root.configure(bg='#010101')
        if os.name=='nt':self.root.attributes('-transparentcolor','#010101')
        image=Image.open(ROOT/'web/assets/original.png').convert('RGBA');image.thumbnail((96,96))
        self.avatar=ImageTk.PhotoImage(image)
        label=tk.Label(self.root,image=self.avatar,bg='#010101',borderwidth=0,cursor='hand2');label.pack()
        self.root.geometry(f'100x108+{self.root.winfo_screenwidth()-118}+{self.root.winfo_screenheight()-154}')
        label.bind('<ButtonPress-1>',self.drag_start);label.bind('<B1-Motion>',self.drag_move);label.bind('<ButtonRelease-1>',self.release)
        menu=tk.Menu(self.root,tearoff=False);menu.add_command(label='Открыть помощника',command=self.toggle);menu.add_command(label='Открыть приложение',command=lambda:webbrowser.open('http://127.0.0.1:8765/?v=0.8.5'));menu.add_command(label='Закрыть маленького ассистента',command=self.root.destroy)
        label.bind('<Button-3>',lambda e:menu.tk_popup(e.x_root,e.y_root))
        self.panel=tk.Toplevel(self.root);self.panel.title('CodiAI 0.8.5 · Компьютер');self.panel.configure(bg=self.bg);self.panel.attributes('-topmost',True);self.panel.minsize(360,540);self.panel.geometry(f'400x560+{self.root.winfo_screenwidth()-410}+{max(20,self.root.winfo_screenheight()-610)}');self.panel.protocol('WM_DELETE_WINDOW',self.panel.withdraw)
        tk.Label(self.panel,text='CodiAI · ваш помощник',font=('Segoe UI',13,'bold'),fg=self.text,bg=self.bg).pack(anchor='w',padx=15,pady=(13,3))
        tk.Label(self.panel,text='Команды выполняются сразу · файлы удаляются в Корзину',font=('Segoe UI',9),fg='#a9bbd8',bg=self.bg,wraplength=350).pack(anchor='w',padx=15)
        bar=tk.Frame(self.panel,bg=self.bg);bar.pack(fill='x',padx=12,pady=9)
        for n,(title,command) in enumerate([('Экран',self.capture),('Файл',self.pick_file),('Папка',self.pick_folder),('Программы',self.show_apps),('Голос',self.voice_toggle),('Игра',self.play_game)]):
            self.button(bar,title,command).grid(row=n//3,column=n%3,sticky='ew',padx=3,pady=3)
        for column in range(3):bar.columnconfigure(column,weight=1,uniform='actions')
        screen_bar=tk.Frame(self.panel,bg=self.bg);screen_bar.pack(fill='x',padx=12,pady=(0,4))
        self.button(screen_bar,'Перевести экран',lambda:self.capture(SCREEN_TRANSLATE)).grid(row=0,column=0,sticky='ew',padx=3,pady=3)
        self.button(screen_bar,'Ответить на вопрос',lambda:self.capture(SCREEN_ANSWER)).grid(row=0,column=1,sticky='ew',padx=3,pady=3)
        self.button(screen_bar,'Выделить область',lambda:self.select_region(SCREEN_TRANSLATE)).grid(row=1,column=0,columnspan=2,sticky='ew',padx=3,pady=3)
        for column in range(2):screen_bar.columnconfigure(column,weight=1,uniform='screen-actions')
        self.see_screen=tk.BooleanVar(value=True)
        tk.Checkbutton(self.panel,text='Видеть экран при отправке сообщения',variable=self.see_screen,bg=self.bg,fg=self.text,selectcolor=self.surface,activebackground=self.bg,activeforeground=self.text,font=('Segoe UI',9)).pack(anchor='w',padx=12)
        self.transcript=ScrolledText(self.panel,height=4,wrap='word',font=('Segoe UI',10),bg=self.surface,fg=self.text,insertbackground=self.text,borderwidth=0,padx=10,pady=8,state='disabled');self.transcript.pack(fill='both',expand=True,padx=12,pady=4)
        self.selected=tk.StringVar(value='Файл или картинка не выбраны');tk.Label(self.panel,textvariable=self.selected,wraplength=350,anchor='w',font=('Segoe UI',9),fg='#aec3e7',bg=self.bg).pack(fill='x',padx=13,pady=5)
        self.input=tk.Entry(self.panel,font=('Segoe UI',11),bg=self.surface,fg=self.text,insertbackground=self.text,relief='flat');self.input.pack(fill='x',padx=12,ipady=8);self.input.bind('<Return>',lambda e:self.send())
        footer=tk.Frame(self.panel,bg=self.bg);footer.pack(fill='x',padx=12,pady=10)
        self.send_button=self.button(footer,'Отправить',self.send);self.send_button.pack(side='right')
        self.button(footer,'Стоп',self.stop).pack(side='right',padx=4)
        self.button(footer,'Запомнить',lambda:self.send('запомни это')).pack(side='left')
        self.status=tk.StringVar(value='Готова');tk.Label(self.panel,textvariable=self.status,font=('Segoe UI',9),bg=self.bg,fg='#aec3e7').pack(anchor='w',padx=13,pady=(0,9))
        self.write('Напишите: «создай папку на рабочем столе», «создай файл заметка.txt» или «удали этот файл».\n\n')
        self.panel.withdraw();self.root.after(100,self.poll)
    def button(self,parent,text,command):return tk.Button(parent,text=text,command=command,bg=self.surface,fg=self.text,activebackground='#3c5278',activeforeground=self.text,font=('Segoe UI',9),relief='flat',padx=8,pady=6,cursor='hand2')
    def drag_start(self,e):self.drag=(e.x_root,e.y_root,self.root.winfo_x(),self.root.winfo_y())
    def drag_move(self,e):
        x,y,rx,ry=self.drag;self.root.geometry(f'+{max(0,rx+e.x_root-x)}+{max(0,ry+e.y_root-y)}')
    def release(self,e):
        if self.drag and abs(e.x_root-self.drag[0])+abs(e.y_root-self.drag[1])<6:self.toggle()
        self.drag=None
    def toggle(self):
        if self.panel.state()=='withdrawn':
            x=max(0,min(self.root.winfo_x()-290,self.root.winfo_screenwidth()-410));y=max(20,min(self.root.winfo_y()-560,self.root.winfo_screenheight()-610))
            self.panel.minsize(360,540);self.panel.geometry(f'400x560+{x}+{y}');self.panel.deiconify();self.panel.lift();self.input.focus_force()
        else:self.panel.withdraw()
    def write(self,text):self.transcript.configure(state='normal');self.transcript.insert('end',text);self.transcript.see('end');self.transcript.configure(state='disabled')
    def run_job(self,work):
        def target():
            try:work()
            except Exception as exc:
                logging.exception('Ошибка фонового запроса помощника')
                self.events.put(('error',str(exc)))
        threading.Thread(target=target,daemon=True).start()
    def upload(self,image,name):
        image=image.convert('RGB');image.thumbnail((1280,1280));buffer=io.BytesIO();image.save(buffer,'JPEG',quality=92)
        return self.client.request('/api/images',{'name':name,'data':base64.b64encode(buffer.getvalue()).decode('ascii')})
    def select_region(self,text=None):
        if self.busy or self.capturing:return
        self.capturing=True;self.panel.withdraw();self.root.withdraw()
        overlay=tk.Toplevel(self.root);overlay.overrideredirect(True);overlay.attributes('-topmost',True);overlay.attributes('-alpha',.3)
        overlay.geometry(f'{self.root.winfo_screenwidth()}x{self.root.winfo_screenheight()}+0+0')
        canvas=tk.Canvas(overlay,bg='#152138',highlightthickness=0,cursor='crosshair');canvas.pack(fill='both',expand=True)
        canvas.create_text(25,25,anchor='nw',text='Выделите текст мышью · Esc — отмена',fill='white',font=('Segoe UI',18,'bold'))
        selection={'start':None,'rectangle':None}
        def cancel(event=None):
            overlay.destroy();self.capturing=False;self.root.deiconify();self.panel.deiconify();self.status.set('Готова')
        def begin(event):
            selection['start']=(event.x_root,event.y_root)
            if selection['rectangle']:canvas.delete(selection['rectangle'])
            selection['rectangle']=canvas.create_rectangle(event.x,event.y,event.x,event.y,outline='white',width=3)
        def drag(event):
            if selection['start']:canvas.coords(selection['rectangle'],*selection['start'],event.x_root,event.y_root)
        def finish(event):
            start=selection['start']
            if not start:cancel();return
            x1,y1=start;x2,y2=event.x_root,event.y_root
            bbox=(min(x1,x2),min(y1,y2),max(x1,x2),max(y1,y2))
            if bbox[2]-bbox[0]<20 or bbox[3]-bbox[1]<20:cancel();return
            overlay.destroy();self.capturing=False;self.capture(text,bbox)
        canvas.bind('<ButtonPress-1>',begin);canvas.bind('<B1-Motion>',drag);canvas.bind('<ButtonRelease-1>',finish)
        overlay.bind('<Escape>',cancel);overlay.focus_force()
    def capture(self,text=None,bbox=None):
        if self.busy or self.capturing:return
        self.capturing=True;self.status.set('Снимок экрана…')
        self.panel.withdraw();self.root.withdraw()
        def work():
            image=ImageGrab.grab(bbox=bbox)
            attachment=self.upload(image,'Снимок экрана.jpg')
            self.events.put(('captured',(attachment,text)))
        self.root.after(160,lambda:self.run_job(work))
    def pick_file(self):
        if self.busy:return
        filename=filedialog.askopenfilename(parent=self.panel,title='Выберите файл для CodiAI',initialdir=str(Path.home()))
        if not filename:return
        self.context={'file':filename};self.selected.set('Файл: '+Path(filename).name)
        if Path(filename).suffix.lower() in ('.jpg','.jpeg','.png','.webp'):
            self.run_job(lambda:self.events.put(('image',self.upload(Image.open(filename),Path(filename).name))))
        elif Path(filename).suffix.lower() not in ('.exe','.dll','.zip','.pdf'):
            self.run_job(lambda:self.client.request('/api/settings',{'workspace':str(Path(filename).parent),'tools_enabled':True}))
    def pick_folder(self):
        if self.busy:return
        folder=filedialog.askdirectory(parent=self.panel,title='Папка для работы CodiAI',initialdir=str(Path.home()),mustexist=True)
        if folder:
            self.context={'folder':folder};self.selected.set('Папка: '+folder)
            self.run_job(lambda:self.client.request('/api/settings',{'workspace':folder,'tools_enabled':True}))
    def play_game(self):
        self.run_job(lambda:self.events.put(('game_windows',self.client.request('/api/game/windows'))))
    def begin_game(self,window_id,task):
        def work():
            self.client.request('/api/game/start',{'task':task,'window_id':window_id});self.events.put(('game_hide',None))
            while True:
                state=self.client.request('/api/game');self.events.put(('game',state))
                if not state['active']:break
                threading.Event().wait(.7)
        self.run_job(work)
    def voice_toggle(self):
        typed=self.input.get().strip()
        def work():
            active=self.client.request('/api/voice')['active']
            if not active:self.voice_base=typed
            self.client.request('/api/voice/stop' if active else '/api/voice/start',{})
            while True:
                state=self.client.request('/api/voice');self.events.put(('voice',state))
                if not state['active']:break
                threading.Event().wait(.3)
        self.run_job(work)
    def show_apps(self):
        def work():self.events.put(('apps',self.client.request('/api/desktop/apps')))
        self.run_job(work)
    def send(self,text=None):
        if getattr(self,'voice_active',False):self.status.set('Завершите голосовую запись кнопкой «Голос»');return
        if self.busy or self.capturing:return
        text=text or self.input.get().strip()
        if not text and not self.images:return
        direct=quick_command(text)
        mode='desktop'
        if not self.images and (self.see_screen.get() and not direct and mode!='super' or needs_screen(text)):self.capture(text);return
        self.busy=True;self.send_button.configure(state='disabled');self.status.set('Выполняю…');self.input.delete(0,'end');self.write('Вы: '+text+'\nCodiAI: ')
        attachments=[i['id'] for i in self.images];selection=dict(self.context);self.images=[]
        self.run_job(lambda:self.send_request(text,attachments,selection,mode))
    def send_request(self,text,attachments,request_context,mode='desktop'):
        request_context=dict(request_context)
        if not self.chat:
            restored=None
            try:
                saved=json.loads(self.session_path.read_text(encoding='utf-8'))
                ident=saved.get('chat_id','')
                if re.fullmatch('[a-f0-9]{32}',ident):
                    restored=self.client.request('/api/chats/'+ident)
                    if restored['mode'] in ('desktop','super'):
                        self.chat=ident;self.chat_mode=restored['mode']
            except (OSError,ValueError,KeyError,RuntimeError):pass
            if not self.chat:
                previous=next((item for item in self.client.request('/api/bootstrap')['chats'] if item['mode']=='desktop'),None)
                if previous:
                    self.chat=previous['id'];restored=self.client.request('/api/chats/'+self.chat);self.chat_mode=restored['mode']
            if self.chat:
                self.session_path.write_text(json.dumps({'chat_id':self.chat}),encoding='utf-8')
                if restored and not request_context:
                    for message in reversed(restored['messages']):
                        selected=message.get('metadata',{}).get('desktop_context',{})
                        if selected:
                            request_context={key:value for key,value in selected.items() if key in ('file','folder') and isinstance(value,str)}
                            self.events.put(('restored_context',request_context));break
        if not self.chat:
            self.chat=self.client.request('/api/chats',{'mode':mode})['id'];self.chat_mode=mode
            self.session_path.write_text(json.dumps({'chat_id':self.chat}),encoding='utf-8')
        if getattr(self,'chat_mode',None)!=mode:
            self.client.request('/api/chats/mode',{'id':self.chat,'mode':mode});self.chat_mode=mode
        for event in self.client.stream({'chat_id':self.chat,'message':text,'images':attachments,'desktop_context':request_context}):
            if event['type']=='token':self.events.put(('token',event['text']))
            elif event['type']=='question':self.events.put(('question',event['value']))
            elif event['type']=='context':self.events.put(('direct_context' if event.get('workspace_change') else 'context',event['value']))
            elif event['type'] in ('activity','tool_start'):self.events.put(('status',event.get('text','Работаю с файлами…')))
            elif event['type']=='error':self.events.put(('token','Ошибка: '+event['message']))
        self.events.put(('done',None))
    def stop(self):
        self.run_job(lambda:self.client.request('/api/game/stop',{}))
        if self.chat:self.run_job(lambda:self.client.request('/api/stop',{'chat_id':self.chat}))
    def poll(self):
        while not self.events.empty():
            kind,data=self.events.get()
            if kind=='token':self.write(data)
            elif kind in ('context','direct_context'):
                self.context=data
                if kind=='direct_context' and data.get('folder'):self.run_job(lambda folder=data['folder']:self.client.request('/api/settings',{'workspace':folder,'tools_enabled':True,'project_autowrite':True}))
            elif kind=='restored_context':self.context=data
            elif kind=='status':self.status.set(data)
            elif kind=='done':self.write('\n\n');self.busy=False;self.send_button.configure(state='normal');self.status.set('Готова');self.selected.set('Файл: '+Path(self.context['file']).name if self.context.get('file') else 'Готова к следующей задаче')
            elif kind=='error':self.capturing=False;self.root.deiconify();self.panel.deiconify();self.write('\nОшибка: '+data+'\n');self.busy=False;self.send_button.configure(state='normal');self.status.set('Не удалось выполнить действие')
            elif kind=='question':
                window=tk.Toplevel(self.panel);window.title('CodiAI · уточнение');window.configure(bg=self.bg);window.geometry(f"420x{250+len(data.get('options',[]))*64}");window.minsize(360,300)
                tk.Label(window,text=data['question'],wraplength=380,bg=self.bg,fg=self.text,font=('Segoe UI',11)).pack(fill='x',padx=14,pady=12)
                def answer(value):
                    if self.busy:return
                    if value.strip():window.destroy();self.send(value.strip())
                for option in data.get('options',[]):
                    button=self.button(window,option,lambda value=option:answer(value));button.configure(wraplength=330,justify='left');button.pack(fill='x',padx=14,pady=3)
                custom=tk.Entry(window,font=('Segoe UI',11),bg=self.surface,fg=self.text,insertbackground=self.text);custom.pack(fill='x',padx=14,pady=10);custom.bind('<Return>',lambda e:answer(custom.get()))
                self.button(window,'Отправить свой ответ',lambda:answer(custom.get())).pack(fill='x',padx=14,pady=4)
            elif kind=='game_windows':
                window=tk.Toplevel(self.panel);window.title('Выберите окно игры');window.geometry('560x380');window.configure(bg=self.bg)
                tk.Label(window,text='Выберите игру. Ввод разрешён только в её активном окне.',bg=self.bg,fg=self.text).pack(pady=8)
                listing=tk.Listbox(window,bg=self.surface,fg=self.text);listing.pack(fill='both',expand=True,padx=10)
                for item in data:listing.insert('end',item['title']+' · '+item['process'])
                task=tk.Entry(window,bg=self.surface,fg=self.text,insertbackground=self.text);task.pack(fill='x',padx=10,pady=8);task.insert(0,'Исследуй местность и двигайся к цели')
                def start_game():
                    if not listing.curselection():return
                    ident=data[listing.curselection()[0]]['id'];goal=task.get().strip();window.destroy();self.begin_game(ident,goal)
                self.button(window,'Начать · переключитесь в игру за 3 секунды',start_game).pack(pady=8)
            elif kind=='game_hide':self.panel.withdraw()
            elif kind=='game':
                self.status.set(data['error'] or data['text'])
                if not data['active']:self.panel.deiconify();self.write('\nИгра: '+(data['error'] or data['text'])+'\n')
            elif kind=='voice':
                self.voice_active=data['active']
                if not data['active'] and data['text']:
                    self.input.delete(0,'end');self.input.insert(0,(getattr(self,'voice_base','')+' '+data['text']).strip())
                self.status.set(data['error'] or data.get('warning') or ('Подключаю микрофон…' if data.get('loading') else 'Распознаю запись…' if data.get('phase')=='processing' else 'Говорите · уровень '+str(data.get('level',0))+'% · нажмите «Голос» для завершения' if data['active'] else 'Текст готов. Проверьте и отправьте'))
            elif kind in ('image','captured'):
                attachment,text=data if kind=='captured' else (data,None)
                self.capturing=False
                self.images=[attachment];self.selected.set('Картинка: '+attachment['name']);self.root.deiconify();self.panel.deiconify()
                if text:self.send(text)
            elif kind=='apps':
                window=tk.Toplevel(self.panel);window.title('Установленные программы');window.configure(bg=self.bg)
                listing=tk.Listbox(window,width=45,height=18,font=('Segoe UI',10),bg=self.surface,fg=self.text)
                listing.pack(fill='both',expand=True,padx=10,pady=10)
                for app in data:listing.insert('end',app['name'])
                def choose(e):
                    if listing.curselection():self.send('открой '+data[listing.curselection()[0]]['name']);window.destroy()
                listing.bind('<Double-Button-1>',choose)
        self.root.after(100,self.poll)
    def start(self):self.root.mainloop()

if __name__=='__main__':
    import sys
    if '--check' in sys.argv:
        widget=Widget();widget.root.withdraw();widget.panel.attributes('-alpha',0);widget.panel.deiconify()
        def buttons(parent):
            for child in parent.winfo_children():
                if isinstance(child,tk.Button):yield child
                yield from buttons(child)
        try:
            for width,height in ((360,540),(400,560)):
                widget.panel.geometry(f'{width}x{height}+0+0');widget.root.update();widget.root.update_idletasks()
                for button in buttons(widget.panel):
                    x=button.winfo_rootx()-widget.panel.winfo_rootx();y=button.winfo_rooty()-widget.panel.winfo_rooty()
                    assert x>=0 and y>=0 and x+button.winfo_width()<=width and y+button.winfo_height()<=height,button.cget('text')+' outside panel'
                    assert button.winfo_width()>=button.winfo_reqwidth(),button.cget('text')+' clipped'
            print('Widget OK: all buttons visible at 360x540 and 400x560')
        finally:widget.root.destroy()
    else:
        ctypes.windll.kernel32.CreateMutexW.restype=ctypes.c_void_p
        task_mutex=ctypes.windll.kernel32.CreateMutexW(None,False,'Local\\CodiAIWidget')
        if ctypes.windll.kernel32.GetLastError()!=183:Widget().start()
