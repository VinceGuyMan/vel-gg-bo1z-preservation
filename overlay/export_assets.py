"""Private Node routing snapshot from verified captured representations; archive read-only."""
import hashlib,json,mimetypes,os,re
from pathlib import Path,PurePosixPath
from types import SimpleNamespace
from urllib.parse import urlsplit
import build_metadata
from refresh_checksums import package_files,file_hash
from serve_coop import HERE,BUILD,overlays

MAPS={'five','kino','riese','nacht','verruckt','shinonuma','ascension','cotd','shangrila','moon'}
def read_index(root):
    entries={}
    for line in (root/'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
        digest,name=line.split('  ',1);rel=PurePosixPath(name)
        if not re.fullmatch('[0-9a-f]{64}',digest) or name in entries or rel.is_absolute() or '..' in rel.parts or '\\' in name:
            raise ValueError('Invalid capture checksum index')
        entries[name]=digest
    return entries

def checked_path(root,name):
    if not isinstance(name,str) or not name or '\\' in name or ':' in name:
        raise ValueError('Invalid capture relative path')
    rel=PurePosixPath(name)
    if rel.is_absolute() or any(part in ('.','..','') for part in name.split('/')) or name.startswith('/'):
        raise ValueError('Invalid capture relative path')
    p=root.joinpath(*rel.parts)
    if not p.is_relative_to(root):raise ValueError('Capture path outside root')
    current=p
    while current!=root:
        if current.is_symlink():raise ValueError('Symlink representation refused')
        if current.parent==current:raise ValueError('Capture ancestor walk escaped root')
        current=current.parent
    if not p.resolve().is_relative_to(root) or not p.is_file():raise ValueError('Capture representation missing/outside root')
    return p

def verify_package(root):
    expected=read_index(HERE)
    actual={name:p for p,name in package_files()}
    if set(actual)!=set(expected) or any(file_hash(actual[n])!=h for n,h in expected.items()):
        raise ValueError('Package checksums differ; verify complete package before launch')
    stored=json.loads((HERE/'build-metadata.json').read_text())
    opts=SimpleNamespace(archive=root,patch_manifest=HERE/'patch-manifest.json',patched_wasm=HERE/'KisakBlack-web.wasm',map=stored['mapSlug'],mode=stored['mode'],verify_content=False,shell=[],protocol_version=stored['protocolVersion'],bridge_abi_version=stored['bridgeAbiVersion'],patch_schema_revision=stored['patchSchemaRevision'],max_players=stored['maxPlayers'])
    derived=build_metadata.generate(opts)
    if stored['peerGuardFields']!=derived['peerGuardFields'] or any(stored[k]!=derived[k] for k in stored['peerGuardFields']) or stored['compatibilitySha256']!=derived['compatibilitySha256']:
        raise ValueError('Package compatibility metadata is stale')

def mime(path,route):
    if route.rstrip('/').rsplit('/',1)[-1] in MAPS:return 'text/html; charset=utf-8'
    if path.suffix in ('.js','.mjs'):return 'text/javascript; charset=utf-8'
    return mimetypes.guess_type(str(path))[0] or 'application/octet-stream'

def export_snapshot(archive,snapshot,launch_id):
    root=Path(archive).resolve();snapshot=Path(snapshot).resolve()
    if snapshot.is_relative_to(root) or snapshot.is_relative_to(HERE):raise ValueError('Snapshot must be separate from archive/package')
    if not snapshot.is_dir() or any(snapshot.iterdir()):raise ValueError('Snapshot must be an empty owned directory')
    os.chmod(snapshot,0o700)
    verify_package(root)
    index=read_index(root)
    jsonl='metadata/responses.jsonl';source=checked_path(root,jsonl)
    if index.get(jsonl)!=file_hash(source):raise ValueError('Capture response metadata digest differs')
    records={}
    for line in source.read_text(encoding='utf-8').splitlines():
        r=json.loads(line);name=r['path']
        if name not in index:raise ValueError('Response path missing from capture index')
        p=checked_path(root,name)
        if r.get('status')!=200 or index.get(name)!=r['sha256'] or p.stat().st_size!=r['bytes'] or r.get('content_encoding','') not in ('','br','gzip'):
            raise ValueError('Capture response representation does not match index')
        records[r['url']]=r
    encodings={r['path']:r.get('content_encoding','') for r in records.values()}
    captured_paths={urlsplit(u).path:r for u,r in records.items() if urlsplit(u).hostname=='vel.gg'}
    def entry(name,route,encoding=''):
        p=checked_path(root,name)
        return {'path':str(p),'bytes':p.stat().st_size,'sha256':index[name],'mime':mime(p,route),'encoding':encoding}
    files={}
    for name in sorted(index):
        if name.startswith('site/bo1z/'):
            route='/'+name[len('site/'):];files[route]=entry(name,route)
    for route,r in captured_paths.items():files[route]=entry(r['path'],route,r.get('content_encoding',''))
    parts={}
    for name in sorted(index):
        if not name.startswith('site/_transport/'):continue
        rel=PurePosixPath(name).parts;slug=rel[2];part=rel[-1];asset='/'.join(rel[3:-1])
        if slug not in MAPS or not part.isascii() or not part.isdigit() or not asset.endswith('.br'):
            raise ValueError('Unexpected captured transport route')
        route='/bo1z/'+('pack/' if slug=='five' else slug+'/pack/')+asset[:-3]
        parts.setdefault(route,{})[part]=entry(name,route,encodings.get(name,''))
        if slug=='five':parts.setdefault('/bo1z/five/pack/'+asset[:-3],{})[part]=parts[route][part]
    # Exact existing generated overlays, with the packaged WASM represented by a file.
    resources=overlays(root)
    wasm_route='/bo1z/artifacts/KisakBlack-web-coop.wasm'
    resources.pop(wasm_route)
    snapshot_entries={}
    def save(route,mime_type,data):
        digest=hashlib.sha256(data).hexdigest();p=snapshot/(digest+'.bin')
        if not p.exists():
            with p.open('xb') as f:f.write(data)
            os.chmod(p,0o600)
        return {'path':str(p),'bytes':len(data),'sha256':digest,'mime':mime_type,'encoding':''}
    for route,(mime_type,data) in resources.items():snapshot_entries[route]=save(route,mime_type,data)
    wasm=HERE/'KisakBlack-web.wasm'
    snapshot_entries[wasm_route]={'path':str(wasm),'bytes':wasm.stat().st_size,'sha256':file_hash(wasm),'mime':'application/wasm','encoding':''}
    health=json.dumps({'ok':True,'service':'bo1z-coop-assets','launchId':launch_id,'build':BUILD,'assetBackend':'node-http-stream-v1'}).encode()
    snapshot_entries['/coop/health']=save('/coop/health','application/json',health)
    page=(root/'site/bo1z/five.html').read_text(encoding='utf-8').replace('</head>','<link rel="stylesheet" href="coop/lobby.css"></head>').replace('<script type="module" src="play.js">','<script type="module" src="coop/lobby.js"></script><script type="module" src="coop-play.js">')
    coop=save('/bo1z/five','text/html; charset=utf-8',page.encode())
    manifest={'schemaVersion':1,'build':BUILD,'launchId':launch_id,'roots':[str(root),str(snapshot),str(HERE.resolve())],'files':files,'parts':parts,'overlays':snapshot_entries,'coopPages':{'/bo1z/five':coop,'/bo1z/five.html':coop},'archiveChecksumIndexSha256':file_hash(root/'SHA256SUMS.txt')}
    target=snapshot/'routes.json'
    with target.open('x',encoding='utf-8') as f:json.dump(manifest,f,separators=(',',':'))
    os.chmod(target,0o600)
    return target
