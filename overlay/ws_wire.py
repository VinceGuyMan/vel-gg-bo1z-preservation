"""Reviewed RFC6455 framing/assembly from frozen local datagram labv3."""
import json,struct,time
MAX_PACKET=65536
HEADER=36
MAX_MESSAGE=HEADER+MAX_PACKET
class Rejected(Exception):pass
def decode_control(data):return json.loads(data.decode("utf-8",errors="strict"))
def read_exact(stream,size):
    out=bytearray()
    while len(out)<size:
        part=stream.read(size-len(out))
        if not part: raise EOFError()
        out.extend(part)
    return bytes(out)
def frame(opcode,data=b''):
    n=len(data)
    head=bytes([0x80|opcode,n]) if n<126 else bytes([0x80|opcode,126])+struct.pack('!H',n) if n<=65535 else bytes([0x80|opcode,127])+struct.pack('!Q',n)
    return head+data
def read_frame(stream,limit):
    a,b=read_exact(stream,2)
    fin=bool(a&128); op=a&15
    if a&112 or not b&128 or op not in (0,1,2,8,9,10): raise Rejected('framing')
    n=b&127
    if n==126:
        n=struct.unpack('!H',read_exact(stream,2))[0]
        if n<126: raise Rejected('noncanonical')
    elif n==127:
        n=struct.unpack('!Q',read_exact(stream,8))[0]
        if n<=65535 or n>>63: raise Rejected('noncanonical')
    if n>limit or op>=8 and (not fin or n>125): raise Rejected('message_limit')
    mask=read_exact(stream,4); raw=read_exact(stream,n)
    return fin,op,bytes(v^mask[i%4] for i,v in enumerate(raw))
def close_valid(data):
    if len(data)==1: raise Rejected('close_payload')
    if data:
        code=struct.unpack('!H',data[:2])[0]
        if code not in (1000,1001,1002,1003,1007,1008,1009,1010,1011,1012,1013,1014) and not 3000<=code<5000: raise Rejected('close_code')
        data[2:].decode('utf-8',errors='strict')

class DeadlineReader:
    def __init__(self,handler,deadline):self.handler=handler;self.deadline=deadline
    def read(self,n):
        remaining=self.deadline-time.monotonic()
        if remaining<=0:raise Rejected('read_deadline')
        self.handler.connection.settimeout(remaining)
        return self.handler.rfile.read1(n)

class Messages:
    def __init__(self,clock=time.monotonic):self.clock=clock;self.data=bytearray();self.active=False;self.deadline=None
    def feed(self,fin,op,data):
        now=self.clock()
        if self.deadline is not None and now>self.deadline:raise Rejected('fragment_limit')
        if op==2:
            if self.active:raise Rejected('fragment_order')
            if fin:return data
            self.active=True;self.deadline=now+3
        elif op==0:
            if not self.active:raise Rejected('fragment_order')
        else:raise Rejected('unexpected_text')
        self.data.extend(data)
        if len(self.data)>MAX_MESSAGE:raise Rejected('fragment_limit')
        if fin:
            out=bytes(self.data);self.data.clear();self.active=False;self.deadline=None;return out
        return None

