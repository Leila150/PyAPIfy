"""Synchronous WebSocket RFC 6455 connection abstraction for PyAPIfy."""
from __future__ import annotations
import json, struct

class WebSocketDisconnect(Exception): pass

class WebSocket:
    def __init__(self,sock): self.sock=sock; self.closed=False
    def _recv_exact(self,n):
        data=b''
        while len(data)<n:
            part=self.sock.recv(n-len(data))
            if not part: raise WebSocketDisconnect()
            data+=part
        return data
    def receive(self):
        while True:
            head=self._recv_exact(2); first,second=head; opcode=first&0x0f; masked=bool(second&0x80); length=second&0x7f
            if length==126:length=struct.unpack('!H',self._recv_exact(2))[0]
            elif length==127:length=struct.unpack('!Q',self._recv_exact(8))[0]
            if length>64*1024*1024: raise WebSocketDisconnect()
            mask=self._recv_exact(4) if masked else b''; payload=bytearray(self._recv_exact(length))
            if masked:
                for i in range(length): payload[i]^=mask[i%4]
            if opcode==8:self.close(); raise WebSocketDisconnect()
            if opcode==9:self._send_frame(10,bytes(payload)); continue
            if opcode==10:continue
            if opcode==1:return bytes(payload).decode('utf-8')
            if opcode==2:return bytes(payload)
            raise WebSocketDisconnect()
    def receive_json(self): return json.loads(self.receive())
    def _send_frame(self,opcode,payload=b''):
        length=len(payload); head=bytes([0x80|opcode])
        if length<126: head+=bytes([length])
        elif length<=65535: head+=bytes([126])+struct.pack('!H',length)
        else: head+=bytes([127])+struct.pack('!Q',length)
        self.sock.sendall(head+payload)
    def send(self,data):
        if isinstance(data,str): self._send_frame(1,data.encode('utf-8'))
        elif isinstance(data,bytes): self._send_frame(2,data)
        else:self._send_frame(1,json.dumps(data,separators=(',',':'),default=str).encode('utf-8'))
    def send_json(self,data): self.send(json.dumps(data,separators=(',',':'),default=str))
    def ping(self,data=b''): self._send_frame(9,data if isinstance(data,bytes) else str(data).encode())
    def pong(self,data=b''): self._send_frame(10,data if isinstance(data,bytes) else str(data).encode())
    def close(self,code=1000,reason=''):
        if self.closed:return
        self.closed=True
        payload=struct.pack('!H',code)+reason.encode('utf-8')[:123]; self._send_frame(8,payload)
