"""Brand assets, themed music and a separate Windows-protected BBC key."""
import json, os, tempfile
from pathlib import Path

ROOT=Path('data/reels')
def atomic(path,payload):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(dir=path.parent,suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            json.dump(payload,stream,ensure_ascii=False,indent=2); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:
        if Path(temp).exists(): Path(temp).unlink()

def branding():
    from newsdesk.theme import LOGO_PATH, BRAND_RED, HEADER_BG, TEXT_PRIMARY
    return dict(logo=str(Path(LOGO_PATH).resolve()),header_bg=HEADER_BG,accent=BRAND_RED,text=TEXT_PRIMARY)

def save_bbc_key(key,path=None):
    if not str(key).strip(): raise ValueError('Enter the BBC News Hub key before saving.')
    from newsdesk.social.store import _protect
    # Uses the same Windows DPAPI protection as the existing Metricool settings.
    atomic(path or ROOT/'bbc-key.json',{'protected_key':_protect(str(key).strip())})

def load_bbc_key(path=None):
    from newsdesk.social.store import _unprotect
    try: data=json.loads(Path(path or ROOT/'bbc-key.json').read_text(encoding='utf-8'))
    except (OSError,ValueError): return ''
    return _unprotect(data.get('protected_key',''))

def theme_for(module): return {'sport':'Sport','events':'Events','business':'Business'}.get(module,'News')

def music_library():
    try: return json.loads((ROOT/'music-themes.json').read_text(encoding='utf-8'))
    except (OSError,ValueError): return {}

def register_track(brand,theme,path):
    data=music_library(); data.setdefault(brand,{})[theme]={'path':str(Path(path).resolve()),'approved':True}
    atomic(ROOT/'music-themes.json',data)

def theme_track(brand,theme):
    row=music_library().get(brand,{}).get(theme,{})
    path=row.get('path','')
    return path if row.get('approved') and path and Path(path).is_file() else ''
