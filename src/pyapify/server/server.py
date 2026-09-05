"""Dependency-free threaded HTTP/1.1 and WebSocket transport for PyAPIfy."""
from __future__ import annotations
import asyncio, socket, threading, traceback, ssl, base64, hashlib, inspect, os, subprocess, tempfile, shutil
from collections.abc import Iterable
from pathlib import Path
from ..http.request import Request
from ..http.response import HTTPResponse
from ..websocket.websocket import WebSocket, WebSocketDisconnect

_REASON={100:'Continue',101:'Switching Protocols',200:'OK',201:'Created',202:'Accepted',204:'No Content',206:'Partial Content',301:'Moved Permanently',302:'Found',303:'See Other',304:'Not Modified',307:'Temporary Redirect',308:'Permanent Redirect',400:'Bad Request',401:'Unauthorized',403:'Forbidden',404:'Not Found',405:'Method Not Allowed',408:'Request Timeout',409:'Conflict',413:'Payload Too Large',415:'Unsupported Media Type',422:'Unprocessable Content',426:'Upgrade Required',429:'Too Many Requests',500:'Internal Server Error',501:'Not Implemented',502:'Bad Gateway',503:'Service Unavailable'}


def _local_ip():
    """Best-effort LAN address discovery without sending application traffic."""
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    try:
        s.connect(('192.0.2.1',80))
        return s.getsockname()[0]
    except OSError:
        return '127.0.0.1'
    finally:
        s.close()


def _dev_certificate():
    """Create/reuse a local self-signed certificate for the development server."""
    root=Path.home()/'.pyapify'/'certs'
    root.mkdir(parents=True,exist_ok=True)
    cert,key=root/'dev-cert.pem',root/'dev-key.pem'
    if cert.exists() and key.exists(): return str(cert),str(key)
    openssl=shutil.which('openssl')
    if not openssl:
        raise RuntimeError('Automatic HTTPS requires OpenSSL. Install OpenSSL or pass certfile= and keyfile=.')
    tmpdir=Path(tempfile.mkdtemp(prefix='pyapify-cert-',dir=str(root)))
    tmpcert,tmpkey=tmpdir/'cert.pem',tmpdir/'key.pem'
    try:
        cmd=[openssl,'req','-x509','-newkey','rsa:2048','-sha256','-nodes','-days','825','-keyout',str(tmpkey),'-out',str(tmpcert),'-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost,IP:127.0.0.1']
        result=subprocess.run(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,check=False,text=True)
        if result.returncode!=0:
            raise RuntimeError('OpenSSL could not create the development certificate: '+result.stderr.strip())
        os.replace(tmpcert,cert);os.replace(tmpkey,key)
        try: os.chmod(key,0o600)
        except OSError: pass
        return str(cert),str(key)
    finally:
        shutil.rmtree(tmpdir,ignore_errors=True)


class HTTPServer:
    def __init__(self,app,host='0.0.0.0',port=8080,debug=False,certfile=None,keyfile=None,https=True,keepalive=True,timeout=30,max_header_size=1024*1024,max_request_size=64*1024*1024):
        self.app,self.host,self.port=app,host,port; self.debug=debug; self.certfile=certfile; self.keyfile=keyfile; self.https=https; self.keepalive=keepalive; self.timeout=timeout; self.max_header_size=max_header_size; self.max_request_size=max_request_size; self._server=None; self._stop=False
        if self.https:
            if bool(self.certfile)!=bool(self.keyfile): raise ValueError('certfile and keyfile must be provided together')
            if not self.certfile:self.certfile,self.keyfile=_dev_certificate()
    def _read_request(self,conn,buffer):
        while b'\r\n\r\n' not in buffer:
            chunk=conn.recv(65536)
            if not chunk:return None,None
            buffer+=chunk
            if len(buffer)>self.max_header_size:raise ValueError('request headers too large')
        head,buffer=buffer.split(b'\r\n\r\n',1); lines=head.decode('iso-8859-1').split('\r\n')
        try:method,target,version=lines[0].split(' ',2)
        except ValueError:raise ValueError('malformed request line')
        headers={}
        for line in lines[1:]:
            if ':' not in line:raise ValueError('malformed header')
            k,v=line.split(':',1);headers[k.strip()]=v.strip()
        lower={k.lower():v for k,v in headers.items()}
        if 'transfer-encoding' in lower:
            if lower['transfer-encoding'].lower().strip()!='chunked':raise ValueError('unsupported transfer encoding')
            chunks=[];total=0
            while True:
                while b'\r\n' not in buffer:
                    part=conn.recv(65536)
                    if not part:raise ValueError('incomplete chunk')
                    buffer+=part
                line,buffer=buffer.split(b'\r\n',1)
                try:size=int(line.split(b';',1)[0],16)
                except ValueError:raise ValueError('invalid chunk size')
                if size<0 or total+size>self.max_request_size:raise ValueError('request body too large')
                if size==0:
                    while b'\r\n\r\n' not in buffer and buffer!=b'\r\n':
                        part=conn.recv(65536)
                        if not part:break
                        buffer+=part
                    if b'\r\n\r\n' in buffer:buffer=buffer.split(b'\r\n\r\n',1)[1]
                    elif buffer.startswith(b'\r\n'):buffer=buffer[2:]
                    break
                while len(buffer)<size+2:
                    part=conn.recv(65536)
                    if not part:raise ValueError('incomplete chunk data')
                    buffer+=part
                if buffer[size:size+2]!=b'\r\n':raise ValueError('invalid chunk terminator')
                chunks.append(buffer[:size]);buffer=buffer[size+2:];total+=size
            body=b''.join(chunks)
        else:
            try:length=int(lower.get('content-length','0') or 0)
            except ValueError:raise ValueError('invalid content length')
            if length<0 or length>self.max_request_size:raise ValueError('request body too large')
            while len(buffer)<length:
                part=conn.recv(min(65536,length-len(buffer)))
                if not part:raise ValueError('incomplete request body')
                buffer+=part
            body,buffer=buffer[:length],buffer[length:]
        return (method,target,version,headers,body),buffer
    @staticmethod
    def _write_headers(conn,status,headers):conn.sendall(f'HTTP/1.1 {status} {_REASON.get(status,"")}\r\n'.encode()+b''.join(f'{k}: {v}\r\n'.encode() for k,v in headers.items())+b'\r\n')
    def _send_response(self,conn,res,request_headers,version):
        is_stream=isinstance(res.data,Iterable) and not isinstance(res.data,(bytes,str,dict,list,tuple,set)); close=request_headers.get('Connection','').lower()=='close' or not self.keepalive or version=='HTTP/1.0'
        if is_stream:
            headers=res._headers(None);headers.pop('Content-Length',None);headers['Transfer-Encoding']='chunked';headers['Connection']='close' if close else 'keep-alive';self._write_headers(conn,res.status,headers)
            for chunk in res._body_iter():
                if chunk:conn.sendall(f'{len(chunk):X}\r\n'.encode()+chunk+b'\r\n')
            conn.sendall(b'0\r\n\r\n');return close
        status,headers,body=res.serialize();headers.setdefault('Content-Length',str(len(body)));headers['Connection']='close' if close else 'keep-alive';self._write_headers(conn,status,headers);conn.sendall(body);return close
    def _websocket(self,conn,addr,req,route,params,headers):
        if headers.get('Upgrade','').lower()!='websocket' or 'upgrade' not in headers.get('Connection','').lower():return False
        key=headers.get('Sec-WebSocket-Key'); version=headers.get('Sec-WebSocket-Version','13')
        if not key or version!='13': self._write_headers(conn,400,{'Content-Length':'0','Connection':'close'});return True
        accept=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
        self._write_headers(conn,101,{'Upgrade':'websocket','Connection':'Upgrade','Sec-WebSocket-Accept':accept})
        ws=WebSocket(conn);req.websocket=ws
        async def run():
            if not await self.app._auth_async(route.auth,req):ws.close(1008,'Authentication required');return
            try: await self.app._call(route.endpoint,req,params,websocket=ws)
            except WebSocketDisconnect:pass
            except Exception:
                if self.debug:traceback.print_exc()
                try:ws.close(1011,'Internal server error')
                except Exception:pass
        asyncio.run(run());return True
    def _handle(self,conn,addr):
        conn.settimeout(self.timeout);buffer=b''
        try:
            while not self._stop:
                parsed,buffer=self._read_request(conn,buffer)
                if not parsed:break
                method,target,version,headers,body=parsed;req=Request(method,target,headers,body,addr,'https' if self.https else 'http')
                route,params=self.app.router.match(req.path,req.method)
                if route is not None and route.websocket and self._websocket(conn,addr,req,route,params,headers):break
                try:res=asyncio.run(self.app.dispatch(req));res=res if isinstance(res,HTTPResponse) else HTTPResponse(res)
                except Exception:
                    if self.debug:traceback.print_exc()
                    res=HTTPResponse({'detail':'Internal server error'},500)
                if self._send_response(conn,res,headers,version):break
        except (socket.timeout,ConnectionError,BrokenPipeError):pass
        except Exception:
            if self.debug:traceback.print_exc()
            try:self._write_headers(conn,400,{'Content-Length':'0','Connection':'close'})
            except Exception:pass
        finally:conn.close()
    def serve_forever(self):
        self._server=socket.socket();self._server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);self._server.bind((self.host,self.port));self._server.listen(128);self._server.settimeout(1);ctx=None
        if self.https:
            ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.minimum_version=ssl.TLSVersion.TLSv1_2;ctx.load_cert_chain(self.certfile,self.keyfile)
        scheme='https' if ctx else 'http';lan=_local_ip();
        print(f'PyAPIfy Development Server\nRunning on {scheme}://127.0.0.1:{self.port}\nNetwork: {scheme}://{lan}:{self.port}\nDebug: {"ON" if self.debug else "OFF"}\nKeep-Alive: {"ON" if self.keepalive else "OFF"}')
        if self.https and not self.certfile.endswith('dev-cert.pem'): print('TLS: custom certificate')
        elif self.https: print('TLS: automatic self-signed development certificate (browser warning is expected)')
        try:
            asyncio.run(self.app.startup_async())
            while not self._stop:
                try:conn,addr=self._server.accept()
                except socket.timeout:continue
                if ctx:
                    try:conn=ctx.wrap_socket(conn,server_side=True)
                    except ssl.SSLError:conn.close();continue
                threading.Thread(target=self._handle,args=(conn,addr),daemon=True).start()
        except KeyboardInterrupt:pass
        finally:
            self._stop=True
            try:asyncio.run(self.app.shutdown_async())
            except Exception:
                if self.debug:traceback.print_exc()
            try:self._server.close()
            except Exception:pass

def serve(app,host='0.0.0.0',port=8080,debug=False,**kwargs):
    return HTTPServer(app,host,port,debug,kwargs.get('certfile'),kwargs.get('keyfile'),kwargs.get('https',True),kwargs.get('keepalive',True),kwargs.get('timeout',30),kwargs.get('max_header_size',1024*1024),kwargs.get('max_request_size',64*1024*1024)).serve_forever()
