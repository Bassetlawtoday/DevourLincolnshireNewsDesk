from __future__ import annotations

import customtkinter as ctk
from newsdesk.theme import HEADER_BG,TEXT_MUTED,APP_NAME,VERSION

class NewsDeskStatusBar(ctk.CTkFrame):
    def __init__(self,master,*,module_name:str,height:int=34,**kwargs):
        super().__init__(master,fg_color=HEADER_BG,corner_radius=0,height=height,**kwargs)
        self.module_name=module_name
        self.grid_propagate(False)
        self.grid_columnconfigure(0,weight=1)
        self.status_label=ctk.CTkLabel(self,text=f'{module_name} ready',font=('Arial',11),text_color=TEXT_MUTED,anchor='w')
        self.status_label.grid(row=0,column=0,sticky='w',padx=18,pady=7)
        self.version_label=ctk.CTkLabel(self,text=f'{APP_NAME}  {VERSION}',font=('Arial',10),text_color=TEXT_MUTED)
        self.version_label.grid(row=0,column=1,sticky='e',padx=18,pady=7)
    def set_status(self,text:str): self.status_label.configure(text=text)
    def clear(self): self.status_label.configure(text=f'{self.module_name} ready')
    def set_module(self,name:str): self.module_name=name; self.clear()
    def set_version_text(self,text:str): self.version_label.configure(text=text)