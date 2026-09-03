"""Server-Sent Events response helpers."""
import json
from ..http.response import HTTPResponse

def encode_event(data=None,event=None,id=None,retry=None):
    lines=[]
    if event is not None: lines.append(f'event: {event}')
    if id is not None: lines.append(f'id: {id}')
    if retry is not None: lines.append(f'retry: {retry}')
    if data is not None:
        text=json.dumps(data,separators=(',',':')) if not isinstance(data,str) else data
        lines.extend('data: '+x for x in text.splitlines() or [''])
    return ('\n'.join(lines)+'\n\n').encode()

def sse(data,*,event=None,id=None,retry=None,status=200,headers=None):
    h={'Content-Type':'text/event-stream; charset=utf-8','Cache-Control':'no-cache','Connection':'keep-alive'}; h.update(headers or {})
    return HTTPResponse(encode_event(data,event=event,id=id,retry=retry),status,headers=h)
