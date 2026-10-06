"""Video transfer using Metricool's official S3 and scheduler schema."""
import base64, hashlib
from pathlib import Path
from urllib.request import Request, urlopen
from newsdesk.social.metricool import MetricoolClient
from .core import ReelError, Store, validate

class VideoClient(MetricoolClient):
    def upload_video(self,path):
        file=Path(path); size=file.stat().st_size
        if file.suffix.lower()!='.mp4' or not 0<size<=500*1024*1024: raise ReelError('Use an MP4 below the trial limit of 500 MB.')
        chunks=[]; offset=0; part_size=8*1024*1024
        with file.open('rb') as stream:
            while payload:=stream.read(part_size):
                chunks.append({'size':len(payload),'startByte':offset,'endByte':offset+len(payload),
                               'hash':base64.b64encode(hashlib.sha256(payload).digest()).decode()}); offset+=len(payload)
        q={'blogId':self.blog_id,'userId':self.user_id}
        tx=self._data(self._request('PUT','/v2/media/s3/upload-transactions',query=q,
            body={'resourceType':'planner','contentType':'video/mp4','fileExtension':'mp4','parts':chunks}))
        if tx.get('presignedUrl'):
            jobs=[dict(chunks[0],presignedUrl=tx['presignedUrl'],partNumber=1)]
            if len(chunks)!=1: raise ReelError('Metricool returned a simple upload for a multipart file.')
        else: jobs=tx.get('parts',[])
        if len(jobs)!=len(chunks): raise ReelError('Metricool did not supply every video upload part.')
        completed=[]
        with file.open('rb') as stream:
            for i,job in enumerate(jobs):
                expected=chunks[i]
                if int(job.get('startByte',expected['startByte']))!=expected['startByte'] or int(job.get('endByte',expected['endByte']))!=expected['endByte']:
                    raise ReelError('Metricool returned inconsistent upload ranges.')
                stream.seek(expected['startByte']); payload=stream.read(expected['size'])
                req=Request(job['presignedUrl'],data=payload,method='PUT',headers={'Content-Type':'video/mp4','x-amz-checksum-sha256':expected['hash']})
                with urlopen(req,timeout=180) as response:
                    response.read(); etag=response.headers.get('ETag','')
                if not etag and not tx.get('presignedUrl'): raise ReelError('Video upload part has no ETag.')
                completed.append({'partNumber':job.get('partNumber',i+1),'etag':etag})
        if tx.get('presignedUrl'): body={'simple':{'fileUrl':tx['fileUrl']}}
        else: body={'multipart':{'uploadId':tx['uploadId'],'key':tx['key'],'parts':completed}}
        result=self._data(self._request('PATCH','/v2/media/s3/upload-transactions',query=q,body=body))
        value=result.get('convertedFileUrl') or result.get('fileUrl')
        if not value: raise ReelError('Metricool did not confirm the uploaded video URL.')
        return value

    def reel_draft(self,record,text,date,timezone,on_create=lambda:None):
        if not all((self.token,self.user_id,self.blog_id)): raise ReelError('Configure the existing Metricool connection first.')
        validate(record['path']); media=self.upload_video(record['path'])
        body={'publicationDate':{'dateTime':date,'timezone':timezone},'text':text,
              'providers':[{'network':'facebook'}],'media':[media], 'draft':True,'autoPublish':False,
              'shortener':False,'saveExternalMediaFiles':False,
              'facebookData':{'type':'REEL','title':record.get('title','')}}
        on_create()
        result=self._request('POST','/v2/scheduler/posts',query={'blogId':self.blog_id,'userId':self.user_id},body=body)
        ref=self.draft_id(result)
        if not ref: raise ReelError('Metricool returned no post ID. Check Planning before retrying.')
        return ref

def deliver(key,settings,text,date,timezone,store=None):
    store=store or Store(); record=store.claim(key); started=False
    def mark_create():
        nonlocal started
        started=True
    if record.get('mode')=='bbc': text=text.rstrip()+'\n\nVideo: BBC'
    elif record.get('credit'): text=text.rstrip()+'\n\nImages: '+record['credit']
    try:
        client=VideoClient(token=settings['token'],user_id=settings['user_id'],blog_id=settings['blog_id'],timeout=180)
        ref=client.reel_draft(record,text,date,timezone,mark_create)
        record.update(delivery_state='sent',metricool_id=ref,delivered_blog_id=settings['blog_id'])
        store.put(key,record); return ref
    except Exception:
        record['delivery_state']='uncertain' if started else 'ready'
        store.put(key,record); raise
