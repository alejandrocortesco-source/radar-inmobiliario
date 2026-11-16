"""Paquete determinista del árbol local, sin commit ni acceso a Cloud."""
from pathlib import Path
import hashlib,json,subprocess,tarfile,io,sys

ROOT=Path(__file__).resolve().parents[1]

def prepare(output=None):
    names=subprocess.check_output(['git','--no-optional-locks','--work-tree='+str(ROOT),'ls-files','-z','--cached','--others','--exclude-standard'],cwd=ROOT).decode().split('\0')
    files={name:(ROOT/name).read_bytes() for name in sorted(set(names)) if name and (ROOT/name).is_file()}
    hashes={name:hashlib.sha256(data).hexdigest() for name,data in files.items()}
    tree=hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    manifest=dict(version='0.14.0',base_commit=head,source_tree=tree,files=hashes)
    folder=Path(output or ROOT/'.tmp/releases')/tree/head[:12];folder.mkdir(parents=True,exist_ok=True)
    target=folder/'source.tar'
    if not target.exists():
        with tarfile.open(target,'w',format=tarfile.GNU_FORMAT) as tar:
            for name,data in list(files.items())+[('RELEASE.json',json.dumps(manifest,sort_keys=True,indent=2).encode())]:
                info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644;info.mtime=0
                tar.addfile(info,io.BytesIO(data))
    if verify(target)!=manifest:raise ValueError('Manifiesto distinto del candidato solicitado')
    (folder/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2),encoding='utf-8')
    return target,manifest

def verify(path):
    with tarfile.open(path) as tar:
        manifest=json.load(tar.extractfile('RELEASE.json'))
        if len(tar.getnames())!=len(manifest['files'])+1:raise ValueError('Contenido inesperado')
        for name,digest in manifest['files'].items():
            if hashlib.sha256(tar.extractfile(name).read()).hexdigest()!=digest:raise ValueError('Paquete alterado: '+name)
        tree=hashlib.sha256(json.dumps(manifest['files'],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if tree!=manifest['source_tree']:raise ValueError('Huella incorrecta')
    return manifest

if __name__=='__main__':
    target,manifest=prepare();print(json.dumps(dict(package=str(target),version=manifest['version'],base_commit=manifest['base_commit'],source_tree=manifest['source_tree'])))
