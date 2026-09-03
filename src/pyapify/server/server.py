"""Dependency-free threaded HTTP/1.1 transport for PyAPIfy."""
from __future__ import annotations
import asyncio, socket, threading, traceback, ssl
from collections.abc import Iterable
from ..http.request import Request
from ..http.response import HTTPResponse

_REASON={100:'Continue',101:'Switching Protocols',200:'OK',201:'Created',202:'Accepted',204:'No Content',206:'Partial Content',301:'Moved Permanently',302:'Found',303:'See Other',304:'Not Modified',307:'Temporary Redirect',308:'Permanent Redirect',400:'Bad Request',401:'Unauthorized',403:'Forbidden',404:'Not Found',405:'Method Not Allowed',408:'Request Timeout',409:'Conflict',413:'Payload Too Large',415:'Unsupported Media Type',422:'Unprocessable Content',429:'Too Many Requests',500:'Internal Server Error',501:'Not Implemented',502:'Bad Gateway',503:'Service Unavailable'}

class HTTPServer:
    def __init__(self,app,host='127.0.0.1',port=8000,debug=False,certfile=None,keyfile=None,keepalive=True,timeout=30,max_header_size=1024*1024,max_request_size=64*1024*1024):
        self.app,self.host,self.port=app,host,port; self.debug=debug; self.certfile=certfile; self.keyfile=keyfile; self.keepalive=keepalive; self.timeout=timeout
        self.max_header_size=max_header_size; self.max_request_size=max_request_size; self._server=None; self._stop=False
    def _read_request(self,conn,buffer):
        while b'\r\n\r\n' not in buffer:
            chunk=conn.recv(65536)
            if not chunk:return None,None
            buffer+=chunk
            if len(buffer)>self.max_header_size: raise ValueError('request headers too large')
        head,buffer=buffer.split(b'\r\n\r\n',1); lines=head.decode('iso-8859-1').split('\r\n');
        try: method,target,version=lines[0].split(' ',2)
        except ValueError: raise ValueError('malformed request line')
        headers={}
        for line in lines[1:]:
            if ':' not in line: raise ValueError('malformed header')
            k,v=line.split(':',1); headers[k.strip()]=v.strip()
        lower={k.lower():v for k,v in headers.items()}
        if 'transfer-encoding' in lower:
            if lower['transfer-encoding'].lower().strip()!='chunked': raise ValueError('unsupported transfer encoding')
            chunks=[]; total=0
            while True:
                while b'\r\n' not in buffer:
                    part=conn.recv(65536)
                    if not part: raise ValueError('incomplete chunk')
                    buffer+=part
                line,buffer=buffer.split(b'\r\n',1)
                try:size=int(line.split(b';',1)[0],16)
                except ValueError: raise ValueError('invalid chunk size')
                if size<0 or total+size>self.max_request_size: raise ValueError('request body too large')
                if size==0:
                    # Consume trailers up to the terminating CRLF.
                    while b'\r\n\r\n' not in buffer:
                        part=conn.recv(65536)
                        if not part: break
                        buffer+=part
                    if b'\r\n\r\n' in buffer: buffer=buffer.split(b'\r\n\r\n',1)[1]
                    else:
                        if buffer.startswith(b'\r\n'): buffer=buffer[2:]
                    break
                while len(buffer)<size+2:
                    part=conn.recv(65536)
                    if not part: raise ValueError('incomplete chunk data')
                    buffer+=part
                if buffer[size:size+2]!=b'\r\n': raise ValueError('invalid chunk terminator')
                chunks.append(buffer[:size]); buffer=buffer[size+2:]; total+=size
            body=b''.join(chunks)
        else:
            try:length=int(lower.get('content-length','0') or 0)
            except ValueError: raise ValueError('invalid content length')
            if length<0 or length>self.max_request_size: raise ValueError('request body too large')
            while len(buffer)<length:
                part=conn.recv(min(65536,length-len(buffer)))
                if not part: raise ValueError('incomplete request body')
                buffer+=part
            body,buffer=buffer[:length],buffer[length:]
        return (method,target,version,headers,body),buffer
    @staticmethod
    def _write_headers(conn,status,headers):
        conn.sendall(f'HTTP/1.1 {status} {_REASON.get(status,"")}\r\n'.encode()+b''.join(f'{k}: {v}\r\n'.encode() for k,v in headers.items())+b'\r\n')
    def _send_response(self,conn,res,request_headers,version):
        status=res.status
        # Iterable responses are streamed with HTTP/1.1 chunked transfer encoding.
        is_stream=isinstance(res.data,Iterable) and not isinstance(res.data,(bytes,str,dict,list,tuple,set))
        client_close=request_headers.get('Connection','').lower()=='close'
        close=client_close or not self.keepalive or version=='HTTP/1.0'
        if is_stream:
            headers=res._headers(None); headers.pop('Content-Length',None); headers['Transfer-Encoding']='chunked'; headers['Connection']='close' if close else 'keep-alive'
            self._write_headers(conn,status,headers)
            for chunk in res._body_iter():
                if chunk: conn.sendall(f'{len(chunk):X}\r\n'.encode()+chunk+b'\r\n')
            conn.sendall(b'0\r\n\r\n'); return close
        status,headers,body=res.serialize(); headers=dict(headers); headers.setdefault('Content-Length',str(len(body))); headers['Connection']='close' if close else 'keep-alive'
        self._write_headers(conn,status,headers); conn.sendall(body); return close
    def _handle(self,conn,addr):
        conn.settimeout(self.timeout); buffer=b''
        try:
            while not self._stop:
                parsed,buffer=self._read_request(conn,buffer)
                if not parsed: break
                method,target,version,headers,body=parsed
                req=Request(method,target,headers,body,addr,'https' if self.certfile else 'http')
                try:
                    res=asyncio.run(self.app.dispatch(req)); res=res if isinstance(res,HTTPResponse) else HTTPResponse(res)
                except Exception:
                    if self.debug: traceback.print_exc()
                    res=HTTPResponse({'detail':'Internal server error'},500)
                if self._send_response(conn,res,headers,version): break
        except (socket.timeout,ConnectionError,BrokenPipeError):
            pass
        except Exception:
            if self.debug: traceback.print_exc()
            try: self._write_headers(conn,400,{'Content-Length':'0','Connection':'close'})
            except Exception: pass
        finally: conn.close()
    def serve_forever(self):
        self._server=socket.socket(); self._server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); self._server.bind((self.host,self.port)); self._server.listen(128); self._server.settimeout(1)
        ctx=None
        if self.certfile:
            if not self.keyfile: raise ValueError('keyfile is required when certfile is set')
            ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); ctx.minimum_version=ssl.TLSVersion.TLSv1_2; ctx.load_cert_chain(self.certfile,self.keyfile)
        scheme='https' if ctx else 'http'; print(f'PyAPIfy Development Server\nRunning on {scheme}://{self.host}:{self.port}\nDebug: {"ON" if self.debug else "OFF"}\nKeep-Alive: {"ON" if self.keepalive else "OFF"}')
        try:
            asyncio.run(self.app.startup_async())
            while not self._stop:
                try: conn,addr=self._server.accept()
                except socket.timeout: continue
                if ctx:
                    try: conn=ctx.wrap_socket(conn,server_side=True)
                    except ssl.SSLError:
                        conn.close(); continue
                threading.Thread(target=self._handle,args=(conn,addr),daemon=True).start()
        except KeyboardInterrupt: pass
        finally:
            self._stop=True
            try: asyncio.run(self.app.shutdown_async())
            except Exception:
                if self.debug: traceback.print_exc()
            try:self._server.close()
            except Exception:pass

def serve(app,host='127.0.0.1',port=8000,debug=False,**kwargs):
    return HTTPServer(app,host,port,debug,kwargs.get('certfile'),kwargs.get('keyfile'),kwargs.get('keepalive',True),kwargs.get('timeout',30),kwargs.get('max_header_size',1024*1024),kwargs.get('max_request_size',64*1024*1024)).serve_forever()
