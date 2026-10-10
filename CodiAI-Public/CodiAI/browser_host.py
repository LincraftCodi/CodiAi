"""CodiAI native WebView2 browser, no Python bridge exposed to websites."""
import ctypes
import json
import os
import sys
import threading
from pathlib import Path
ROOT=Path(__file__).resolve().parent
os.environ['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS']='--disable-gpu --disable-gpu-compositing --disable-features=ElasticOverscroll'
import clr
clr.AddReference('System.Windows.Forms');clr.AddReference('System.Drawing')
from webview.util import interop_dll_path
clr.AddReference(interop_dll_path('Microsoft.Web.WebView2.Core.dll'));clr.AddReference(interop_dll_path('Microsoft.Web.WebView2.WinForms.dll'))
os.environ['PATH']+=';'+str(Path(interop_dll_path('win-x64')))
from System import Action,String,Uri
from System.Drawing import Color,Font
from System.Threading.Tasks import Task,TaskScheduler
from System.Windows.Forms import Application,Form,Panel,Button,TextBox,Label,DockStyle,Timer,Keys,Padding
from Microsoft.Web.WebView2.WinForms import WebView2,CoreWebView2CreationProperties
from widget import Client
from codi.web_sources import public_url

class Host:
    def __init__(self,url,check=False):
        self.client=Client();self.client.token=self.client.request('/api/bootstrap')['token'];self.check=check;self.poll_busy=False
        self.form=Form();self.form.Text='CodiAI · Браузер';self.form.Width=1120;self.form.Height=780;self.form.BackColor=Color.FromArgb(32,38,51)
        self.bar=Panel();self.bar.Dock=DockStyle.Top;self.bar.Height=58
        self.address=TextBox();self.address.Left=110;self.address.Top=18;self.address.Width=620;self.address.Font=Font('Segoe UI',10);self.address.Text=url
        self.address.KeyDown+=self.key;self.bar.Controls.Add(self.address)
        self.back=self.button('Назад',8,lambda s,e:self.view.GoBack() if self.view.CanGoBack else None)
        self.button('Открыть',738,self.navigate)
        self.study=self.button('Изучить страницу',836,self.capture,width=170)
        self.status=Label();self.status.Dock=DockStyle.Bottom;self.status.Height=30;self.status.Padding=Padding(10,5,0,0);self.status.ForeColor=Color.FromArgb(180,200,230);self.status.Text='Страницы не получают доступа к функциям компьютера. GPU отключён.'
        self.view=WebView2();self.view.Dock=DockStyle.Fill
        properties=CoreWebView2CreationProperties();properties.UserDataFolder=str(ROOT/'data/browser-profile');properties.AdditionalBrowserArguments=os.environ['WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS'];self.view.CreationProperties=properties
        self.view.CoreWebView2InitializationCompleted+=self.ready;self.view.NavigationStarting+=self.starting;self.view.NavigationCompleted+=self.loaded
        self.form.Controls.Add(self.view);self.form.Controls.Add(self.bar);self.form.Controls.Add(self.status)
        self.timer=Timer();self.timer.Interval=800;self.timer.Tick+=self.tick
        self.form.Shown+=self.shown;self.initial_url=url
        if check:
            self.timeout=Timer();self.timeout.Interval=20000;self.timeout.Tick+=self.failed;self.timeout.Start()
    def button(self,title,x,callback,width=92):
        b=Button();b.Text=title;b.Left=x;b.Top=12;b.Width=width;b.Height=34;b.Font=Font('Segoe UI',9);b.ForeColor=Color.White;b.BackColor=Color.FromArgb(50,65,85);b.Click+=callback;self.bar.Controls.Add(b);return b
    def shown(self,s,e):
        self.scheduler=TaskScheduler.FromCurrentSynchronizationContext();self.view.EnsureCoreWebView2Async(None)
    def ready(self,s,e):
        if not e.IsSuccess:
            self.status.Text='WebView2 не запустился: '+str(e.InitializationException)
            if self.check:print(str(e.InitializationException),flush=True);self.failed(s,e)
            return
        core=self.view.CoreWebView2
        core.Settings.AreHostObjectsAllowed=False;core.Settings.IsWebMessageEnabled=False
        core.NewWindowRequested+=self.new_window
        core.DownloadStarting+=self.no_download
        if self.check:print('Native browser OK · WebView2 · GPU disabled',flush=True);self.timeout.Stop();self.form.Close();return
        self.view.Source=Uri(self.initial_url);self.timer.Start()
    def no_download(self,s,e):e.Cancel=True;self.status.Text='Для загрузки файла используйте обычный браузер. Автоматические загрузки отключены.'
    def new_window(self,s,e):
        e.Handled=True
        try:url,_=public_url(str(e.Uri),resolve=False);self.view.Source=Uri(url)
        except ValueError as exc:self.status.Text=str(exc)
    def key(self,s,e):
        if e.KeyCode==Keys.Enter:e.SuppressKeyPress=True;self.navigate(s,e)
    def navigate(self,s=None,e=None):
        try:
            value=self.address.Text.strip();value=value if '://' in value else 'https://'+value
            url,_=public_url(value,resolve=False);self.view.Source=Uri(url)
        except Exception as exc:self.status.Text=str(exc)
    def starting(self,s,e):
        try:public_url(str(e.Uri),resolve=False)
        except ValueError:e.Cancel=True;self.status.Text='Встроенный браузер открывает публичные http/https страницы'
    def loaded(self,s,e):
        if self.view.Source:self.address.Text=str(self.view.Source)
        self.status.Text='Страница открыта. «Изучить страницу» сохранит конспект и источник в памяти.' if e.IsSuccess else 'Страница недоступна. Код браузера: '+str(e.WebErrorStatus)
    def tick(self,s,e):
        if self.poll_busy:return
        self.poll_busy=True;url=str(self.view.Source) if self.view.Source else ''
        def work():
            try:
                result=self.client.request('/api/browser/heartbeat',{'url':url})
                for command in result['commands']:
                    if command['type']=='navigate':self.form.BeginInvoke(Action(lambda url=command['url']:self.go(url)))
            except Exception:pass
            finally:self.poll_busy=False
        threading.Thread(target=work,daemon=True).start()
    def go(self,url):self.address.Text=url;self.navigate()
    def capture(self,s,e):
        self.study.Enabled=False
        script="JSON.stringify({url:location.href,title:document.title.slice(0,240),text:(document.querySelector('article')||document.querySelector('main')||document.body).innerText.slice(0,60000)})"
        def received(task):
            try:page=json.loads(json.loads(str(task.Result)));self.status.Text='Начинаю изучение. Прогресс — в разделе «Память».'
            except Exception as exc:self.status.Text='Не удалось прочитать страницу';self.study.Enabled=True;return
            def work():
                try:
                    result=self.client.request('/api/learn',{'topic':page['title'],'url':page['url'],'page':page,'minutes':3,'max_pages':1})
                    message='Изучение началось: '+result['topic']
                except Exception as exc:message=str(exc)
                self.form.BeginInvoke(Action(lambda:self.after_study(message)))
            threading.Thread(target=work,daemon=True).start()
        self.view.ExecuteScriptAsync(script).ContinueWith(Action[Task[String]](received),self.scheduler)
    def after_study(self,message):self.status.Text=message;self.study.Enabled=True
    def failed(self,s,e):
        print('Native browser initialization failed',flush=True);self.form.Close()
    def run(self):Application.Run(self.form)

if __name__=='__main__':
    from System.Threading import Thread,ThreadStart,ApartmentState
    def main():
        Application.EnableVisualStyles()
        check='--check' in sys.argv
        Host('https://duckduckgo.com/' if check or len(sys.argv)<2 else sys.argv[1],check).run()
    task_ui_thread=Thread(ThreadStart(main));task_ui_thread.SetApartmentState(ApartmentState.STA);task_ui_thread.Start();task_ui_thread.Join()
