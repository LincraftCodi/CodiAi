"""Validated local image attachments, normalized without metadata."""
import base64
import binascii
import io
import re
import time
from PIL import Image, ImageOps, UnidentifiedImageError
from .storage import new_id

VISION_MODEL = 'qwen3-vl:2b-instruct'
Image.MAX_IMAGE_PIXELS = 20_000_000

class Images:
    def __init__(self, store, directory):
        self.store, self.directory = store, directory
        self.resized_cache={}
        directory.mkdir(parents=True,exist_ok=True)
        with store.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS images(id TEXT PRIMARY KEY,name TEXT NOT NULL,width INTEGER NOT NULL,height INTEGER NOT NULL,created REAL NOT NULL)')

    def add(self, name, encoded):
        if not isinstance(name,str) or not 1 <= len(name) <= 240 or not isinstance(encoded,str) or len(encoded)>8_000_000:
            raise ValueError('Изображение слишком большое или имя недопустимо')
        try:
            raw=base64.b64decode(encoded,validate=True)
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in ('PNG','JPEG','WEBP'):
                    raise ValueError('Поддерживаются PNG, JPEG и WebP')
                if image.width*image.height>20_000_000:
                    raise ValueError('Изображение слишком большое: максимум 20 млн пикселей')
                image.load()
                image=ImageOps.exif_transpose(image).convert('RGB')
                image.thumbnail((1280,1280))
                output=io.BytesIO();image.save(output,'JPEG',quality=88)
                width,height=image.size
        except (binascii.Error,UnidentifiedImageError,OSError,Image.DecompressionBombError) as exc:
            raise ValueError('Не удалось прочитать изображение. Выберите PNG, JPEG или WebP') from exc
        ident=new_id()
        (self.directory/(ident+'.jpg')).write_bytes(output.getvalue())
        with self.store.db() as db:
            db.execute('INSERT INTO images VALUES(?,?,?,?,?)',(ident,name,width,height,time.time()))
        return self.get(ident)

    def get(self, ident):
        if not isinstance(ident,str) or not re.fullmatch('[a-f0-9]{32}',ident):
            raise ValueError('Недопустимый идентификатор картинки')
        with self.store.db() as db:
            row=db.execute('SELECT * FROM images WHERE id=?',(ident,)).fetchone()
        if not row:
            raise ValueError('Изображение не найдено')
        return {**dict(row),'url':'/api/images/'+ident}

    def bytes(self, ident):
        self.get(ident)
        return (self.directory/(ident+'.jpg')).read_bytes()

    def encode(self, ident,max_side=None):
        if max_side is None:return base64.b64encode(self.bytes(ident)).decode('ascii')
        key=(ident,max_side)
        if key not in self.resized_cache:
            with Image.open(io.BytesIO(self.bytes(ident))) as image:
                image.thumbnail((max_side,max_side));buffer=io.BytesIO();image.save(buffer,'JPEG',quality=92)
            if len(self.resized_cache)>=32:self.resized_cache.pop(next(iter(self.resized_cache)))
            self.resized_cache[key]=base64.b64encode(buffer.getvalue()).decode('ascii')
        return self.resized_cache[key]
