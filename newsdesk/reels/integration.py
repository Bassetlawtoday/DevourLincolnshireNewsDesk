"""Additive hooks: retain the installed Social Desk and selection implementation."""
import json, threading
from pathlib import Path
from .core import Store, identity, suggest, render

def brand_name():
    try:
        cfg=json.loads(Path('config/branding.json').read_text(encoding='utf-8'))
        return str(cfg.get('newsroom_name') or cfg.get('brand_name') or cfg.get('name') or cfg.get('title') or cfg.get('app_title') or 'NewsDesk')
    except (OSError,ValueError): return 'NewsDesk'

def install_selection(namespace):
    original=namespace.get('add_story_to_social_desk')
    if not original or getattr(original,'_reel_hook',False): return
    def selected(parent,story,**kwargs):
        draft=original(parent,story,**kwargs)
        if draft is None: return draft
        try:
            from newsdesk.updates.content_gate import has_verified_full_content
            verified=has_verified_full_content(kwargs.get('module_key',''),story)
        except ImportError: verified=False
        key=identity(str(story.url or ''),draft.draft_id); store=Store(); old=store.get(key)
        if old.get('delivery_state') in ('sent','sending','uncertain') or old.get('path') or old.get('delivery_state')=='rendering': return draft
        record=dict(old,id=key,draft_id=draft.draft_id,title=story.title,body=story.body,
                    source_url=story.url,source_kind=kwargs.get('module_key',''),
                    full_content_verified=verified,brand=brand_name(),mode='images',
                    captions=suggest(story.title,story.body),credit=str(getattr(story,'image_credit','') or ''),
                    image_url=str(getattr(story,'image_url','') or ''),rights_approved=False,delivery_state='staged')
        store.put(key,record)
        return draft
    selected._reel_hook=True; namespace['add_story_to_social_desk']=selected

def install_social_desk(cls):
    if getattr(cls,'_reel_hook',False): return
    original=cls._build
    def build(self):
        original(self)
        import customtkinter as ctk
        from .ui import Builder
        from .bbc_ui import BBCDesk
        ctk.CTkButton(self,text='REEL BUILDER / BBC VIDEO',height=42,
                     command=lambda: Builder(self)).pack(fill='x',padx=24,pady=(0,12))
        ctk.CTkButton(self,text='BBC NEWS HUB — COLLECT LINCOLNSHIRE VIDEOS',height=42,
                     command=lambda: BBCDesk(self)).pack(fill='x',padx=24,pady=(0,12))
    send_original=cls._send
    def send(self):
        if self.current and self.current.source_kind=='bbc':
            from tkinter import messagebox
            messagebox.showinfo('BBC video','Open REEL BUILDER / BBC VIDEO to create, preview and send this clip as a Facebook Reel draft.',parent=self)
            return
        return send_original(self)
    cls._send=send
    save_original=cls._save
    def save(self):
        result=save_original(self)
        if result and self.current:
            auto_create(self.current)
        return result
    cls._save=save
    cls._build=build; cls._reel_hook=True

def auto_config():
    try: return json.loads(Path('data/reels/auto.json').read_text())
    except (OSError,ValueError): return {}

def auto_create(draft):
    key=identity(draft.internal_source_url or draft.source_url,draft.draft_id)
    store=Store(); record=store.get(key)
    if not auto_config().get(draft.source_kind) or not record.get('full_content_verified'): return
    if record.get('path') or record.get('delivery_state') in ('sent','sending','uncertain','rendering'): return
    if draft.image_rights_status!='approved' or not draft.image_credit: return
    record.update(rights_approved=True,credit=draft.image_credit,images=[draft.local_image_path] if draft.local_image_path else [],music='')
    image_url=draft.image_url
    def worker():
        try:
            if not record['images'] and image_url:
                from urllib.request import Request,urlopen
                dest=(store.root/key/'source.jpg').resolve(); dest.parent.mkdir(parents=True,exist_ok=True)
                with urlopen(Request(image_url,headers={'User-Agent':'NewsDesk/1.0'}),timeout=30) as response: data=response.read(30*1024*1024+1)
                if len(data)>30*1024*1024: return
                dest.write_bytes(data); record['images']=[str(dest)]
            render(key,record,store=store)
        except Exception as exc:
            current=store.get(key)
            if current.get('delivery_state') not in ('sent','sending','uncertain','rendering'):
                current['auto_error']=str(exc); store.put(key,current)
    threading.Thread(target=worker,daemon=True).start()
