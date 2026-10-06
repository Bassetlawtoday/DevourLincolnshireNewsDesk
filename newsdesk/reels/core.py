from __future__ import annotations
import hashlib, json, os, re, shutil, sqlite3, subprocess, tempfile
from contextlib import closing
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path('data/reels')
class ReelError(RuntimeError): pass

def run(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=600,
                            creationflags=0x08000000 if os.name == 'nt' else 0)
    if result.returncode: raise ReelError(result.stderr[-1800:])
    return result.stdout

def tool(name):
    found = shutil.which(name) or str(Path('tools/ffmpeg') / (name + ('.exe' if os.name == 'nt' else '')))
    if not Path(found).is_file(): raise ReelError('FFmpeg and FFprobe are required. See README for installation.')
    return found

def probe(path):
    return json.loads(run([tool('ffprobe'), '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))

def validate(path):
    data = probe(path); video = next((s for s in data['streams'] if s['codec_type']=='video'), {})
    duration = float(data['format'].get('duration',0))
    if not 4 <= duration <= 90.1: raise ReelError('Facebook trial reels must be 4–90 seconds.')
    if video.get('width')!=1080 or video.get('height')!=1920 or video.get('codec_name')!='h264':
        raise ReelError('Expected a 1080 × 1920 H.264 reel.')
    return duration

class Store:
    def __init__(self, root=None):
        self.root=Path(root or ROOT); self.root.mkdir(parents=True,exist_ok=True)
        self.db=self.root/'reels.sqlite'
        with closing(self.connect()) as c:
            c.execute('CREATE TABLE IF NOT EXISTS assets (id TEXT PRIMARY KEY, payload TEXT NOT NULL)'); c.commit()
    def connect(self): return sqlite3.connect(self.db, timeout=30)
    def get(self, key):
        with closing(self.connect()) as c: row=c.execute('SELECT payload FROM assets WHERE id=?',(key,)).fetchone()
        return json.loads(row[0]) if row else {}
    def put(self,key,record):
        with closing(self.connect()) as c:
            c.execute('INSERT OR REPLACE INTO assets VALUES (?,?)',(key,json.dumps(record,ensure_ascii=False))); c.commit()
    def list(self):
        with closing(self.connect()) as c: rows=c.execute('SELECT payload FROM assets').fetchall()
        return [json.loads(x[0]) for x in rows]
    def claim(self,key):
        with closing(self.connect()) as c:
            c.execute('BEGIN IMMEDIATE'); row=c.execute('SELECT payload FROM assets WHERE id=?',(key,)).fetchone()
            record=json.loads(row[0]) if row else {}
            if not record.get('preview_approved'): raise ReelError('Preview and approve this version first.')
            if record.get('delivery_state') in ('sending','sent','uncertain'):
                raise ReelError('This reel has already been sent, or its previous delivery needs checking in Metricool.')
            record['delivery_state']='sending'
            c.execute('UPDATE assets SET payload=? WHERE id=?',(json.dumps(record),key)); c.commit()
            return record

def identity(url, draft_id):
    return hashlib.sha256((url.strip().rstrip('/').casefold() or draft_id).encode()).hexdigest()

def suggest(title, body):
    # Extract whole sentences only; never invent or cut a sentence midway.
    sentences=re.split(r'(?<=[.!?])\s+', re.sub(r'\s+',' ',body).strip())
    chosen=[s for s in sentences if 20<=len(s)<=150 and s.casefold()!=title.casefold()][:3]
    return [title]+chosen+['Read the full story']

def font(size):
    for path in ['C:/Windows/Fonts/arialbd.ttf','/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf']:
        if Path(path).is_file(): return ImageFont.truetype(path,size)
    return ImageFont.load_default()

def wrapped(draw,text,f,width):
    words=text.split(); lines=[]; line=''
    for word in words:
        new=(line+' '+word).strip()
        if draw.textlength(new,font=f)>width and line: lines.append(line); line=word
        else: line=new
    if line: lines.append(line)
    return lines

def slide(image,text,brand,credit,dest,style=None):
    canvas=Image.new('RGB',(1080,1920),'#111827')
    if image:
        with Image.open(image) as source: pic=ImageOps.contain(ImageOps.exif_transpose(source).convert('RGB'),(1000,1020))
        canvas.paste(pic,((1080-pic.width)//2,220+(1020-pic.height)//2))
    d=ImageDraw.Draw(canvas)
    if style is None:
        from .settings import branding
        style=branding()
    logo_path=Path(style.get('logo',''))
    if not logo_path.is_file(): raise ReelError('The NewsDesk logo was not found. Choose your Devour Lincolnshire logo in Reel Builder.')
    d.rectangle((0,0,1080,190),fill=style['header_bg'])
    d.rectangle((0,180,1080,190),fill=style['accent'])
    with Image.open(logo_path) as source_logo:
        logo=ImageOps.contain(source_logo.convert('RGBA'),(150,150))
    canvas.paste(logo,(30,15),logo)
    brand_lines=wrapped(d,brand,font(44),830)
    if len(brand_lines)>2: raise ReelError('Brand name is too long.')
    for i,line in enumerate(brand_lines): d.text((210,35+i*54),line,font=font(44),fill=style['text'])
    lines=wrapped(d,text,font(60),900)
    if len(lines)>6: raise ReelError('Caption is too long for a readable reel. Shorten it before rendering.')
    for i,line in enumerate(lines): d.text((90,1280+i*76),line,font=font(60),fill='white')
    credit_lines=wrapped(d,credit,font(27),900)
    if len(credit_lines)>2: raise ReelError('Credit is too long for the image reel footer.')
    for i,line in enumerate(credit_lines): d.text((90,1790+i*38),line,font=font(27),fill='#cbd5e1')
    canvas.save(dest)

def _render(key, record, *, store=None, progress=lambda message,fraction:None):
    store=store or Store(); previous=store.get(key)
    progress('Preparing your reel…',0.03)
    if previous.get('delivery_state') in ('sent','sending','uncertain'): raise ReelError('A delivered reel cannot be regenerated and sent again.')
    if not record.get('full_content_verified') or not record.get('body','').strip(): raise ReelError('Verified full story content is required.')
    if not record.get('rights_approved'): raise ReelError('Confirm social-use rights for the source images/video.')
    output=(store.root/key).resolve(); output.mkdir(parents=True,exist_ok=True)
    final=output/'reel.mp4'; temp=output/'rendering.mp4'
    ff=tool('ffmpeg')
    with tempfile.TemporaryDirectory(dir=output) as folder:
        work=Path(folder)
        if record.get('mode')=='bbc':
            progress('Preparing BBC video — preserving the full frame and audio…',0.1)
            source=Path(record['video']).resolve(); data=probe(source)
            duration=float(data['format'].get('duration',0))
            if not 4<=duration<=90: raise ReelError('Choose a complete BBC clip lasting 4–90 seconds. This trial does not trim BBC footage.')
            # Letterbox full source frame; BBC logo is never cropped or covered.
            # BBC credit is placed outside the source frame in a separate top band.
            card=work/'bbc.png'; canvas=Image.new('RGB',(1080,1920),'#111827'); d=ImageDraw.Draw(canvas)
            style=record.get('branding')
            if style is None:
                from .settings import branding
                style=branding()
            logo_path=Path(style.get('logo',''))
            if not logo_path.is_file():raise ReelError('Choose your installed Devour logo before creating the BBC reel.')
            d.rectangle((0,0,1080,190),fill=style['header_bg']);d.rectangle((0,180,1080,190),fill=style['accent'])
            with Image.open(logo_path) as logo_source:logo=ImageOps.contain(logo_source.convert('RGBA'),(150,150))
            canvas.paste(logo,(30,15),logo)
            d.text((210,45),record['brand'],font=font(40),fill=style['text'])
            d.text((60,1800),'Video: BBC',font=font(40),fill='white'); canvas.save(card)
            vf='[0:v]scale=1000:1520:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1[v];[1:v][v]overlay=(W-w)/2:(H-h)/2,format=yuv420p[out]'
            run([ff,'-y','-i',str(source),'-loop','1','-i',str(card),'-filter_complex',vf,'-map','[out]','-map','0:a?',
                 '-t',str(duration),'-r','30','-c:v','libx264','-preset','fast','-crf','20','-c:a','aac','-b:a','128k','-ar','48000','-movflags','+faststart',str(temp)])
            original=output/('original'+source.suffix.lower()); shutil.copy2(source,original)
            record.update(credit='BBC',original=str(original),source='BBC News Hub',music='')
        else:
            images=[Path(p).resolve() for p in record.get('images',[]) if Path(p).is_file()]
            if not images: raise ReelError('At least one usable image is required.')
            if not record.get('credit'): raise ReelError('Enter the required image credit.')
            captions=[x.strip() for x in record.get('captions',[]) if x.strip()]
            if not 3<=len(captions)<=6: raise ReelError('Use 3–6 captions for the 20-second reel.')
            segments=[]; duration=20/len(captions)
            for i,text in enumerate(captions):
                progress(f'Creating scene {i+1} of {len(captions)}…',0.1+0.7*i/len(captions))
                card=work/f'card{i}.png'; part=work/f'part{i}.mp4'
                slide(images[i%len(images)],text,record['brand'],record['credit'],card,record.get('branding'))
                run([ff,'-y','-loop','1','-i',str(card),'-t',str(duration),'-vf',
                     f"scale=1080:1920,fade=t=in:st=0:d=0.3,fade=t=out:st={duration-0.3}:d=0.3,format=yuv420p",
                     '-r','30','-c:v','libx264','-preset','fast','-crf','20',str(part)])
                segments.append(part)
            concat=work/'list.txt'; concat.write_text('\n'.join("file '"+p.as_posix()+"'" for p in segments))
            args=[ff,'-y','-f','concat','-safe','0','-i',str(concat)]
            music=record.get('music','')
            if music:
                if not record.get('music_rights_approved'): raise ReelError('Confirm the music licence covers this social use.')
                args+=['-stream_loop','-1','-i',str(Path(music).resolve()),'-af','volume=0.18,afade=t=in:d=1,afade=t=out:st=18:d=2','-map','0:v','-map','1:a','-c:a','aac','-b:a','128k','-ar','48000']
            else: args+=['-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-map','0:v','-map','1:a','-c:a','aac','-b:a','128k']
            progress('Combining scenes and preparing audio…',0.85)
            run(args+['-t','20','-c:v','copy','-movflags','+faststart',str(temp)])
    progress('Checking the completed video…',0.95)
    actual=validate(temp); os.replace(temp,final)
    record.update(id=key,path=str(final),duration=actual,preview_approved=False,delivery_state='ready',metricool_id='')
    store.put(key,record); progress('Reel created successfully.',1.0); return record


def render(key,record,*,store=None,progress=lambda message,fraction:None):
    store=store or Store()
    with closing(store.connect()) as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT payload FROM assets WHERE id=?',(key,)).fetchone()
        old=json.loads(row[0]) if row else {}
        if old.get('delivery_state') in ('rendering','sent','sending','uncertain'):
            raise ReelError('This reel is rendering, delivered, or requires a delivery check.')
        reserved=dict(old,delivery_state='rendering')
        c.execute('INSERT OR REPLACE INTO assets VALUES (?,?)',(key,json.dumps(reserved))); c.commit()
    try: return _render(key,record,store=store,progress=progress)
    except Exception:
        store.put(key,old or dict(record,delivery_state='staged')); raise
