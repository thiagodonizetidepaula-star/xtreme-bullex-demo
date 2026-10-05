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
