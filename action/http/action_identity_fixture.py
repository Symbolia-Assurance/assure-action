"""Public Action scope-binding fixture, created by the caller before capture.

No response/sidecar authority, network, key file, environment key or key output.
"""
import argparse
import ast
import hashlib
import os
from pathlib import Path
import stat
import types

FLAGS=dict(execution_authorized=False,hardware_authorized=False,
           industrial_release_authorized=False,release_allowed=False,
           physical_validation=False,simulation=True,self_approved=False)
COLLECTOR_PIN='916af00b93b49df84fc2e186e95b8d184fc93917a06696bed5c7f4aa394cae9b'
BINDING_PIN='64889563b2b974c736dab5f45f66c9cf1be464a9a16e81cb17e3508f2220be8c'

class ProducerError(Exception):
    def __init__(self,code):
        self.code=code
        super().__init__(code)


def _source(path):
    opened=[]
    try:
        opened.append(os.open('/',os.O_RDONLY|os.O_DIRECTORY))
        for part in path.absolute().parts[1:-1]:
            opened.append(os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=opened[-1]))
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=opened[-1]);opened.append(fd)
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size>131072:raise ProducerError('PACKAGE-DIGEST-MISMATCH')
        data=bytearray()
        while len(data)<=131072:
            part=os.read(fd,min(65536,131073-len(data)))
            if not part:break
            data.extend(part)
        if len(data)>131072:raise ProducerError('PACKAGE-DIGEST-MISMATCH')
        return bytes(data)
    except OSError:raise ProducerError('PACKAGE-DIGEST-MISMATCH') from None
    finally:
        for fd in reversed(opened):os.close(fd)


def _collector():
    base=Path(__file__).absolute().parent
    binding_path=base/'scope_binding.py';collector_path=base/'collector/collect_http.py'
    binding_data=_source(binding_path);collector_data=_source(collector_path)
    if hashlib.sha256(binding_data).hexdigest()!=BINDING_PIN or hashlib.sha256(collector_data).hexdigest()!=COLLECTOR_PIN:
        raise ProducerError('PACKAGE-DIGEST-MISMATCH')
    # Remove the pinned collector's import-loader bootstrap BEFORE execution.
    # Reading a source pin then importing it could execute a matching cached
    # pyc. Execute only the verified helper bytes into a fresh module instead.
    bootstrap=ast.parse("""_binding_spec = importlib.util.spec_from_file_location(
    'http_collector_scope_binding', Path(__file__).resolve().parents[1]/'scope_binding.py')
scope_binding = importlib.util.module_from_spec(_binding_spec)
_binding_spec.loader.exec_module(scope_binding)
""").body
    tree=ast.parse(collector_data,filename=str(collector_path))
    expected=[ast.dump(node,include_attributes=False) for node in bootstrap]
    matches=[i for i in range(len(tree.body)-len(bootstrap)+1)
             if [ast.dump(node,include_attributes=False) for node in tree.body[i:i+len(bootstrap)]]==expected]
    if len(matches)!=1:raise ProducerError('PACKAGE-DIGEST-MISMATCH')
    start=matches[0]
    del tree.body[start:start+len(bootstrap)]
    binding=types.ModuleType('http_action_fixture_verified_scope_binding')
    binding.__file__=str(binding_path)
    exec(compile(binding_data,str(binding_path),'exec'),binding.__dict__)
    namespace={'__name__':'http_action_fixture_collector','__file__':str(collector_path),
               'scope_binding':binding}
    exec(compile(tree,str(collector_path),'exec'),namespace)
    if _source(binding_path)!=binding_data:raise ProducerError('PACKAGE-DIGEST-MISMATCH')
    return namespace


def produce_action_binding(fixture_dir,out,*,identity_key,identity_key_id):
    collector=_collector()
    endpoints=collector['_fixture_endpoints'](fixture_dir)
    scope=collector['scope_binding'].caller_scope(endpoints,identity_key,identity_key_id)
    collector['_write_caller_scope'](out,scope)
    return scope


class _Parser(argparse.ArgumentParser):
    def error(self,message):raise ProducerError('CLI-INVALID')


def main(argv=None):
    parser=_Parser(description='Write public Action identity fixture from independent caller manifest')
    parser.add_argument('--fixture-dir',required=True)
    parser.add_argument('--out',required=True)
    parser.add_argument('--identity-key-fd',type=int,required=True)
    parser.add_argument('--identity-key-id',required=True)
    try:
        args=parser.parse_args(argv)
        collector=_collector()
        # Read caller selection before response collection; no response file
        # or uploaded sidecar is consulted by this endpoint-only helper.
        endpoints=collector['_fixture_endpoints'](args.fixture_dir)
        key=collector['_read_identity_key_fd'](args.identity_key_fd)
        scope=collector['scope_binding'].caller_scope(endpoints,key,args.identity_key_id)
        collector['_write_caller_scope'](args.out,scope)
        return 0
    except Exception as error:
        code=getattr(error,'code',None)
        if not isinstance(code,str) or not code.replace('-','').isalnum() or code.upper()!=code:
            code='PRODUCER-INTERNAL'
        import sys
        sys.stderr.write('HTTP identity producer refused: '+code+'\n')
        return 3


if __name__=='__main__':
    raise SystemExit(main())
