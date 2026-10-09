"""Optional bounded original-datagram relay for authenticated signaling rooms.
No game assets/native interfaces. Terminal membership socket; no resume/rejoin.
"""
import base64,collections,hashlib,json,re,secrets,socket,struct,threading,time
from pathlib import Path
from ws_wire import Rejected,read_frame,frame,Messages,DeadlineReader,decode_control,close_valid
PROTOCOL='bo1z-original-packet-ws-v1'
BUILD='bo1z-lan-lobby-v2'
MAGIC=0x42575331;HEADER=36;MAX_PACKET=65536;MAX_MESSAGE=HEADER+MAX_PACKET;CONTROL=8192
MAX_WS_ROOMS=4;MAX_WS_SOCKETS=16;TICKET_SECONDS=5;AUTH_SECONDS=3;IDLE_SECONDS=15
ROOM_PAYLOAD_BUDGET=1024*1024*1024;MEMBER_PAYLOAD_BUDGET=256*1024*1024
RATE_MESSAGES=512;RATE_BYTES=2*1024*1024
SOURCE_QUEUE_MESSAGES=64;SOURCE_QUEUE_BYTES=1024*1024;TOTAL_QUEUE_BYTES=4*1024*1024
ADAPTER={'protocol':PROTOCOL,'build':BUILD,'adapterSha256':hashlib.sha256((Path(__file__).parent/'ws-transport.js').read_bytes()).hexdigest(),'wireVersion':1}
def exact(v,keys):
 if type(v)is not dict or set(v)!=set(keys):raise Rejected('schema')
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False)
def epoch_bytes(value):
 if not isinstance(value,str)or not re.fullmatch('[A-Za-z0-9_-]{22}',value):raise Rejected('epoch')
 raw=base64.urlsafe_b64decode(value+'==')
 if len(raw)!=16 or base64.urlsafe_b64encode(raw).decode().rstrip('=')!=value:raise Rejected('epoch')
 return raw
def slot(member):
 identity=member.get('identity',{})
 if identity.get('port')!=3074 or not re.fullmatch(r'10\.0\.0\.[1-4]',identity.get('ip','')):raise Rejected('slot')
 return int(identity['ip'][-1])-1
class FairQueue:
 """Reserved control queue plus per-source bounded round-robin destinations."""
 def __init__(self):self.condition=threading.Condition();self.sources={i:collections.deque()for i in range(4)};self.bytes={i:0 for i in range(4)};self.controls=collections.deque();self.control_bytes=0;self.total=0;self.next=0;self.closed=False
 def put(self,op,data,source=None):
  with self.condition:
   if self.closed:raise Rejected('queue_capacity')
   if source is None:
    if len(self.controls)>=32 or self.control_bytes+len(data)>65536:raise Rejected('queue_capacity')
    self.controls.append((op,data));self.control_bytes+=len(data)
   else:
    if source not in self.sources or len(self.sources[source])>=SOURCE_QUEUE_MESSAGES or self.bytes[source]+len(data)>SOURCE_QUEUE_BYTES or self.total+len(data)>TOTAL_QUEUE_BYTES:raise Rejected('queue_capacity')
    self.sources[source].append((op,data));self.bytes[source]+=len(data)
   self.total+=len(data);self.condition.notify()
 def get(self,timeout=.25):
  with self.condition:
   if self.total==0 and not self.closed:self.condition.wait(timeout)
   if self.closed:return None
   if self.controls:
    item=self.controls.popleft();self.control_bytes-=len(item[1]);self.total-=len(item[1]);return item
   for offset in range(4):
    source=(self.next+offset)%4
    if self.sources[source]:
     item=self.sources[source].popleft();self.bytes[source]-=len(item[1]);self.total-=len(item[1]);self.next=(source+1)%4;return item
   return None
 def stop(self):
  with self.condition:
   self.closed=True;self.controls.clear();self.control_bytes=0;self.total=0
   for source in self.sources:self.sources[source].clear();self.bytes[source]=0
   self.condition.notify_all()
class Peer:
 def __init__(self,handler):self.handler=handler;self.room=None;self.member=None;self.slot=None;self.seq=0;self.closed=False;self.queue=FairQueue();self.write_lock=threading.Lock()
 def put(self,op,data,source=None):
  if self.closed:raise Rejected('queue_capacity')
  self.queue.put(op,data,source)
 def control(self,kind,**values):self.put(1,json.dumps({'type':kind,'adapter':ADAPTER,'metadata':self.room['metadata'],'transport':'websocket-relay','code':self.room['code'],'slot':self.slot,'epoch':self.member['epoch'],**values},separators=(',',':'),allow_nan=False).encode())
 def stop(self):
  if self.closed:return
  self.closed=True;self.queue.stop()
  try:self.handler.connection.shutdown(socket.SHUT_RDWR)
  except OSError:pass
 def write(self,op,data):
  with self.write_lock:
   if not self.closed:self.handler.connection.sendall(frame(op,data))
 def writer(self):
  last=time.monotonic()
  try:
   while not self.closed:
    item=self.queue.get()
    if item is None:
     if time.monotonic()-last>=10:self.write(9,b'bo1z');last=time.monotonic()
     continue
    self.write(*item);last=time.monotonic()
  except(OSError,Rejected):self.stop()
class Relay:
 def __init__(self,registry):self.registry=registry;self.tickets={};self.rejects=collections.Counter();self.route_drops=collections.Counter();self.ingress=0;self.forwarded=0;self.datagrams=0
 def check(self,room,metadata,transport,adapter):
  if room['closed']or self.registry.rooms.get(room['code'])is not room:raise Rejected('room_closed')
  if transport!='websocket-relay'or room.get('transport')!=transport:raise Rejected('transport')
  if canonical(metadata)!=canonical(room['metadata'])or adapter!=ADAPTER:raise Rejected('identity')
 def ticket(self,room,member,body,origin):
  exact(body,['metadata','transport','adapter','epoch','generation'])
  self.check(room,body['metadata'],body['transport'],body['adapter'])
  if type(body['generation'])is not int or body['generation']!=1 or body['epoch']!=member['epoch']:raise Rejected('epoch_generation')
  if not isinstance(origin,str)or not origin:raise Rejected('origin')
  if room['startEpoch']or member.get('wsAttached')or member.get('wsTerminal'):raise Rejected('no_rejoin')
  now=self.registry.clock();self.tickets={k:v for k,v in self.tickets.items()if v['expires']>now}
  if len(self.tickets)>=32:raise Rejected('ticket_capacity')
  if any(t['member']is member for t in self.tickets.values()):raise Rejected('ticket_pending')
  token=secrets.token_urlsafe(32);self.tickets[token]={'room':room,'member':member,'epoch':member['epoch'],'origin':origin,'metadata':canonical(room['metadata']),'adapter':dict(ADAPTER),'expires':now+TICKET_SECONDS}
  return {'ticket':token,'adapter':dict(ADAPTER),'transport':'websocket-relay','metadata':json.loads(canonical(room['metadata']))}
 def attach(self,value,origin,peer):
  with self.registry.condition:
   exact(value,['type','ticket','metadata','transport','adapter','code','epoch','slot','generation'])
   ticket=value['ticket']
   if not isinstance(ticket,str)or not re.fullmatch('[A-Za-z0-9_-]{43}',ticket):raise Rejected('ticket')
   t=self.tickets.pop(ticket,None)
   if not t or t['expires']<=self.registry.clock():raise Rejected('ticket')
   room,member=t['room'],t['member'];self.check(room,value['metadata'],value['transport'],value['adapter'])
   if value['type']!='authenticate'or origin!=t['origin']or value['code']!=room['code']or self.registry.rooms.get(room['code'])is not room or room['members'].get(member['id'])is not member or member['epoch']!=t['epoch']or value['epoch']!=t['epoch']or type(value['slot'])is not int or value['slot']!=slot(member)or type(value['generation'])is not int or value['generation']!=1 or room['startEpoch']or member.get('wsAttached')or member.get('wsTerminal'):raise Rejected('ticket_identity')
   peer.room=room;peer.member=member;peer.slot=slot(member);member['wsAttached']=True;member['wsPeer']=peer
   active=[self.registry.public_member(m)for m in room['members'].values()if m.get('wsPeer')and not m['wsPeer'].closed and(peer.slot==0 or slot(m)==0 or m is member)]
   peer.control('ready',members=active)
   try:
    for m in room['members'].values():
     other=m.get('wsPeer')
     if other and other is not peer and not other.closed and(peer.slot==0 or other.slot==0):other.control('peer-ready',member=self.registry.public_member(member))
   except Rejected:self.close_room(room);raise
 def ready(self,room,member):return room.get('transport')!='websocket-relay'or bool(member.get('wsPeer')and not member['wsPeer'].closed and not member.get('wsTerminal'))
 def start(self,room):
  if room.get('transport')!='websocket-relay':return
  if not all(self.ready(room,m)for m in room['members'].values()):raise Rejected('relay_not_ready')
  try:
   for m in room['members'].values():m['wsPeer'].control('started',startEpoch=1)
  except Rejected:self.close_room(room);raise Rejected('start_delivery_failed')
 def route(self,peer,data):
  with self.registry.condition:
   room,member=peer.room,peer.member
   if not room or room['closed']or self.registry.rooms.get(room['code'])is not room or room['transport']!='websocket-relay'or room['startEpoch']!=1 or room['members'].get(member['id'])is not member or member.get('wsPeer')is not peer or peer.closed or member.get('wsTerminal'):raise Rejected('sender_membership')
   if not HEADER<len(data)<=MAX_MESSAGE:raise Rejected('packet_length')
   magic,version,sock,source,target,epoch,start,seq,n=struct.unpack('!IBBBB16sIII',data[:HEADER])
   if magic!=MAGIC or version!=1 or source!=peer.slot or sock!=(1 if source==0 else 0)or epoch!=epoch_bytes(member['epoch'])or start!=room['startEpoch']:raise Rejected('packet_identity')
   if target==source or target>3 or(source!=0 and target!=0):raise Rejected('packet_slot')
   if not 1<=n<=MAX_PACKET or len(data)!=HEADER+n or seq<=peer.seq:raise Rejected('packet_sequence_length')
   if room.get('wsIngress',0)+n>ROOM_PAYLOAD_BUDGET or member.get('wsIngress',0)+n>MEMBER_PAYLOAD_BUDGET:raise Rejected('aggregate_limit')
   room['wsIngress']=room.get('wsIngress',0)+n;member['wsIngress']=member.get('wsIngress',0)+n;self.ingress+=n;peer.seq=seq
   dest=next((m for m in room['members'].values()if slot(m)==target),None);target_peer=dest.get('wsPeer')if dest else None
   if not target_peer or target_peer.closed or dest.get('wsTerminal'):self.route_drops['target_unavailable']+=1;return False
   # Only transport envelope destination epoch/socket change; original bytes untouched.
   envelope=bytearray(data);envelope[5]=1 if source==0 else 0;envelope[8:24]=epoch_bytes(dest['epoch'])
   try:target_peer.put(2,bytes(envelope),source)
   except Rejected as error:
    if str(error)!='queue_capacity':raise
    self.route_drops['destination_backpressure']+=1;return False
   self.forwarded+=n;self.datagrams+=1;return True
 def detached(self,peer):
  with self.registry.condition:
   room,member=peer.room,peer.member
   if not room or self.registry.rooms.get(room['code'])is not room or room['members'].get(member['id'])is not member or member.get('wsPeer')is not peer:return
   member['wsTerminal']=True
   if member['role']=='host':self.close_room(room);room['closed']=True;return
   for m in room['members'].values():
    other=m.get('wsPeer')
    if other and other is not peer and not other.closed and(peer.slot==0 or other.slot==0):
     try:other.control('peer-left',member=self.registry.public_member(member))
     except Rejected:other.stop()
 def remove_member(self,room,member):
  peer=member.get('wsPeer')
  if peer:peer.stop()
  member['wsTerminal']=True
  self.tickets={k:v for k,v in self.tickets.items()if v['member']is not member}
 def close_room(self,room):
  self.tickets={k:v for k,v in self.tickets.items()if v['room']is not room}
  for m in room['members'].values():self.remove_member(room,m)
 def close_all(self):
  with self.registry.condition:
   for room in self.registry.rooms.values():self.close_room(room)

def websocket(handler):
 peer=Peer(handler);acquired=False;writer=None;upgraded=False
 try:
  origin=handler.origin()
  if not origin or handler.headers.get_all('Origin')!=[origin]:raise Rejected('origin')
  if handler.path!='/coop/ws':raise Rejected('route')
  if not handler.server.ws_upgrades.acquire(blocking=False):raise Rejected('upgrade_capacity')
  acquired=True
  for name in ('Upgrade','Connection','Sec-WebSocket-Version','Sec-WebSocket-Protocol','Sec-WebSocket-Key'):
   if len(handler.headers.get_all(name,[]))!=1:raise Rejected('upgrade')
  key=handler.headers['Sec-WebSocket-Key']
  if handler.headers['Upgrade'].lower()!='websocket'or 'upgrade'not in[x.strip().lower()for x in handler.headers['Connection'].split(',')]or handler.headers['Sec-WebSocket-Version']!='13'or handler.headers['Sec-WebSocket-Protocol']!=PROTOCOL or len(base64.b64decode(key,validate=True))!=16 or handler.headers.get('Sec-WebSocket-Extensions'):raise Rejected('upgrade')
  accept=base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
  handler.send_response(101);handler.send_header('Upgrade','websocket');handler.send_header('Connection','Upgrade');handler.send_header('Sec-WebSocket-Accept',accept);handler.send_header('Sec-WebSocket-Protocol',PROTOCOL);handler.end_headers();handler.close_connection=True;upgraded=True
  fin,op,data=read_frame(DeadlineReader(handler,time.monotonic()+AUTH_SECONDS),CONTROL)
  if not fin or op!=1:raise Rejected('first_control')
  handler.server.registry.relay.attach(decode_control(data),origin,peer)
  handler.connection.settimeout(IDLE_SECONDS);writer=threading.Thread(target=peer.writer,daemon=True);writer.start();messages=Messages();rates=collections.deque()
  while not peer.closed:
   remaining=3600-(handler.server.registry.clock()-peer.room['created'])
   if remaining<=0:raise Rejected('room_expired')
   deadline=min(time.monotonic()+IDLE_SECONDS,time.monotonic()+remaining,messages.deadline or float('inf'))
   fin,op,data=read_frame(DeadlineReader(handler,deadline),MAX_MESSAGE);now=time.monotonic()
   while rates and rates[0][0]<now-1:rates.popleft()
   rates.append((now,len(data)))
   if len(rates)>RATE_MESSAGES or sum(n for _,n in rates)>RATE_BYTES:raise Rejected('socket_rate')
   if op==8:close_valid(data);peer.write(8,data);break
   if op==9:peer.put(10,data);continue
   if op==10:continue
   complete=messages.feed(fin,op,data)
   if complete is not None:handler.server.registry.relay.route(peer,complete)
 except(Rejected,ValueError,UnicodeError,EOFError,OSError):
  handler.server.registry.relay.rejects['protocol_or_socket_closed']+=1
  if not upgraded:
   try:handler.respond(403,{'error':'websocket_upgrade_refused'})
   except OSError:pass
 finally:
  peer.stop();handler.server.registry.relay.detached(peer)
  if writer:writer.join(timeout=1)
  if acquired:handler.server.ws_upgrades.release()
