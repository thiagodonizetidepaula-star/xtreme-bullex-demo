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


# Vendor isolation: keep IQ Option's community library separate from Bullex.
IQ_SHA='8a903cc094a74af1ed935a56a2d6b5a9ed3319d7'
try:
    iq_url=f'https://codeload.github.com/iqoptionapi/iqoptionapi/zip/{IQ_SHA}'
    iq_data=urllib.request.urlopen(iq_url,timeout=30).read()
    with zipfile.ZipFile(io.BytesIO(iq_data)) as archive:
        for member in archive.infolist():
            components=pathlib.PurePosixPath(member.filename).parts
            if (len(components)>2 and components[1]=='iqoptionapi'
                    and member.filename.endswith('.py')):
                destination=ROOT/'vendor_iq'/pathlib.Path(*components[1:])
                destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_bytes(archive.read(member))
    iq_api=ROOT/'vendor_iq/iqoptionapi/api.py'
    source=iq_api.read_text()
    assert 'self.session.verify = False' in source
    assert '"check_hostname": False, "cert_reqs": ssl.CERT_NONE, "ca_certs": "cacert.pem"' in source
    source=source.replace('self.session.verify = False','self.session.verify = True')
    source=source.replace('"check_hostname": False, "cert_reqs": ssl.CERT_NONE, "ca_certs": "cacert.pem"','"check_hostname": True, "cert_reqs": ssl.CERT_REQUIRED')
    tree=Patch().visit(ast.parse(source));ast.fix_missing_locations(tree);iq_api.write_text(ast.unparse(tree))
    iq_stable=ROOT/'vendor_iq/iqoptionapi/stable_api.py'
    tree=Patch().visit(ast.parse(iq_stable.read_text()));ast.fix_missing_locations(tree);iq_stable.write_text(ast.unparse(tree))
    assert 'CERT_NONE' not in iq_api.read_text() and 'self.session.verify = False' not in iq_api.read_text()
    print('IQ Option comunitária preparada isoladamente, com TLS verificado.')
except Exception as err:
    print('IQ Option temporariamente indisponível (Bullex não afetada): '+str(err)[:150])
