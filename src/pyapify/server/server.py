"""Small dependency-free threaded HTTP/1.1 server for PyAPIfy."""
from __future__ import annotations
import asyncio, socket, threading, traceback, ssl
from ..http.request import Request
from ..http.response import HTTPResponse

_REASON={100:'Continue',101:'Switching Protocols',200:'OK',201:'Created',202:'Accepted',204:'No Content',206:'Partial Content',301:'Moved Permanently',302:'Found',303:'See Other',304:'Not Modified',307:'Temporary Redirect',308:'Permanent Redirect',400:'Bad Request',401:'Unauthorized',403:'Forbidden',404:'Not Found',405:'Method Not Allowed',408:'Request Timeout',409:'Conflict',413:'Payload Too Large',415:'Unsupported Media Type',422:'Unprocessable Content',429:'Too Many Requests',500:'Internal Server Error',501:'Not Implemented',502:'Bad Gateway',503:'Service Unavailable'}

class HTTPServer:
    def __init__(self,app,host='127.0.0.1',port=8000,debug=False,certfile=None,keyfile=None,keepalive=True,timeout=30):
        self.app,self.host,self.port=app,host,port; self.debug=debug; self.certfile=certfile; self.keyfile=keyfile; self.keepalive=keepalive; self.timeout=timeout; self._server=None; self._stop=False
    def _read_request(self,conn,buffer):
        while b'\r\n\r\n' not in buffer:
            chunk=conn.recv(65536)
            if not chunk:return None,None
            buffer+=chunk
            if len(buffer)>2**20: raise ValueError('request headers too large')
        head,buffer=buffer.split(b'\r\n\r\n',1); lines=head.decode('iso-8859-1').split('\r\n'); method,target,version=lines[0].split(' ',2); headers={}
        for line in lines[1:]:
            if ':' not in line: raise ValueError('malformed header')
            k,v=line.split(':',1); headers[k.strip()]=v.strip()
        if 'transfer-encoding' in {k.lower():v for k,v in headers.items()}:
            transfer=next(v for k,v in headers.items() if k.lower()=='transfer-encoding')
            if 'chunked' not in transfer.lower(): raise ValueError('unsupported transfer encoding')
            chunks=[]
            while True:
                while b'\r\n' not in buffer:
                    part=conn.recv(65536)
                    if not part: raise ValueError('incomplete chunk')
                    buffer+=part
                line,buffer=buffer.split(b'\r\n',1); size=int(line.split(b';',1)[0],16)
                if size==0:
                    while len(buffer)<2: buffer+=conn.recv(2)
                    buffer=buffer[2:]; break
                while len(buffer)<size+2: buffer+=conn.recv(65536)
                chunks.append(buffer[:size]); buffer=buffer[size+2:]
            body=b''.join(chunks)
        else:
            length=int(next((v for k,v in headers.items() if k.lower()=='content-length'),'0') or 0)
            if length<0 or length>64*1024*1024: raise ValueError('invalid content length')
            while len(buffer)<length:
                part=conn.recv(min(65536,length-len(buffer)))
                if not part: raise ValueError('incomplete request body')
                buffer+=part
            body,buffer=buffer[:length],buffer[length:]
        return (method,target,version,headers,body),buffer
    def _handle(self,conn,addr):
        conn.settimeout(self.timeout); buffer=b''
        try:
            while not self._stop:
                parsed,buffer=self._read_request(conn,buffer)
                if not parsed: break
                method,target,version,headers,body=parsed
                req=Request(method,target,headers,body,addr,'https' if self.certfile else 'http')
                res=asyncio.run(self.app.dispatch(req)); res=res if isinstance(res,HTTPResponse) else HTTPResponse(res)
                status,h,b=res.serialize(); h=dict(h); client_close=headers.get('Connection','').lower()=='close'; close=client_close or not self.keepalive or version=='HTTP/1.0'
                h.setdefault('Content-Length',str(len(b))); h.setdefault('Connection','close' if close else 'keep-alive')
                payload=f'HTTP/1.1 {status} {_REASON.get(status,"")}\r\n'.encode()+b''.join(f'{k}: {v}\r\n'.encode() for k,v in h.items())+b'\r\n'+b
                conn.sendall(payload)
                if close: break
        except Exception:
            if self.debug: traceback.print_exc()
            try: conn.sendall(b'HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            except Exception: pass
        finally: conn.close()
    def serve_forever(self):
        self._server=socket.socket(); self._server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); self._server.bind((self.host,self.port)); self._server.listen(128); self._server.settimeout(1)
        ctx=None
        if self.certfile:
            if not self.keyfile: raise ValueError('keyfile is required when certfile is set')
            ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.load_cert_chain(self.certfile,self.keyfile)
        scheme='https' if ctx else 'http'; print(f'PyAPIfy Development Server\nRunning on {scheme}://{self.host}:{self.port}\nDebug: {"ON" if self.debug else "OFF"}\nKeep-Alive: {"ON" if self.keepalive else "OFF"}')
        try:
            asyncio.run(self.app.startup_async())
            while not self._stop:
                try: conn,addr=self._server.accept()
                except socket.timeout: continue
                if ctx: conn=ctx.wrap_socket(conn,server_side=True)
                threading.Thread(target=self._handle,args=(conn,addr),daemon=True).start()
        except KeyboardInterrupt: pass
        finally:
            self._stop=True
            try: asyncio.run(self.app.shutdown_async())
            except Exception:
                if self.debug: traceback.print_exc()
            self._server.close()

def serve(app,host='127.0.0.1',port=8000,debug=False,**kwargs):
    return HTTPServer(app,host,port,debug,kwargs.get('certfile'),kwargs.get('keyfile'),kwargs.get('keepalive',True),kwargs.get('timeout',30)).serve_forever()
