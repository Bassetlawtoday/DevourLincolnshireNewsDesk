"""Date-first BBC collection; API contract verified against BBC public web client."""
from __future__ import annotations
import hashlib,json,re,sqlite3,threading,time
from contextlib import closing
from datetime import datetime,timedelta,timezone
from pathlib import Path
from urllib.parse import urlsplit,urlencode,quote
from urllib.request import Request,urlopen,build_opener,HTTPCookieProcessor
from urllib.error import HTTPError
from http.cookiejar import CookieJar
from .core import Store,ReelError,identity,probe,run,tool
from .settings import load_bbc_key
SITE='https://newshub.bbc.co.uk/'
API='https://api.newshub.pa.media'
MEDIA_HOST='content.newshub.lnps.pa.media'
_COLLECT_LOCK=threading.Lock()

def timestamp(value):
    try:
        value=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return value.astimezone(timezone.utc) if value.tzinfo else None
    except (TypeError,ValueError): return None

def decision(item,now=None):
    now=now or datetime.now(timezone.utc)
    created=timestamp(item.get('firstcreated'))
    if not created or not now-timedelta(hours=72)<=created<=now: return 'outside_date_limit',()
    if item.get('pubstatus')!='usable': return 'not_published',()
    embargo=timestamp(item.get('embargotime'))
    if embargo and embargo>now: return 'embargoed',()
    media=item.get('associations',{}).get('media',{})
    if media.get('type')!='video': return 'not_video',()
    from newsdesk.geography.lincolnshire import match_lincolnshire
    # Mixed BBC regions cover other counties; never treat the region label as proof.
    labels=[s.get('name','') for s in item.get('subject',[]) if isinstance(s,dict)]
    locations=[s for s in labels if s.casefold().strip() not in
               ('bbc east yorkshire & lincolnshire','bbc east midlands','bbc radio humberside','humberside')]
    values=[item.get('headline',''),item.get('body_text',''),item.get('description_text',''),*locations]
    values=[re.sub(r'(?:BBC\s+)?East Yorkshire\s*(?:&|and)\s*Lincolnshire','',str(v),flags=re.I) for v in values]
    evidence=match_lincolnshire(values)
    return ('eligible',evidence.places) if evidence.matched else ('location_needs_review',())

def media_url(item):
    href=item.get('associations',{}).get('media',{}).get('renditions',{}).get('original',{}).get('href','')
    if href and not href.startswith(('https://','http://')): href='https://'+href
    p=urlsplit(href)
    if p.scheme!='https' or p.hostname!=MEDIA_HOST or not p.path.lower().endswith('.mp4'):
        raise ReelError('BBC did not provide a supported original MP4 link.')
    return href

def safe_item(item):
    # Persist only metadata needed for review. No raw API responses/media credentials.
    return {k:item.get(k,'') for k in ('id','headline','firstcreated','body_text','description_text')}

def download(item,dest):
    url=media_url(item);limit=500*1024*1024
    temp=dest.with_suffix('.part');dest.parent.mkdir(parents=True,exist_ok=True)
    try:
        with urlopen(Request(url,headers={'User-Agent':'NewsDesk/1.0'}),timeout=45) as response,temp.open('wb') as out:
            length=int(response.headers.get('Content-Length') or 0)
            if length>limit:raise ReelError('BBC video exceeds the 500 MB download limit.')
            total=0
            while True:
                chunk=response.read(1024*1024)
                if not chunk:break
                total+=len(chunk)
                if total>limit:raise ReelError('BBC video exceeds the 500 MB download limit.')
                out.write(chunk)
            if length and total!=length:raise ReelError('BBC video download was incomplete.')
        data=probe(temp)
        duration=float(data.get('format',{}).get('duration',0))
        if not any(s.get('codec_type')=='video' for s in data.get('streams',[])):raise ReelError('BBC file has no video stream.')
        if not 4<=duration<=90:raise ReelError('The complete BBC clip is outside the current 4–90 second Reel Builder limit.')
        # Decode the complete clip to catch truncation beyond readable MP4 headers.
        run([tool('ffmpeg'),'-v','error','-xerror','-i',str(temp),'-map','0:v:0','-f','null','-'])
        temp.replace(dest);return duration
    finally:
        temp.unlink(missing_ok=True)

def sign_in_browser(driver,key):
    """Use the visible BBC sign-in form; reuse an already signed-in session."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    wait=WebDriverWait(driver,35)
    def state(d):
        if any(e.is_displayed() and e.text.strip().casefold()=='log out'
               for e in d.find_elements(By.TAG_NAME,'button')):return 'signed_in'
        return next((e for e in d.find_elements(By.CSS_SELECTOR,'input[placeholder="api key"]')
                     if e.is_displayed()),None)
    field=wait.until(state)
    if field=='signed_in':return
    field.clear();field.send_keys(key)
    login=wait.until(lambda d:next((e for e in d.find_elements(By.TAG_NAME,'button')
                       if e.is_displayed() and e.text.strip().casefold()=='log in'),None))
    driver.execute_script('arguments[0].click();',login)
    wait.until(lambda d:any(e.is_displayed() and e.text.strip().casefold()=='log out'
                          for e in d.find_elements(By.TAG_NAME,'button')))

def open_portal(url=SITE+'explorer',driver=None):
    """Open a separate visible Chrome window with the locally protected key."""
    p=urlsplit(url)
    if p.scheme!='https' or p.hostname!='newshub.bbc.co.uk' or p.query or p.fragment:
        raise ReelError('Unsupported BBC portal address.')
    key=load_bbc_key()
    if not key:raise ReelError('Save your BBC key in Reel Builder > BBC NEWS HUB SETTINGS first.')
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import WebDriverException
    if driver is not None:
        try:
            if not driver.window_handles:driver=None
        except WebDriverException:driver=None
    created=driver is None
    try:
        if created:
            options=Options();options.add_argument('--window-size=1600,1100')
            options.add_experimental_option('detach',True)
            driver=webdriver.Chrome(options=options)
            driver.set_page_load_timeout(35);driver.set_script_timeout(35)
        driver.get(SITE)
        sign_in_browser(driver,key)
        driver.get(url)
        return driver
    except Exception:
        if created and driver is not None:
            try:driver.quit()
            except Exception:pass
        raise ReelError('BBC portal sign-in could not complete. Check your saved BBC key and connection, then retry.') from None

class Client:
    def __init__(self,key):
        self.key=key;self.browser=None
        self.opener=build_opener(HTTPCookieProcessor(CookieJar()))
    def close(self):
        if self.browser:
            try:self.browser.quit()
            except Exception:pass
    def browser_get(self,path,params):
        if self.browser is None:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            options=Options();options.add_argument('--headless=new');options.add_argument('--window-size=1600,1100')
            self.browser=webdriver.Chrome(options=options)
            self.browser.set_page_load_timeout(35);self.browser.set_script_timeout(35)
            self.browser.get(SITE)
            sign_in_browser(self.browser,self.key)
        url=API+path+('?' + urlencode(params) if params else '')
        result=self.browser.execute_async_script("""
            const url=arguments[0],key=arguments[1],done=arguments[arguments.length-1];
            // BBC allows wildcard origins, so cross-origin cookies must be omitted.
            fetch(url,{headers:{apikey:key,'Content-Type':'application/json'},credentials:'omit'})
            .then(async response=>{
                if(!response.ok){done({status:response.status});return;}
                const text=await response.text();
                if(text.length>12582912){done({error:'size'});return;}
                try{done({status:response.status,data:JSON.parse(text)});}catch(e){done({error:'json'});}
            }).catch(()=>done({error:'network'}));
        """,url,self.key)
        if not isinstance(result,dict) or result.get('status')!=200 or 'data' not in result:
            status=result.get('status') if isinstance(result,dict) else None
            error=result.get('error') if isinstance(result,dict) else None
            detail=('HTTP '+str(status)) if status else {
                'network':'browser network or cross-origin access error',
                'size':'response exceeds the size limit',
                'json':'response is not valid JSON',
            }.get(error,'unrecognised browser response')
            raise ReelError('BBC '+path+' request failed ('+detail+') in the signed-in session. Progress retained.')
        return result['data']
    def get(self,path,params=None):
        if self.browser is not None:return self.browser_get(path,params)
        url=API+path+('?' + urlencode(params) if params else '')
        headers={'apikey':self.key,'Content-Type':'application/json','Origin':'https://newshub.bbc.co.uk',
                 'Referer':SITE,'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'}
        try:
            with self.opener.open(Request(url,headers=headers),timeout=25) as response:
                raw=response.read(12*1024*1024+1)
            if len(raw)>12*1024*1024:raise ValueError()
            return json.loads(raw)
        except HTTPError as exc:
            status=exc.code
            if status in (401,403):return self.browser_get(path,params)
            raise ReelError('BBC '+path+' request failed (HTTP '+str(status)+'). Progress retained; retry collection.') from None
        except ReelError:raise
        except Exception as exc:
            raise ReelError('BBC '+path+' request could not complete ('+type(exc).__name__+'). Progress retained; retry collection.') from None
    def filters(self):
        # Follow the same login check as the BBC web client before reading filters.
        self.get('/login')
        data=self.get('/filters')
        filters=data.get('filter')
        if not isinstance(filters,dict):raise ReelError('BBC region filters could not be verified.')
        return filters
    def page(self,filters,lower,upper,offset):
        subjects=[]
        for kind in ('tv','online'):
            for value in filters.get(kind,[]):
                category=re.sub(r'\W+','_',value.replace('&','and')).rstrip('_').lower()
                subjects.append('category:'+category)
        params=dict(pubstatus='usable',sort='firstcreated:desc',rangeField='firstcreated',
                    start=lower.date().isoformat(),end=(upper+timedelta(days=1)).date().isoformat(),limit=50,offset=offset,
                    fields='associations,body_text,byline,description_text,firstcreated,versioncreated,embargotime,headline,id,type,pubstatus,subject')
        if subjects:params['subject']=','.join(subjects)
        # BBC's date search accepts calendar days; exact 72h is enforced below.
        return self.get('/item',params)

class Journal:
    def __init__(self,store):
        self.store=store
        with closing(store.connect()) as c:
            c.execute('CREATE TABLE IF NOT EXISTS bbc_seen (scope TEXT,id TEXT,outcome TEXT,created TEXT,PRIMARY KEY(scope,id))')
            c.execute('CREATE TABLE IF NOT EXISTS bbc_checkpoint (scope TEXT PRIMARY KEY,completed TEXT)');c.commit()
    def window(self,scope,now):
        with closing(self.store.connect()) as c:row=c.execute('SELECT completed FROM bbc_checkpoint WHERE scope=?',(scope,)).fetchone()
        last=timestamp(row[0]) if row else None
        return max(now-timedelta(hours=72),last-timedelta(minutes=10)) if last and last<=now else now-timedelta(hours=72)
    def seen(self,scope,asset_id):
        with closing(self.store.connect()) as c:return bool(c.execute('SELECT 1 FROM bbc_seen WHERE scope=? AND id=?',(scope,asset_id)).fetchone())
    def mark(self,scope,item,outcome):
        with closing(self.store.connect()) as c:
            c.execute('INSERT OR REPLACE INTO bbc_seen VALUES (?,?,?,?)',(scope,item['id'],outcome,item['firstcreated']));c.commit()
    def complete(self,scope,now):
        with closing(self.store.connect()) as c:
            c.execute('INSERT OR REPLACE INTO bbc_checkpoint VALUES (?,?)',(scope,now.isoformat()));c.commit()

def collect(progress=lambda text:None,store=None,client_factory=Client):
    store=store or Store();key=load_bbc_key()
    if not key:raise ReelError('Save your BBC key in Reel Builder > BBC NEWS HUB SETTINGS first.')
    if not _COLLECT_LOCK.acquire(blocking=False):raise ReelError('BBC collection is already running.')
    client=None
    result={'imported':[],'review':[],'duplicates':0,'failed':0,'scanned':0,'filters':{},'limit_reached':False,'partial':False,'error':''}
    try:
        now=datetime.now(timezone.utc);client=client_factory(key);journal=Journal(store)
        progress('Reading BBC region filters…');filters=client.filters();result['filters']=filters
        scope=hashlib.sha256(json.dumps(filters,sort_keys=True).encode()).hexdigest()
        lower=journal.window(scope,now);result['from']=lower.isoformat();result['to']=now.isoformat()
        result['max_age_hours']=72
        # Recover downloaded clips that were not yet admitted to Social Desk.
        for record in store.list():
            created=timestamp(record.get('published_at'))
            if record.get('bbc_asset_id') and not record.get('bbc_admitted') and created and now-timedelta(hours=72)<=created<=now and Path(record.get('video','')).is_file():
                result['imported'].append(record)
        offset=0;seen=set();deadline=time.monotonic()+180
        for page_number in range(100):
            progress(f'Fetching BBC metadata batch {page_number+1} — last 72 hours / new records…')
            page=client.page(filters,lower,now,offset)
            items=page.get('item')
            if not isinstance(items,list):raise ReelError('BBC returned an unrecognised metadata response.')
            if not items:break
            boundary=False
            for item in items:
                if time.monotonic()>deadline:
                    result['partial']=True;result['error']='Three-minute collection budget reached. Run again to resume.';break
                if not isinstance(item,dict) or not re.fullmatch(r'[A-Fa-f0-9-]{36}',str(item.get('id',''))):continue
                asset_id=item['id']
                if asset_id in seen:continue
                seen.add(asset_id);created=timestamp(item.get('firstcreated'))
                if not created or created>now:continue
                if created<lower:boundary=True;continue
                result['scanned']+=1
                url=SITE+'article/'+asset_id;reel_id=identity(url,asset_id);existing=store.get(reel_id)
                if existing or journal.seen(scope,asset_id):result['duplicates']+=1;continue
                state,places=decision(item,now)
                if state=='location_needs_review':
                    result['review'].append(dict(safe_item(item),source_url=url));journal.mark(scope,item,state);continue
                if state!='eligible':journal.mark(scope,item,state);continue
                try:
                    progress('Downloading a confirmed Lincolnshire clip…')
                    dest=(store.root/reel_id/'bbc-source.mp4').resolve();duration=download(item,dest)
                    from .integration import brand_name
                    record=dict(id=reel_id,draft_id='bbc-'+asset_id,title=item.get('headline') or asset_id,
                        body=item.get('body_text') or item.get('description_text') or item.get('headline'),source_url=url,
                        source_kind='bbc',brand=brand_name(),mode='bbc',credit='BBC',video=str(dest),source='BBC News Hub',
                        bbc_asset_id=asset_id,published_at=created.isoformat(),matched_places=list(places),full_content_verified=True,
                        video_metadata_verified=True,rights_approved=False,duration=duration,delivery_state='staged',bbc_admitted=False)
                    store.put(reel_id,record);journal.mark(scope,item,'downloaded');result['imported'].append(record)
                except Exception:result['failed']+=1
            if result['partial'] or boundary:break
            offset+=len(items)
            total=page.get('total')
            if isinstance(total,int) and offset>=total:break
            if len(seen)<offset:
                result['partial']=True;result['error']='BBC pagination repeated records. Progress retained.';break
        else:result['limit_reached']=True;result['partial']=True
        if result['failed']:result['partial']=True;result['error']='Some downloads failed or were incompatible. Successful progress is retained.'
        if not result['partial']:journal.complete(scope,now)
        result['checkpoint_advanced']=not result['partial']
        return result
    except Exception as exc:
        result['partial']=True;result['checkpoint_advanced']=False
        result['error']=str(exc) if isinstance(exc,ReelError) else 'BBC collection interrupted ('+type(exc).__name__+'). Progress retained.'
        return result
    finally:
        if client and hasattr(client,'close'):client.close()
        _COLLECT_LOCK.release()
