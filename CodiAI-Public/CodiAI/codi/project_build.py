"""Run project build tools in the chosen folder, never pretend text is an APK."""
import os,shutil,subprocess,sys
from pathlib import Path

def build(workspace,kind):
 if not workspace:raise ValueError('Сначала выберите папку проекта')
 root=Path(workspace).resolve(strict=True)
 if kind=='android':
  wrapper=root/'gradlew.bat'
  if not wrapper.is_file():raise ValueError('Нужен Android-проект с gradlew.bat. Сначала создайте проект и установите Android SDK/JDK.')
  command=[str(wrapper),'assembleDebug','--console=plain']
 elif kind in ('npm-build','npm-test'):
  executable=shutil.which('npm.cmd') or shutil.which('npm')
  if not executable:raise ValueError('Node.js/npm не установлен')
  if not (root/'package.json').is_file():raise ValueError('В выбранной папке нет package.json')
  command=[executable,'run','build' if kind=='npm-build' else 'test']
 elif kind=='python-test':command=[sys.executable,'-m','unittest','discover']
 else:raise ValueError('Сборка: android, npm-build, npm-test или python-test')
 completed=subprocess.run(command,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
 artifacts=[str(p.relative_to(root)) for p in root.rglob('*.apk') if p.is_file()] if kind=='android' else []
 return {'exit_code':completed.returncode,'output':completed.stdout.decode('utf-8',errors='replace')[-20000:],'artifacts':artifacts,'success':completed.returncode==0 and (bool(artifacts) if kind=='android' else True)}
