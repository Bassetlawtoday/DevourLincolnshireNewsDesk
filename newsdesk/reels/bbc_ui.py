"""Main-thread Social Desk admission and background BBC collection."""
import json, queue, threading
from datetime import datetime, timedelta
import customtkinter as ctk
from tkinter import messagebox
from .bbc import collect, open_portal
from .core import Store


def admit(desk,records,reels=None):
    from newsdesk.social.store import SocialDraft
    reels=reels or Store();added=0
    for record in records:
        existing=desk.store.find_by_source_url(desk.drafts,record['source_url'])
        if existing:
            record['draft_id']=existing.draft_id
        else:
            draft=SocialDraft(draft_id=record['draft_id'],title='BBC VIDEO: '+record['title'],
                text=record['title']+'\n\n'+record['body']+'\n\nVideo: BBC',
                source_url='',internal_source_url=record['source_url'],include_source_url=False,
                image_credit='BBC',source_kind='bbc',providers=['facebook'],
                publication_datetime=(datetime.now()+timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),
                timezone='Europe/London')
            desk.drafts.append(draft);added+=1
    desk.store.save(desk.drafts)
    for record in records:
        record['bbc_admitted']=True;reels.put(record['id'],record)
    desk._refresh_list()
    return added

class BBCDesk(ctk.CTkToplevel):
    def __init__(self,desk):
        super().__init__(desk);self.desk=desk;self.title('BBC News Hub — Lincolnshire');self.geometry('880x740')
        self.events=queue.Queue();self.busy=False
        ctk.CTkLabel(self,text='BBC VIDEO • LINCOLNSHIRE • LAST 72 HOURS',font=('Arial',24,'bold')).pack(pady=16)
        ctk.CTkLabel(self,text='Confirmed Lincolnshire videos enter Social Desk with their original clip ready in Reel Builder.\nBroad BBC regions need a separate location check. Current BBC website filters are respected.',wraplength=820).pack(padx=20,pady=8)
        self.status=ctk.CTkLabel(self,text='Ready to collect.',font=('Arial',20,'bold'),wraplength=820);self.status.pack(pady=12)
        self.progress=ctk.CTkProgressBar(self,mode='indeterminate');self.progress.pack(fill='x',padx=24,pady=10)
        self.button=ctk.CTkButton(self,text='COLLECT BBC VIDEOS — LAST 72 HOURS',command=self.start,height=44);self.button.pack(fill='x',padx=24,pady=8)
        self.portal_button=ctk.CTkButton(self,text='OPEN BBC NEWS HUB / CHANGE REGION FILTERS',command=self.open_portal);self.portal_button.pack(pady=6)
        self.summary=ctk.CTkTextbox(self,height=135,font=('Arial',17));self.summary.pack(fill='x',padx=24,pady=10)
        ctk.CTkLabel(self,text='Recent clips needing a location check — open the source to review',font=('Arial',18)).pack()
        self.review=ctk.CTkScrollableFrame(self);self.review.pack(fill='both',expand=True,padx=24,pady=10)
        ctk.CTkLabel(self,text='No automatic publishing. Confirm rights, create and preview the reel, then send a Metricool draft.\nThe current builder accepts complete 4–90 second clips; longer clips remain outside this import.',wraplength=820).pack(pady=8)
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.after(100,self.lift)
    def close(self):
        if self.busy:messagebox.showinfo('BBC collection','Please wait for the BBC task to finish.',parent=self)
        else:self.destroy()
    def open_portal(self,url='https://newshub.bbc.co.uk/explorer'):
        if self.busy:return
        self.busy=True;self.status.configure(text='Opening BBC News Hub and signing you in…')
        self.button.configure(state='disabled');self.portal_button.configure(state='disabled',text='SIGNING IN…')
        self.progress.start()
        def work():
            try:
                driver=open_portal(url,getattr(self.desk,'_bbc_portal_browser',None))
                self.events.put(('portal_ready',driver))
            except Exception as exc:
                from .core import ReelError
                self.events.put(('portal_error',str(exc) if isinstance(exc,ReelError) else 'BBC portal could not open. Check Chrome and your connection, then retry.'))
        threading.Thread(target=work,daemon=True).start();self.after(100,self.poll)
    def start(self):
        if self.busy:return
        if getattr(self.desk,'_bbc_collecting',False):return
        self.busy=True;self.desk._bbc_collecting=True
        self.button.configure(state='disabled',text='COLLECTING BBC VIDEOS…');self.portal_button.configure(state='disabled');self.progress.start()
        def work():
            try:self.events.put(('done',collect(lambda text:self.events.put(('progress',text)))))
            except Exception as exc:self.events.put(('error',str(exc)))
        threading.Thread(target=work,daemon=True).start();self.after(100,self.poll)
    def poll(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind in ('portal_ready','portal_error'):
                    self.busy=False;self.progress.stop();self.button.configure(state='normal')
                    self.portal_button.configure(state='normal',text='OPEN BBC NEWS HUB / CHANGE REGION FILTERS')
                    if kind=='portal_ready':
                        self.desk._bbc_portal_browser=value
                        self.status.configure(text='BBC News Hub signed in. Save your region filters there, then collect again here.')
                    else:self.status.configure(text=value)
                    return
                if kind=='progress':self.status.configure(text=value)
                else:
                    self.busy=False;self.desk._bbc_collecting=False;self.progress.stop()
                    self.button.configure(state='normal',text='COLLECT BBC VIDEOS — LAST 72 HOURS');self.portal_button.configure(state='normal')
                    if kind=='error':self.status.configure(text=value);return
                    try:added=admit(self.desk,value['imported'])
                    except Exception:
                        self.status.configure(text='Downloaded clips retained. Social Desk could not save; retry collection.');return
                    self.status.configure(text=f"{'BBC collection paused' if value.get('partial') else 'BBC collection complete'} — {added} new videos added to Social Desk.")
                    self.summary.delete('1.0','end')
                    self.summary.insert('1.0',f"{value.get('error','')}\nMetadata records checked: {value['scanned']}\nAlready imported: {value['duplicates']}\nLocation needs review: {len(value['review'])}\nDownload/detail failures or incompatible clips: {value['failed']}\nSaved BBC region filters: {json.dumps(value['filters'],ensure_ascii=False)}" + ('\nPage limit reached; collection is partial.' if value['limit_reached'] else ''))
                    for child in self.review.winfo_children():child.destroy()
                    review_path=Store().root/'bbc-review.json'
                    try:previous=json.loads(review_path.read_text(encoding='utf-8'))
                    except (OSError,ValueError):previous=[]
                    rows={row['id']:row for row in previous}
                    rows.update({row['id']:row for row in value['review']})
                    from .bbc import timestamp
                    from datetime import timezone
                    cutoff=datetime.now(timezone.utc)-timedelta(hours=72)
                    rows=[row for row in rows.values() if timestamp(row.get('firstcreated')) and timestamp(row['firstcreated'])>=cutoff]
                    review_path.write_text(json.dumps(rows,ensure_ascii=False),encoding='utf-8')
                    for row in rows:
                        ctk.CTkButton(self.review,text=row['headline'],anchor='w',command=lambda url=row['source_url']:self.open_portal(url)).pack(fill='x',pady=4)
                    Store().root.joinpath('bbc-last-collection.json').write_text(json.dumps({k:v for k,v in value.items() if k!='imported'},ensure_ascii=False,indent=2),encoding='utf-8')
                    return
        except queue.Empty:pass
        self.after(100,self.poll)
