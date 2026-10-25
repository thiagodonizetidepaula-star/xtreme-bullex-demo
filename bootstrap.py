"""Baixa fonte fixada; preserva TLS e evita executar setup.py remoto."""
import io,pathlib,urllib.request,zipfile,ast
ROOT=pathlib.Path(__file__).resolve().parent
SHA='3178f332db662ea60c570c842362b391aa618c57'
url=f'https://codeload.github.com/CassDs/bullexapi/zip/{SHA}'
print('Baixando biblioteca não oficial CassDs/bullexapi, revisão fixa...')
data=urllib.request.urlopen(url,timeout=30).read()
with zipfile.ZipFile(io.BytesIO(data)) as z:
    for item in z.infolist():
        parts=pathlib.PurePosixPath(item.filename).parts
        if len(parts)>2 and parts[1]=='bullexapi' and item.filename.endswith('.py'):
            dest=ROOT/'vendor'/pathlib.Path(*parts[1:])
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(z.read(item))
p=ROOT/'vendor/bullexapi/api.py';src=p.read_text()
src=src.replace('self.session.verify = False','self.session.verify = True')
src=src.replace('"check_hostname": False, "cert_reqs": ssl.CERT_NONE, "ca_certs": "cacert.pem"','"check_hostname": True, "cert_reqs": ssl.CERT_REQUIRED')
tree=ast.parse(src)
class Patch(ast.NodeTransformer):
    def visit_Call(self,node):
        self.generic_visit(node)
        if isinstance(node.func,ast.Attribute) and node.func.attr=='request':
            if not any(k.arg=='timeout' for k in node.keywords): node.keywords.append(ast.keyword(arg='timeout',value=ast.Constant(15)))
        return node
    def visit_While(self,node):
        self.generic_visit(node)
        node.body.insert(0,ast.Expr(ast.Call(ast.Attribute(ast.Name('time',ast.Load()),'sleep',ast.Load()),[ast.Constant(.01)],[])))
        return node
tree=Patch().visit(tree);ast.fix_missing_locations(tree);p.write_text(ast.unparse(tree))
p=ROOT/'vendor/bullexapi/stable_api.py';tree=Patch().visit(ast.parse(p.read_text()));ast.fix_missing_locations(tree);p.write_text(ast.unparse(tree))
assert 'CERT_NONE' not in (ROOT/'vendor/bullexapi/api.py').read_text()
print('Biblioteca preparada: certificados verificados; chamadas HTTP com timeout.')


# Keep IQ Option 2026 fork isolated from Bullex.
IQ_SHA='acac6e08333466ae188c7dfa7fd2a03174e34ca2'
try:
    iq_url=f'https://codeload.github.com/victalejo/iqoptionapi/zip/{IQ_SHA}'
    iq_data=urllib.request.urlopen(iq_url,timeout=30).read()
    allowed={'__init__.py','api.py','stable_api.py','constants.py','country_id.py',
             'expiration.py','global_value.py','http','ws'}
    with zipfile.ZipFile(io.BytesIO(iq_data)) as iqzip:
        for member in iqzip.infolist():
            parts=pathlib.PurePosixPath(member.filename).parts
            if len(parts)<2 or not member.filename.endswith('.py'):continue
            relative=parts[1:]
            if relative[0] not in allowed:continue
            dest=ROOT/'vendor_iq/iqoptionapi'/pathlib.Path(*relative)
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(iqzip.read(member))
    iq_api=ROOT/'vendor_iq/iqoptionapi/api.py'
    iq_stable=ROOT/'vendor_iq/iqoptionapi/stable_api.py'
    if not iq_api.is_file() or not iq_stable.is_file():raise RuntimeError('Pacote IQ incompleto')
    src=iq_api.read_text()
    assert 'self.session.verify = False' in src
    assert '"check_hostname": False, "cert_reqs": ssl.CERT_NONE, "ca_certs": "cacert.pem"' in src
    src=src.replace('self.session.verify = False','self.session.verify = True')
    src=src.replace('"check_hostname": False, "cert_reqs": ssl.CERT_NONE, "ca_certs": "cacert.pem"','"check_hostname": True, "cert_reqs": ssl.CERT_REQUIRED')
    tree=Patch().visit(ast.parse(src));ast.fix_missing_locations(tree);iq_api.write_text(ast.unparse(tree))
    tree=Patch().visit(ast.parse(iq_stable.read_text()));ast.fix_missing_locations(tree);iq_stable.write_text(ast.unparse(tree))
    assert 'CERT_NONE' not in iq_api.read_text()
    print('IQ Option 2026: biblioteca comunitária isolada e TLS verificado.')
except Exception as err:
    print('IQ Option indisponível no bootstrap; Bullex preservada: '+type(err).__name__)
