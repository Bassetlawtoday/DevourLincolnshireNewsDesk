from __future__ import annotations
import json, os, subprocess, threading, webbrowser, queue
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox
from urllib.request import Request, urlopen
import customtkinter as ctk
from .core import Store, ReelError, identity, suggest, render
from .integration import brand_name
from .metricool import deliver
from .settings import branding, save_bbc_key, load_bbc_key, theme_for, theme_track, register_track

class Builder(ctk.CTkToplevel):
    def __init__(self,desk):
        super().__init__(desk); self.desk=desk; self.title('NewsDesk Reel Builder — trial'); self.geometry('1000x900')
        self.store=Store(); self.busy=False; self.images=[]; self.video=''; self.music=''
        if not desk._save(): self.destroy(); return
        self.draft=desk.current; self.key=identity(self.draft.internal_source_url or self.draft.source_url,self.draft.draft_id)
        self.record=self.store.get(self.key)
        self.logo=self.record.get('branding',{}).get('logo') or branding()['logo']
        self.events=queue.Queue()
        banner=ctk.CTkFrame(self); banner.pack(fill='x',padx=18,pady=(12,0))
        self.status=ctk.CTkLabel(banner,text='Ready to create a reel.',font=('Arial',22,'bold'),wraplength=920)
        self.status.pack(fill='x',padx=12,pady=10)
        self.progress=ctk.CTkProgressBar(banner,mode='determinate'); self.progress.pack(fill='x',padx=12,pady=(0,12)); self.progress.set(0)
        panel=ctk.CTkScrollableFrame(self); panel.pack(fill='both',expand=True,padx=18,pady=18)
        ctk.CTkLabel(panel,text='20-SECOND REEL / BBC VIDEO',font=('Arial',26,'bold')).pack(anchor='w')
        self.status.configure(text='Reel already created — preview available.' if self.record.get('path') else 'Ready to create a reel.')
        self.mode=ctk.StringVar(value='BBC video' if self.record.get('mode')=='bbc' else 'Image reel')
        ctk.CTkOptionMenu(panel,values=['Image reel','BBC video'],variable=self.mode).pack(anchor='w',pady=8)
        self.brand=self.entry(panel,'Brand',self.record.get('brand') or brand_name())
        ctk.CTkButton(panel,text='CHOOSE DEVOUR LOGO (only if the installed logo is missing)',command=self.choose_logo).pack(anchor='w',pady=5)
        self.logo_label=ctk.CTkLabel(panel,text='Using the installed NewsDesk colours and logo.'); self.logo_label.pack(anchor='w')
        self.credit=self.entry(panel,'Required image credit (BBC is enforced for BBC clips)',self.record.get('credit') or self.draft.image_credit)
        ctk.CTkLabel(panel,text='Story text / BBC supplied video metadata',font=('Arial',18)).pack(anchor='w',pady=6)
        self.body=ctk.CTkTextbox(panel,height=140,font=('Arial',18)); self.body.pack(fill='x')
        self.body.insert('1.0',self.record.get('body') or self.draft.text)
        self.full=ctk.BooleanVar(value=self.record.get('full_content_verified',False))
        ctk.CTkCheckBox(panel,text='Full story verified, or complete BBC video and supplied metadata verified',variable=self.full).pack(anchor='w',pady=6)
        ctk.CTkLabel(panel,text='Captions: one complete caption per line; 3–6 lines',font=('Arial',18)).pack(anchor='w',pady=6)
        self.captions=ctk.CTkTextbox(panel,height=155,font=('Arial',20)); self.captions.pack(fill='x')
        self.captions.insert('1.0','\n'.join(self.record.get('captions') or suggest(self.draft.title,self.draft.text)))
        ctk.CTkButton(panel,text='SUGGEST CAPTIONS FROM FULL STORY',command=self.suggest).pack(anchor='w',pady=6)
        self.media=ctk.CTkLabel(panel,text='Select images, use the story image, or import a BBC clip.',wraplength=900); self.media.pack(fill='x')
        row=ctk.CTkFrame(panel); row.pack(fill='x',pady=6)
        ctk.CTkButton(row,text='CHOOSE IMAGES',command=self.choose_images).pack(side='left',padx=4)
        ctk.CTkButton(row,text='IMPORT BBC CLIP',command=self.choose_video).pack(side='left',padx=4)
        ctk.CTkButton(row,text='OPEN BBC NEWS HUB',command=lambda:webbrowser.open('https://newshub.bbc.co.uk/')).pack(side='left',padx=4)
        ctk.CTkButton(panel,text='BBC NEWS HUB SETTINGS',command=self.bbc_settings).pack(anchor='w',pady=7)
        self.rights=ctk.BooleanVar(value=self.draft.image_rights_status=='approved' or self.record.get('rights_approved',False))
        ctk.CTkCheckBox(panel,text='Source images/video approved for this social use',variable=self.rights).pack(anchor='w',pady=6)
        self.music_mode=ctk.StringVar(value='None'); ctk.CTkOptionMenu(panel,values=['None','Choose track','Auto'],variable=self.music_mode).pack(anchor='w',pady=6)
        self.music_theme=ctk.StringVar(value=theme_for(self.draft.source_kind))
        ctk.CTkLabel(panel,text='Music theme — Auto uses your approved track for this theme').pack(anchor='w')
        ctk.CTkOptionMenu(panel,values=['News','Sport','Events','Business'],variable=self.music_theme).pack(anchor='w',pady=6)
        ctk.CTkButton(panel,text='FREE MUSIC (MIXKIT)',command=lambda:webbrowser.open('https://mixkit.co/free-stock-music/')).pack(anchor='w',pady=5)
        ctk.CTkButton(panel,text='CHOOSE LICENSED MUSIC',command=self.choose_music).pack(anchor='w')
        self.music_label=ctk.CTkLabel(panel,text='No music. BBC original audio is always preserved.'); self.music_label.pack(anchor='w')
        self.music_rights=ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(panel,text='Chosen music licence permits this social use',variable=self.music_rights).pack(anchor='w',pady=6)
        actions=ctk.CTkFrame(panel); actions.pack(fill='x',pady=12)
        self.render_button=ctk.CTkButton(actions,text='CREATE REEL',command=self.create); self.render_button.pack(side='left',padx=4)
        ctk.CTkButton(actions,text='PREVIEW MP4',command=self.preview).pack(side='left',padx=4)
        self.approved=ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(panel,text='I have checked the latest MP4, captions, credits and BBC logo',variable=self.approved).pack(anchor='w',pady=6)
        self.send_button=ctk.CTkButton(panel,text='SEND REEL TO METRICOOL AS FACEBOOK DRAFT',command=self.send); self.send_button.pack(fill='x',pady=8)
        ctk.CTkLabel(panel,text='Separate Reel delivery status. Review and schedule the draft in Metricool.\nCollect BBC videos using the BBC NEWS HUB button in Social Desk.',wraplength=900).pack(fill='x')
        self.images=list(self.record.get('images',[])); self.video=self.record.get('video','')
        if self.draft.local_image_path and not self.images: self.images=[self.draft.local_image_path]
        from .integration import auto_config
        self.auto=ctk.BooleanVar(value=bool(auto_config().get(self.draft.source_kind)))
        ctk.CTkCheckBox(panel,text='Auto-create image reels when verified full stories from this module are saved with approved images in Social Desk',variable=self.auto,command=self.set_auto).pack(anchor='w',pady=8)
        self.after(100,self.lift)
    def set_auto(self):
        from .integration import auto_config
        cfg=auto_config(); cfg[self.draft.source_kind]=self.auto.get()
        self.store.root.joinpath('auto.json').write_text(json.dumps(cfg),encoding='utf-8')

    def entry(self,parent,label,value):
        ctk.CTkLabel(parent,text=label).pack(anchor='w'); entry=ctk.CTkEntry(parent); entry.pack(fill='x',pady=4); entry.insert(0,value); return entry
    def suggest(self):
        lines=suggest(self.draft.title,self.body.get('1.0','end')); self.captions.delete('1.0','end'); self.captions.insert('1.0','\n'.join(lines))
    def choose_images(self):
        selected=filedialog.askopenfilenames(parent=self,filetypes=[('Images','*.jpg *.jpeg *.png')])
        if selected: self.images=list(selected); self.media.configure(text=f'{len(selected)} images selected')
    def choose_video(self):
        selected=filedialog.askopenfilename(parent=self,filetypes=[('BBC video','*.mp4 *.mov')])
        if selected:
            self.video=selected; self.mode.set('BBC video'); self.media.configure(text=Path(selected).name)
    def choose_logo(self):
        selected=filedialog.askopenfilename(parent=self,filetypes=[('Logo image','*.png *.jpg *.jpeg')])
        if selected: self.logo=selected; self.logo_label.configure(text='Logo: '+Path(selected).name)
    def bbc_settings(self):
        dialog=ctk.CTkToplevel(self); dialog.title('BBC News Hub Settings'); dialog.geometry('640x300'); dialog.transient(self)
        ctk.CTkLabel(dialog,text='BBC NEWS HUB API KEY',font=('Arial',22,'bold')).pack(pady=14)
        ctk.CTkLabel(dialog,text='Stored separately from LDRS and Metricool, protected by Windows.').pack()
        entry=ctk.CTkEntry(dialog,show='*',width=560); entry.pack(pady=14)
        label=ctk.CTkLabel(dialog,text='Enter the key here. It is never included in reels or installer files.',wraplength=560); label.pack()
        try:
            if load_bbc_key(): label.configure(text='A BBC key is already saved securely. Enter a replacement only if needed.')
        except Exception:
            label.configure(text='The saved key could not be unlocked by this Windows account.')
        def save():
            try:
                save_bbc_key(entry.get()); entry.delete(0,'end')
                label.configure(text='BBC key saved securely. Use BBC NEWS HUB in Social Desk to collect videos from the last 14 days.')
            except Exception:
                label.configure(text='Key could not be saved. Windows-protected storage is required; try again.')
        ctk.CTkButton(dialog,text='SAVE BBC KEY',command=save).pack(pady=14)
        self.after(100,dialog.lift)
    def choose_music(self):
        selected=filedialog.askopenfilename(parent=self,filetypes=[('Audio','*.mp3 *.wav *.m4a')])
        if selected: self.music=selected; self.music_mode.set('Choose track'); self.music_label.configure(text=Path(selected).name)
    def job(self,work,done,*,creating=False):
        if self.busy: return
        self.busy=True
        self.render_button.configure(state='disabled',text='CREATING REEL…' if creating else 'CREATE REEL')
        self.send_button.configure(state='disabled')
        self.progress.configure(mode='determinate' if creating else 'indeterminate'); self.progress.set(0)
        if not creating: self.progress.start()
        def finish(value=None,error=''):
            self.busy=False; self.progress.stop()
            self.render_button.configure(state='normal',text='CREATE REEL'); self.send_button.configure(state='normal')
            if error:
                self.status.configure(text='REEL CREATION FAILED' if creating else 'DELIVERY FAILED',text_color='#ef4444')
                messagebox.showerror('Reel Builder',error,parent=self)
            else:
                self.progress.set(1); done(value)
        def poll():
            if not self.winfo_exists(): return
            try:
                while True:
                    kind,value=self.events.get_nowait()
                    if kind=='progress': self.status.configure(text=value[0],text_color='#f8fafc'); self.progress.set(value[1])
                    elif kind=='done': finish(value); return
                    elif kind=='error': finish(error=value); return
            except queue.Empty: pass
            self.after(100,poll)
        def worker():
            try: self.events.put(('done',work()))
            except Exception as exc: self.events.put(('error',str(exc)))
        self.after(100,poll); threading.Thread(target=worker,daemon=True).start()
    def create(self):
        if self.busy: return
        old=self.store.get(self.key)
        if old.get('delivery_state') in ('sent','sending','uncertain'):
            messagebox.showinfo('Reel Builder','This story already has a delivered reel or a delivery to check in Metricool.',parent=self); return
        mode='bbc' if self.mode.get()=='BBC video' else 'images'
        music=self.music if self.music_mode.get()=='Choose track' else ''
        if self.music_mode.get()=='Auto' and mode!='bbc':
            if self.draft.source_kind not in ('police','fire'):
                music=theme_track(self.brand.get().strip(),self.music_theme.get())
                if not music:
                    messagebox.showinfo('Music theme','No approved track is assigned to this theme yet. Choose a free music download, select it here and confirm its licence to save it for this theme.',parent=self); return
        if music and self.music_mode.get()=='Choose track' and self.music_rights.get():
            register_track(self.brand.get().strip(),self.music_theme.get(),music)
        style=branding(); style['logo']=self.logo
        record=dict(self.record,id=self.key,draft_id=self.draft.draft_id,title=self.draft.title,source_url=self.draft.internal_source_url or self.draft.source_url,
            source_kind=self.draft.source_kind,mode=mode,body=self.body.get('1.0','end').strip(),full_content_verified=self.full.get(),
            branding=style,music_theme=self.music_theme.get(),brand=self.brand.get().strip(),credit=self.credit.get().strip(),captions=self.captions.get('1.0','end').splitlines(),images=list(self.images),
            video=self.video,rights_approved=self.rights.get(),music=music,
            music_rights_approved=self.music_rights.get() or (bool(music) and self.music_mode.get()=='Auto'))
        image_url=self.draft.image_url
        def work():
            if mode=='images' and not record['images'] and image_url:
                dest=(self.store.root/self.key/'source.jpg').resolve(); dest.parent.mkdir(parents=True,exist_ok=True)
                with urlopen(Request(image_url,headers={'User-Agent':'NewsDesk/1.0'}),timeout=30) as response: payload=response.read(30*1024*1024+1)
                if len(payload)>30*1024*1024: raise ReelError('Source image exceeds 30 MB.')
                dest.write_bytes(payload); record['images']=[str(dest)]
            return render(self.key,record,store=self.store,progress=lambda message,fraction:self.events.put(('progress',(message,fraction))))
        self.status.configure(text='CREATING YOUR REEL — please wait…',text_color='#f8fafc'); self.approved.set(False)
        def done(result):
            self.record=result
            self.status.configure(text=f"REEL CREATED SUCCESSFULLY — {result['duration']:.1f} seconds.",text_color='#22c55e')
            messagebox.showinfo('Reel created',f"Your {result['duration']:.1f}-second reel has been created. Click PREVIEW MP4 to watch it before sending.",parent=self)
        self.job(work,done,creating=True)
    def preview(self):
        record=self.store.get(self.key); path=record.get('path','')
        if not path or not Path(path).is_file(): messagebox.showinfo('Reel Builder','Create the reel first.',parent=self); return
        if os.name=='nt': os.startfile(path)
        else: subprocess.Popen(['xdg-open',path],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    def send(self):
        already=self.store.get(self.key)
        if already.get('delivery_state') in ('sent','sending','uncertain'):
            messagebox.showinfo('Reel delivery',f"Reel already sent or awaiting a delivery check. Metricool post ID: {already.get('metricool_id') or 'check required'}.",parent=self);return
        if not self.approved.get(): messagebox.showwarning('Reel Builder','Preview and approve the latest MP4 first.',parent=self); return
        record=self.store.get(self.key)
        if not record.get('path'): return
        if not self.full.get() or not self.rights.get():
            messagebox.showwarning('Reel Builder','Confirm full story content and source rights before sending.',parent=self); return
        if (('bbc' if self.mode.get()=='BBC video' else 'images')!=record['mode']
            or (record['mode']=='images' and (self.brand.get().strip()!=record['brand'] or self.credit.get().strip()!=record['credit']))
            or (record['mode']=='bbc' and self.video!=record['video'])):
            messagebox.showwarning('Reel Builder','Media or branding changed after rendering. Create and preview a fresh reel.',parent=self); return
        # Captions/full text/media edits after render require a fresh render.
        if self.body.get('1.0','end').strip()!=record['body'] or (record['mode']=='images' and [x.strip() for x in self.captions.get('1.0','end').splitlines() if x.strip()]!=[x.strip() for x in record['captions'] if x.strip()]):
            messagebox.showwarning('Reel Builder','Content changed after rendering. Create and preview a fresh reel.',parent=self); return
        settings=self.desk.settings_store.load()
        if 'facebook' not in settings.get('connected_networks','').split(','):
            messagebox.showwarning('Metricool','Verify the Facebook connection in Social Desk settings first.',parent=self); return
        self.desk._save(); draft=self.desk.current
        try:
            from dateutil.tz import gettz
            scheduled=datetime.fromisoformat(draft.publication_datetime)
            zone=gettz(draft.timezone)
            if zone is None:raise ValueError("Unknown timezone")
            if scheduled.tzinfo is None:scheduled=scheduled.replace(tzinfo=zone)
            if scheduled<=datetime.now(zone):
                messagebox.showwarning('Metricool','This draft date is in the past. Set a future date/time in Social Desk before sending the reel.',parent=self);return
        except (ValueError,KeyError): messagebox.showwarning('Metricool','Enter a valid draft date/time in Social Desk.',parent=self); return
        record['preview_approved']=True; self.store.put(self.key,record)
        text=draft.text
        if draft.include_source_url and draft.source_url: text+='\n\n'+draft.source_url
        self.status.configure(text='Uploading Reel to Metricool…')
        self.job(lambda:deliver(self.key,settings,text,draft.publication_datetime,draft.timezone,self.store),
                 lambda ref:self.status.configure(text=f'Reel sent to Metricool as Facebook draft. ID {ref}. Review and schedule it there.'))
