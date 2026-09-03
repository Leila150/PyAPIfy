"""PyAPIfy command line interface."""
from __future__ import annotations
import argparse, importlib.util, json, pathlib, subprocess, sys

def load(path):
    path=str(path); spec=importlib.util.spec_from_file_location('pyapify_app',path)
    if spec is None or spec.loader is None: raise RuntimeError(f'Cannot load {path}')
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    for value in vars(mod).values():
        if hasattr(value,'router') and hasattr(value,'dispatch'): return value
    raise RuntimeError('No PyAPIfy application object found in '+path)

def _app_arg(parser, required=False): parser.add_argument('app',nargs=None if required else '?',default='app.py',help='application Python file (default: app.py)')

def main(argv=None):
    p=argparse.ArgumentParser(prog='pyapify',description='The PyAPIfy API framework CLI'); sub=p.add_subparsers(dest='command')
    for name in ('dev','run','routes','check','docs','openapi','inspect','benchmark','test','generate','config','plugins','validate'):
        q=sub.add_parser(name); _app_arg(q)
        if name=='generate': q.add_argument('kind',choices=('openapi','client'),default='openapi',nargs='?'); q.add_argument('--output','-o')
    q=sub.add_parser('create'); q.add_argument('name',nargs='?',default='myapi')
    q=sub.add_parser('cert'); q.add_argument('--output','-o',default='certs'); q.add_argument('--hostname',default='localhost')
    sub.add_parser('version'); sub.add_parser('doctor'); q=sub.add_parser('export'); _app_arg(q); q.add_argument('--output','-o')
    q=sub.add_parser('shell'); _app_arg(q)
    a=p.parse_args(argv)
    if a.command is None:p.print_help();return 0
    if a.command=='version': from pyapify import __version__; print(__version__); return 0
    if a.command=='doctor':
        import pyapify
        print(f'Python: {sys.version.split()[0]}'); print(f'PyAPIfy: {pyapify.__version__}'); print(f'Executable: {sys.executable}'); print('Environment: OK'); return 0
    if a.command=='create': return create_project(a.name)
    if a.command=='cert': return create_certificates(a.output,a.hostname)
    if a.command in {'dev','run'}: return _serve(a.app,a.command=='dev')
    if a.command=='test': return subprocess.call([sys.executable,'-m','pytest'])
    app=load(a.app)
    if a.command=='routes':
        print('METHOD   PATH                         AUTH')
        for r in app.router.routes: print(f'{",".join(sorted(r.methods)):8} {r.path:28} {"yes" if r.auth else "-"}')
    elif a.command in {'openapi','docs'}: print(json.dumps(app.openapi(),indent=2))
    elif a.command=='check': print(f'OK: {len(app.router.routes)} routes registered')
    elif a.command=='validate':
        errors=[]
        for r in app.router.routes:
            if not r.path.startswith('/'): errors.append(f'{r.path}: path must start with /')
        print('VALID' if not errors else '\n'.join(errors)); return 0 if not errors else 1
    elif a.command=='inspect': print(f'Application: {app.title} {app.version}\nRoutes: {len(app.router.routes)}\nMiddleware: {len(app._middleware)}\nPlugins: {len(app.plugins)}')
    elif a.command=='benchmark': print('Use `pyapify benchmark app.py` with an external load generator or the native test client for deterministic in-process tests.')
    elif a.command=='generate':
        if a.kind=='openapi':
            text=json.dumps(app.openapi(),indent=2)+'\n'; target=a.output or 'openapi.json'; pathlib.Path(target).write_text(text,encoding='utf-8'); print(target)
        else: print('# Client generation is intentionally schema-driven; use the exported OpenAPI document with your preferred generator.')
    elif a.command=='config':
        print(json.dumps({'title':app.title,'version':app.version,'debug':app.debug,'max_body_size':app.max_body_size,'routes':len(app.router.routes)},indent=2))
    elif a.command=='plugins':
        for plugin in app.plugins: print(f'{getattr(plugin,"name",plugin.__class__.__name__)} {getattr(plugin,"version","")}')
    elif a.command=='export':
        text=json.dumps(app.openapi(),indent=2)+'\n';
        if a.output:pathlib.Path(a.output).write_text(text,encoding='utf-8'); print(a.output)
        else:print(text)
    elif a.command=='shell':
        ns={'app':app}; exec('from pyapify import *',ns); print('PyAPIfy shell — app is available as `app`'); import code; code.interact(local=ns)
    return 0

def _serve(path,debug): load(path).run(debug=debug); return 0

def create_project(name):
    root=pathlib.Path(name); root.mkdir(parents=True,exist_ok=True)
    (root/'app.py').write_text('from pyapify import PyAPIfy\n\napi = PyAPIfy()\n\n@api.get("/")\ndef home():\n    return {"message": "Hello from PyAPIfy!"}\n\nif __name__ == "__main__":\n    api.run(debug=True)\n',encoding='utf-8')
    (root/'README.md').write_text(f'# {name}\n\nRun `pyapify dev app.py`.\n',encoding='utf-8'); print(f'Created {root}/'); return 0

def create_certificates(output,hostname):
    try:
        from ..server.tls import generate_self_signed
        cert,key=generate_self_signed(output,hostname); print(f'Certificate: {cert}\nKey: {key}'); return 0
    except (ImportError,AttributeError):
        print('Certificate generation requires the optional TLS helper. Supply certfile/keyfile to `api.run()`.',file=sys.stderr); return 1

if __name__=='__main__': raise SystemExit(main())
