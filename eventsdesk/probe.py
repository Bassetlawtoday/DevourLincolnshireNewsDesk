from __future__ import annotations
import argparse, json, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from .base import MissingCredentialError
from .source_catalog import SourceCatalog, connector_factory


def classify_error(exc: Exception) -> str:
    if isinstance(exc, MissingCredentialError): return 'credential_blocked'
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)): return 'network_unavailable'
    if isinstance(exc, requests.HTTPError): return 'http_error'
    return 'parse_or_connector_error'


def probe_one(source, timeout: float = 10.0) -> dict:
    started=time.monotonic()
    try:
        connector=connector_factory(source)()
        if hasattr(connector,'options'):
            connector.options.timeout=timeout
        events=connector.fetch()
        return {'id':source.id,'name':source.name,'connector':source.connector,
                'status':'success' if events else 'zero_yield','events':len(events),
                'seconds':round(time.monotonic()-started,2),
                'sample_titles':[e.title for e in events[:3]]}
    except Exception as exc:
        return {'id':source.id,'name':source.name,'connector':source.connector,
                'status':classify_error(exc),'events':0,
                'seconds':round(time.monotonic()-started,2),
                'error':f'{type(exc).__name__}: {exc}'}


def main()->int:
    ap=argparse.ArgumentParser(description='Probe EventsDesk sources once, without persistence/retries')
    ap.add_argument('--batch',type=int,action='append',required=True)
    ap.add_argument('--workers',type=int,default=8)
    ap.add_argument('--timeout',type=float,default=10.0)
    ap.add_argument('--output')
    args=ap.parse_args()
    catalog=SourceCatalog.load_default()
    rows=catalog.select(batches=set(args.batch),runnable_only=True)
    results=[]
    with ThreadPoolExecutor(max_workers=max(1,args.workers)) as pool:
        futs={pool.submit(probe_one,s,args.timeout):s for s in rows}
        for fut in as_completed(futs): results.append(fut.result())
    order={s.id:i for i,s in enumerate(rows)}; results.sort(key=lambda r:order[r['id']])
    summary={}
    for r in results: summary[r['status']]=summary.get(r['status'],0)+1
    payload={'batches':sorted(set(args.batch)),'selected':len(rows),'summary':summary,'sources':results}
    text=json.dumps(payload,indent=2,ensure_ascii=False)
    if args.output: open(args.output,'w',encoding='utf-8').write(text+'\n')
    print(text); return 0
if __name__=='__main__': raise SystemExit(main())
