"""Dependency-free threaded HTTP/1.1 development server."""
from __future__ import annotations
import asyncio, socket, threading, traceback
from ..http.request import Request
from ..http.response import HTTPResponse

class HTTPServer:
    def __init__(self,app,host='127.0.0.1',port=8000,debug=False): self.app=app; self.host=host; self.port=port; self.debug=debug; self._server=None
    def _handle(self,conn,addr):
        try:
            data=b''
            while b'\r\n\r\n' not in data:
                chunk=conn.recv(65536)
                if not chunk: return
                data+=chunk
                if len(data)>2**20: return
            head,body=data.split(b'\r\n\r\n',1); lines=head.decode('iso-8859-1').split('\r\n'); method,target,version=lines[0].split(' ',2); headers={}
            for line in lines[1:]:
                if ':' in line:
                    k,v=line.split(':',1); headers[k.strip()]=v.strip()
            length=int(headers.get('Content-Length','0') or 0)
            while len(body)<length:
                body+=conn.recv(min(65536,length-len(body)))
            req=Request(method,target,headers,body[:length],addr)
            res=asyncio.run(self.app.dispatch(req))
            if not isinstance(res,HTTPResponse): res=HTTPResponse(res)
            status,h,b=res.serialize(); reason={200:'OK',201:'Created',204:'No Content',301:'Moved Permanently',302:'Found',400:'Bad Request',401:'Unauthorized',403:'Forbidden',404:'Not Found',405:'Method Not Allowed',413:'Payload Too Large',422:'Unprocessable Content',429:'Too Many Requests',500:'Internal Server Error',503:'Service Unavailable'}.get(status,'')
            h.setdefault('Connection','close'); raw=f'HTTP/1.1 {status} {reason}\r\n'.encode()+b''.join(f'{k}: {v}\r\n'.encode() for k,v in h.items())+b'\r\n'+b
            conn.sendall(raw)
        except Exception:
            if self.debug: traceback.print_exc()
        finally: conn.close()
    def serve_forever(self):
        self._server=socket.socket(socket.AF_INET,socket.SOCK_STREAM); self._server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); self._server.bind((self.host,self.port)); self._server.listen(128)
        print(f'PyAPIfy Development Server\nRunning on http://{self.host}:{self.port}\nDebug: {"ON" if self.debug else "OFF"}')
        try:
            while True:
                conn,addr=self._server.accept(); threading.Thread(target=self._handle,args=(conn,addr),daemon=True).start()
        except KeyboardInterrupt: pass
        finally:self._server.close()

def serve(app,host='127.0.0.1',port=8000,debug=False,**kwargs): return HTTPServer(app,host,port,debug).serve_forever()
