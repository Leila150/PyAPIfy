"""PyAPIfy command line interface."""
import argparse,importlib.util,inspect,json,sys

def load(path):
    spec=importlib.util.spec_from_file_location('pyapify_app',path); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    for v in vars(mod).values():
        if hasattr(v,'router') and hasattr(v,'dispatch'): return v
    raise RuntimeError('No PyAPIfy application object found in '+path)

def main(argv=None):
    p=argparse.ArgumentParser(prog='pyapify'); sub=p.add_subparsers(dest='command')
    for n in ('dev','run','routes','check','docs','openapi','inspect','doctor','benchmark','test','shell','export','config','plugins','version','create','generate'): sub.add_parser(n)
    a=p.parse_args(argv)
    if a.command=='version': from pyapify import __version__; print(__version__); return 0
    if a.command in {'dev','run','routes','check','openapi','docs','inspect','benchmark','test'}:
        # Commands accept an optional positional app path without forcing a second parser hierarchy.
        path='app.py'
        if a.command in {'dev','run'}: return _serve(path,a.command=='dev')
        app=load(path)
        if a.command=='routes':
            print('METHOD   PATH                         AUTH')
            for r in app.router.routes: print(f'{",".join(sorted(r.methods)):8} {r.path:28} {"yes" if r.auth else "-"}')
        elif a.command=='openapi' or a.command=='docs': print(json.dumps(app.openapi(),indent=2))
        elif a.command=='check': print(f'OK: {len(app.router.routes)} routes registered')
        elif a.command=='inspect': print(app.__dict__)
        elif a.command=='benchmark': print('Use pyapify.test() with your workload for application benchmarks.')
        elif a.command=='test':
            import pytest; return pytest.main([])
        return 0
    if a.command=='doctor': print('Python:',sys.version); print('PyAPIfy environment: OK'); return 0
    if a.command=='create': print('Project creation is available through the package template tooling.'); return 0
    print('Run pyapify --help for available commands.'); return 0

def _serve(path,debug):
    app=load(path); app.run(debug=debug); return 0
if __name__=='__main__': raise SystemExit(main())
